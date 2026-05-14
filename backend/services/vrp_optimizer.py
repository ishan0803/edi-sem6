"""
VRP Objective Optimizer
=======================
Core convergence engine:  Optimal ETA = Tier_Adjusted_T_transit + P_SAP + C_ZAFI

Uses OR-Tools CP routing model to assign orders to riders while minimising
total "True Cost" (friction-aware ETA).
"""
from __future__ import annotations
import asyncio, logging, math, os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import FulfillmentCentre
from services.nlp_sap import compute_sap
from services.osm_zafi import compute_zafi
from services.eta_calculator import get_tier_factor, _haversine

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
MAX_ORDERS_PER_RIDER = 5
SLA_SECONDS = 600

def _build_ors_matrix(coordinates):
    if not ORS_API_KEY or len(coordinates) < 2:
        return None
    try:
        resp = requests.post(ORS_MATRIX_URL, json={"locations": coordinates, "metrics": ["duration"], "units": "m"},
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("durations")
    except Exception as exc:
        logger.warning("ORS matrix failed: %s", exc)
        return None

def _haversine_matrix(coords):
    n = len(coords)
    matrix = [[0.0]*n for _ in range(n)]
    speed = 25000/3600
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = _haversine(coords[i]["lat"], coords[i]["lon"], coords[j]["lat"], coords[j]["lon"]) / speed
    return matrix

def _solve_vrp(true_cost_matrix, num_vehicles, depot_indices, num_locations):
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        logger.error("ortools not installed")
        return None
    depot = depot_indices[0] if depot_indices else 0
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def cost_cb(fi, ti):
        return true_cost_matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]
    cb_idx = routing.RegisterTransitCallback(cost_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(cb_idx)

    def demand_cb(fi):
        node = manager.IndexToNode(fi)
        return 0 if node in depot_indices else 1
    d_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(d_idx, 0, [MAX_ORDERS_PER_RIDER]*num_vehicles, True, "Capacity")

    routing.AddDimension(cb_idx, SLA_SECONDS, SLA_SECONDS*3, True, "Time")
    td = routing.GetDimensionOrDie("Time")
    for i in range(num_locations):
        if i not in depot_indices:
            td.SetCumulVarSoftUpperBound(manager.NodeToIndex(i), SLA_SECONDS, 100)

    sp = pywrapcp.DefaultRoutingSearchParameters()
    sp.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sp.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    sp.time_limit.seconds = 5
    solution = routing.SolveWithParameters(sp)
    if not solution:
        return None
    routes = []
    for v in range(num_vehicles):
        route = []
        idx = routing.Start(v)
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node not in depot_indices:
                route.append(node)
            idx = solution.Value(routing.NextVar(idx))
        routes.append(route)
    return routes

async def dispatch_orders(orders: List[Dict[str, Any]], db: AsyncSession, available_riders: Optional[int] = None) -> Dict:
    result = await db.execute(select(FulfillmentCentre))
    stores = result.scalars().all()
    if not stores: return {"error": "No active stores configured."}
    if not orders: return {"error": "No orders to dispatch."}
    num_riders = available_riders or (len(stores) * 3)

    store_coords = [{"lat": s.lat, "lon": s.lon, "id": s.id, "name": s.name} for s in stores]
    order_coords = [{"lat": o["lat"], "lon": o["lon"], "id": o["order_id"]} for o in orders]
    all_coords = store_coords + order_coords
    depot_indices = list(range(len(store_coords)))
    num_locations = len(all_coords)

    ors_locs = [[c["lon"], c["lat"]] for c in all_coords]
    loop = asyncio.get_running_loop()
    ors_matrix = await loop.run_in_executor(_executor, _build_ors_matrix, ors_locs)
    if ors_matrix is None:
        ors_matrix = _haversine_matrix(all_coords)

    sap_results = await asyncio.gather(*[compute_sap(o["address_text"]) for o in orders])
    zafi_results = await asyncio.gather(*[compute_zafi(o["lat"], o["lon"]) for o in orders])
    tier_factor, tier_label = get_tier_factor(stores[0].lat, stores[0].lon)

    true_cost = [[0]*num_locations for _ in range(num_locations)]
    for i in range(num_locations):
        for j in range(num_locations):
            base = ors_matrix[i][j] if ors_matrix[i][j] else 0
            adjusted = base * tier_factor
            penalty = 0
            if j >= len(store_coords):
                oi = j - len(store_coords)
                penalty = sap_results[oi]["penalty_seconds"] + zafi_results[oi]["penalty_seconds"]
            true_cost[i][j] = int(adjusted + penalty)

    routes = await loop.run_in_executor(_executor, _solve_vrp, true_cost, num_riders, depot_indices, num_locations)
    if routes is None:
        return {"error": "VRP solver could not find a feasible solution."}

    riders_out = []
    for ridx, route in enumerate(routes):
        if not route: continue
        assigned = store_coords[0]
        if route:
            foi = route[0] - len(store_coords)
            md = float("inf")
            for sc in store_coords:
                d = _haversine(sc["lat"], sc["lon"], orders[foi]["lat"], orders[foi]["lon"])
                if d < md: md, assigned = d, sc

        details = []
        for ni in route:
            oi = ni - len(store_coords)
            if oi < 0 or oi >= len(orders): continue
            o = orders[oi]
            si = store_coords.index(assigned)
            bt = ors_matrix[si][ni] if ors_matrix else 0
            ta = bt * tier_factor
            sp_s, zf_s = sap_results[oi]["penalty_seconds"], zafi_results[oi]["penalty_seconds"]
            details.append({"order_id": o["order_id"], "lat": o["lat"], "lon": o["lon"],
                "address_text": o["address_text"], "base_transit_sec": round(bt,1),
                "tier_factor": tier_factor, "tier_label": tier_label, "tier_adjusted_sec": round(ta,1),
                "sap_sec": sp_s, "sap_breakdown": sap_results[oi],
                "zafi_sec": zf_s, "zafi_breakdown": zafi_results[oi], "total_eta_sec": round(ta+sp_s+zf_s,1)})
        if details:
            riders_out.append({"rider_id": ridx, "store_id": assigned["id"], "store_name": assigned["name"],
                "store_lat": assigned["lat"], "store_lon": assigned["lon"], "route": details,
                "total_cost_sec": sum(r["total_eta_sec"] for r in details)})

    return {"riders": riders_out, "meta": {"total_orders": len(orders), "total_riders_used": len(riders_out),
        "tier_factor": tier_factor, "tier_label": tier_label, "sla_target_sec": SLA_SECONDS}}
