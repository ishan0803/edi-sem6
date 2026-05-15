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
MAX_ORDERS_PER_RIDER = 8
SLA_SECONDS = 900  # 15 min SLA — realistic for Indian quick commerce


def _build_ors_matrix(coordinates):
    from services.ors_limiter import ors_matrix
    return ors_matrix(coordinates)


def _haversine_matrix(coords):
    """Build a transit time matrix using haversine + 20 km/h average speed."""
    n = len(coords)
    matrix = [[0.0]*n for _ in range(n)]
    speed = 20_000 / 3600  # 20 km/h in m/s
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = _haversine(
                    coords[i]["lat"], coords[i]["lon"],
                    coords[j]["lat"], coords[j]["lon"]
                ) / speed
    return matrix


def _solve_vrp(true_cost_matrix, num_vehicles, depot_indices, num_locations):
    """
    Solve the VRP using OR-Tools.
    Returns list of routes (each route = list of node indices), or None on failure.
    """
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        logger.error("ortools not installed — falling back to greedy assignment")
        return None

    depot = depot_indices[0] if depot_indices else 0
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def cost_cb(fi, ti):
        return true_cost_matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]
    cb_idx = routing.RegisterTransitCallback(cost_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(cb_idx)

    # Capacity constraint — max orders per rider
    def demand_cb(fi):
        node = manager.IndexToNode(fi)
        return 0 if node in depot_indices else 1
    d_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        d_idx, 0, [MAX_ORDERS_PER_RIDER]*num_vehicles, True, "Capacity"
    )

    # Time dimension — very generous hard limit, SLA enforced via soft bound only
    max_route_time = 30_000  # 8+ hours — effectively unconstrained
    routing.AddDimension(
        cb_idx,
        0,                    # no slack needed
        max_route_time,       # hard max cumul per vehicle
        True,                 # fix start cumul to zero
        "Time",
    )
    td = routing.GetDimensionOrDie("Time")
    for i in range(num_locations):
        if i not in depot_indices:
            idx = manager.NodeToIndex(i)
            # Soft bound: prefer under SLA, but penalty is low enough to not drop orders
            td.SetCumulVarSoftUpperBound(idx, SLA_SECONDS, 10)

    # Allow dropping orders only as absolute last resort (very high penalty)
    for i in range(num_locations):
        if i not in depot_indices:
            routing.AddDisjunction([manager.NodeToIndex(i)], 1_000_000)

    sp = pywrapcp.DefaultRoutingSearchParameters()
    sp.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sp.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    sp.time_limit.seconds = 5

    solution = routing.SolveWithParameters(sp)
    if not solution:
        logger.warning("OR-Tools VRP solver returned no solution")
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

    # Check if solver actually assigned any orders (vs dropping all via disjunction)
    total_assigned = sum(len(r) for r in routes)
    if total_assigned == 0:
        logger.warning("OR-Tools solved but dropped all orders — falling back to greedy")
        return None

    return routes


def _greedy_assign(orders, store_coords, ors_matrix, num_stores):
    """
    Fallback greedy assignment when OR-Tools is unavailable or fails.
    Assigns each order to its nearest store based on the transit matrix.
    Returns routes in the same format as _solve_vrp.
    """
    # Group orders by nearest store
    store_orders: Dict[int, List[int]] = {si: [] for si in range(num_stores)}
    for oi in range(len(orders)):
        order_idx = num_stores + oi
        best_store = 0
        best_cost = float("inf")
        for si in range(num_stores):
            cost = ors_matrix[si][order_idx] if ors_matrix[si][order_idx] else float("inf")
            if cost < best_cost:
                best_cost = cost
                best_store = si
        store_orders[best_store].append(order_idx)

    # Create one "route" per store that has orders
    routes = []
    for si in range(num_stores):
        if store_orders[si]:
            routes.append(store_orders[si])
    return routes


async def dispatch_orders(
    orders: List[Dict[str, Any]],
    db: AsyncSession,
    available_riders: Optional[int] = None,
) -> Dict:
    result = await db.execute(select(FulfillmentCentre))
    stores = result.scalars().all()
    if not stores:
        return {"error": "No active stores configured. Add hubs on the Map tab first."}
    if not orders:
        return {"error": "No orders to dispatch."}

    num_riders = available_riders or max(len(stores) * 2, math.ceil(len(orders) / 3))

    store_coords = [{"lat": s.lat, "lon": s.lon, "id": s.id, "name": s.name} for s in stores]
    order_coords = [{"lat": o["lat"], "lon": o["lon"], "id": o["order_id"]} for o in orders]
    all_coords = store_coords + order_coords
    depot_indices = list(range(len(store_coords)))
    num_locations = len(all_coords)

    # Build transit time matrix
    ors_locs = [[c["lon"], c["lat"]] for c in all_coords]
    loop = asyncio.get_running_loop()
    ors_mat = await loop.run_in_executor(_executor, _build_ors_matrix, ors_locs)
    if ors_mat is None:
        logger.info("Using haversine fallback matrix (ORS unavailable)")
        ors_mat = _haversine_matrix(all_coords)

    # Log sample distances for debugging
    if len(store_coords) > 0 and len(orders) > 0:
        sample_dist = _haversine(
            store_coords[0]["lat"], store_coords[0]["lon"],
            orders[0]["lat"], orders[0]["lon"]
        )
        sample_time = ors_mat[0][len(store_coords)]
        logger.info(
            "Sample: Store '%s' → Order '%s': %.1f km, %.0f sec transit",
            store_coords[0]["name"], orders[0]["order_id"],
            sample_dist / 1000, sample_time,
        )

    # Compute SAP and ZAFI penalties
    sap_results = await asyncio.gather(*[compute_sap(o["address_text"]) for o in orders])
    zafi_results = await asyncio.gather(*[
        compute_zafi(o["lat"], o["lon"], o.get("address_text", "")) for o in orders
    ])
    tier_factor, tier_label = get_tier_factor(stores[0].lat, stores[0].lon)

    # Build true cost matrix (transit × tier_factor + penalties at delivery node)
    true_cost = [[0]*num_locations for _ in range(num_locations)]
    for i in range(num_locations):
        for j in range(num_locations):
            base = ors_mat[i][j] if ors_mat[i][j] else 0
            adjusted = base * tier_factor
            penalty = 0
            if j >= len(store_coords):
                oi = j - len(store_coords)
                penalty = sap_results[oi]["penalty_seconds"] + zafi_results[oi]["penalty_seconds"]
            true_cost[i][j] = int(adjusted + penalty)

    # Try OR-Tools first
    routes = await loop.run_in_executor(
        _executor, _solve_vrp, true_cost, num_riders, depot_indices, num_locations
    )

    # Fallback to greedy if solver fails or drops all orders
    if routes is None:
        logger.warning("Using greedy assignment fallback")
        routes = _greedy_assign(orders, store_coords, ors_mat, len(store_coords))

    # Build response
    riders_out = []
    for ridx, route in enumerate(routes):
        if not route:
            continue

        # Find nearest store for this route's first order
        assigned = store_coords[0]
        first_order_idx = route[0] - len(store_coords)
        if 0 <= first_order_idx < len(orders):
            md = float("inf")
            for sc in store_coords:
                d = _haversine(sc["lat"], sc["lon"], orders[first_order_idx]["lat"], orders[first_order_idx]["lon"])
                if d < md:
                    md, assigned = d, sc

        details = []
        for ni in route:
            oi = ni - len(store_coords)
            if oi < 0 or oi >= len(orders):
                continue
            o = orders[oi]
            si = store_coords.index(assigned)
            bt = ors_mat[si][ni] if ors_mat[si][ni] else 0
            ta = bt * tier_factor
            sp_s = sap_results[oi]["penalty_seconds"]
            zf_s = zafi_results[oi]["penalty_seconds"]
            total = ta + sp_s + zf_s

            details.append({
                "order_id": o["order_id"],
                "lat": o["lat"],
                "lon": o["lon"],
                "address_text": o["address_text"],
                "base_transit_sec": round(bt, 1),
                "tier_factor": tier_factor,
                "tier_label": tier_label,
                "tier_adjusted_sec": round(ta, 1),
                "sap_sec": sp_s,
                "sap_breakdown": sap_results[oi],
                "zafi_sec": zf_s,
                "zafi_breakdown": zafi_results[oi],
                "total_eta_sec": round(total, 1),
            })

        if details:
            riders_out.append({
                "rider_id": ridx,
                "store_id": assigned["id"],
                "store_name": assigned["name"],
                "store_lat": assigned["lat"],
                "store_lon": assigned["lon"],
                "route": details,
                "total_cost_sec": sum(r["total_eta_sec"] for r in details),
            })

    if not riders_out:
        return {
            "error": "Could not assign any orders. Check that order coordinates are valid and hubs are configured.",
            "riders": [],
        }

    return {
        "riders": riders_out,
        "meta": {
            "total_orders": len(orders),
            "total_riders_used": len(riders_out),
            "tier_factor": tier_factor,
            "tier_label": tier_label,
            "sla_target_sec": SLA_SECONDS,
        },
    }
