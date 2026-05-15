"""
Synthetic Data Generator & GNN Rebalancing Engine
==================================================
Generates synthetic 30-day demand history across FulfillmentCentre nodes,
trains a lightweight 2-layer GCN to predict demand imbalances, and outputs
inter-store inventory transfer recommendations.

Also provides real-inventory rebalancing using the same GCN architecture,
weighted by haversine distance for cost-effective transfers.

All heavy compute is offloaded to ThreadPoolExecutor.
"""
from __future__ import annotations
import asyncio, logging, random, math, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import FulfillmentCentre, HubInventory, CustomSKU

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

# Module-level state for the trained model & synthetic data
_model_state: Dict[str, Any] = {"trained": False, "data": None, "recommendations": None}

# SKU catalogue for simulation
SKUS = [
    {"id": "SKU001", "name": "Mineral Water 1L", "category": "beverages", "base_demand": 80},
    {"id": "SKU002", "name": "Instant Noodles Pack", "category": "food", "base_demand": 60},
    {"id": "SKU003", "name": "Cold Brew Coffee 250ml", "category": "beverages", "base_demand": 40},
    {"id": "SKU004", "name": "Paracetamol Strip", "category": "pharma", "base_demand": 30},
    {"id": "SKU005", "name": "Phone Charger Cable", "category": "electronics", "base_demand": 20},
    {"id": "SKU006", "name": "Face Wash 100ml", "category": "personal_care", "base_demand": 35},
    {"id": "SKU007", "name": "Milk 500ml", "category": "dairy", "base_demand": 90},
    {"id": "SKU008", "name": "Bread Loaf", "category": "bakery", "base_demand": 70},
    {"id": "SKU009", "name": "Battery Pack AA", "category": "electronics", "base_demand": 25},
    {"id": "SKU010", "name": "Chips Party Pack", "category": "snacks", "base_demand": 55},
]


def _generate_synthetic_data(stores: List[Dict]) -> Dict:
    """Generate 30-day synthetic stock & order history with intentional imbalances."""
    random.seed(42)
    np.random.seed(42)
    n_days = 30
    today = datetime.now()
    stock_records, order_records = [], []

    for day_offset in range(n_days):
        date = (today - timedelta(days=n_days - day_offset)).strftime("%Y-%m-%d")
        # Simulate heatwave on days 10-15 → water demand spikes
        is_heatwave = 10 <= day_offset <= 15
        # Weekend effect
        day_of_week = (today - timedelta(days=n_days - day_offset)).weekday()
        is_weekend = day_of_week >= 5

        for si, store in enumerate(stores):
            for sku in SKUS:
                # --- Demand calculation with realistic variability ---
                base = sku["base_demand"]
                # Store-specific bias (some stores in busier areas)
                store_bias = 1.0 + (si % 3) * 0.15
                # Weekend boost for snacks/beverages
                weekend_mult = 1.3 if is_weekend and sku["category"] in ("snacks", "beverages") else 1.0
                # Heatwave spike for water
                heatwave_mult = 2.5 if is_heatwave and sku["id"] == "SKU001" else 1.0
                # Random noise
                noise = np.random.normal(1.0, 0.15)

                demand = int(base * store_bias * weekend_mult * heatwave_mult * noise)
                demand = max(0, demand)
                unique_customers = max(1, int(demand * random.uniform(0.5, 0.9)))

                # Stock: intentionally create imbalance
                # First store hoards water during heatwave
                if si == 0 and sku["id"] == "SKU001" and is_heatwave:
                    stock = demand * 3  # overstocked
                elif si > 0 and sku["id"] == "SKU001" and is_heatwave:
                    stock = max(0, demand - int(demand * 0.6))  # understocked
                else:
                    stock = int(demand * random.uniform(0.7, 1.4))

                stock_records.append({
                    "store_id": store["id"], "store_name": store["name"],
                    "article_id": sku["id"], "article_description": sku["name"],
                    "stock_qty": stock, "date": date,
                })
                order_records.append({
                    "store_id": store["id"], "store_name": store["name"],
                    "article_id": sku["id"], "order_qty": demand,
                    "unique_customers": unique_customers, "order_date": date,
                })

    return {"stock_records": stock_records, "order_records": order_records, "stores": stores, "skus": SKUS}


def _train_gnn(data: Dict) -> Dict:
    """Train a lightweight 2-layer GCN and compute transfer recommendations."""
    stores = data["stores"]
    skus = data["skus"]
    n_stores = len(stores)
    n_skus = len(skus)

    try:
        import torch
        import torch.nn.functional as F
        from torch_geometric.data import Data
        from torch_geometric.nn import GCNConv
    except ImportError:
        logger.warning("torch_geometric not available, using heuristic fallback")
        return _heuristic_recommendations(data)

    # Build feature matrix: each node = (store, sku) pair
    # Features: [avg_stock, avg_demand, stock_demand_ratio, trend]
    stock_by_key, demand_by_key = {}, {}
    for r in data["stock_records"]:
        k = (r["store_id"], r["article_id"])
        stock_by_key.setdefault(k, []).append(r["stock_qty"])
    for r in data["order_records"]:
        k = (r["store_id"], r["article_id"])
        demand_by_key.setdefault(k, []).append(r["order_qty"])

    node_features = []
    node_labels = []
    node_map = {}
    idx = 0
    for si, store in enumerate(stores):
        for ski, sku in enumerate(skus):
            k = (store["id"], sku["id"])
            stocks = stock_by_key.get(k, [0])
            demands = demand_by_key.get(k, [0])
            avg_s, avg_d = np.mean(stocks), np.mean(demands)
            ratio = avg_s / (avg_d + 1e-6)
            # Trend: linear regression slope
            if len(demands) > 1:
                x = np.arange(len(demands))
                trend = np.polyfit(x, demands, 1)[0]
            else:
                trend = 0
            node_features.append([avg_s, avg_d, ratio, trend])
            node_labels.append(avg_d)  # predict demand
            node_map[idx] = {"store_id": store["id"], "store_name": store["name"],
                             "sku_id": sku["id"], "sku_name": sku["name"]}
            idx += 1

    x = torch.tensor(node_features, dtype=torch.float)
    y = torch.tensor(node_labels, dtype=torch.float)

    # Build edges: connect same-SKU nodes across stores (bipartite)
    edge_src, edge_dst = [], []
    for ski in range(n_skus):
        for si in range(n_stores):
            for sj in range(n_stores):
                if si != sj:
                    edge_src.append(si * n_skus + ski)
                    edge_dst.append(sj * n_skus + ski)
    edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
    graph_data = Data(x=x, edge_index=edge_index, y=y)

    # Define a simple GCN
    class DemandGCN(torch.nn.Module):
        def __init__(self, in_ch, hidden, out_ch):
            super().__init__()
            self.conv1 = GCNConv(in_ch, hidden)
            self.conv2 = GCNConv(hidden, out_ch)
        def forward(self, data):
            x = F.relu(self.conv1(data.x, data.edge_index))
            x = self.conv2(x, data.edge_index)
            return x.squeeze(-1)

    model = DemandGCN(4, 16, 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    model.train()
    for epoch in range(100):
        optimizer.zero_grad()
        pred = model(graph_data)
        loss = F.mse_loss(pred, graph_data.y)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        predicted_demand = model(graph_data).numpy()

    # Compute transfer recommendations
    transfers = []
    for ski, sku in enumerate(skus):
        store_data_list = []
        for si, store in enumerate(stores):
            ni = si * n_skus + ski
            k = (store["id"], sku["id"])
            avg_stock = np.mean(stock_by_key.get(k, [0]))
            pred_dem = float(predicted_demand[ni])
            surplus = avg_stock - pred_dem
            store_data_list.append({"store_id": store["id"], "store_name": store["name"],
                              "avg_stock": round(float(avg_stock), 1), "predicted_demand": round(pred_dem, 1),
                              "surplus": round(float(surplus), 1)})
        # Find overstocked → understocked flows
        overstocked = [s for s in store_data_list if s["surplus"] > 5]
        understocked = [s for s in store_data_list if s["surplus"] < -5]
        for src in overstocked:
            for dst in understocked:
                qty = min(src["surplus"], abs(dst["surplus"]))
                if qty > 2:
                    transfers.append({"sku_id": sku["id"], "sku_name": sku["name"],
                        "from_store": src["store_id"], "from_name": src["store_name"],
                        "to_store": dst["store_id"], "to_name": dst["store_name"],
                        "transfer_qty": round(qty, 0), "priority": "high" if qty > 20 else "medium"})

    # Aggregate metrics
    total_shifted = sum(t["transfer_qty"] for t in transfers)
    stockouts = sum(1 for ni in range(len(predicted_demand))
                    if node_features[ni][0] < predicted_demand[ni] * 0.5)

    return {
        "transfers": transfers[:20],
        "metrics": {
            "stockouts_prevented": stockouts,
            "total_value_shifted": round(total_shifted, 0),
            "network_balance_score": round(100 - (stockouts / max(1, len(predicted_demand)) * 100), 1),
            "model_loss": round(float(loss.item()), 4),
        },
        "store_summaries": _build_store_summaries(data, predicted_demand, node_features, stores, skus, n_skus),
    }


def _build_store_summaries(data, predictions, features, stores, skus, n_skus):
    summaries = []
    for si, store in enumerate(stores):
        total_stock, total_demand, total_pred = 0, 0, 0
        for ski in range(n_skus):
            ni = si * n_skus + ski
            total_stock += features[ni][0]
            total_demand += features[ni][1]
            total_pred += float(predictions[ni])
        summaries.append({"store_id": store["id"], "store_name": store["name"],
            "total_avg_stock": round(total_stock, 0), "total_avg_demand": round(total_demand, 0),
            "total_predicted_demand": round(total_pred, 0),
            "health": "balanced" if abs(total_stock - total_demand) < total_demand * 0.2 else
                      "overstocked" if total_stock > total_demand else "understocked"})
    return summaries


def _heuristic_recommendations(data):
    """Fallback when torch_geometric is unavailable."""
    stores = data["stores"]
    skus = data["skus"]
    stock_by_key, demand_by_key = {}, {}
    for r in data["stock_records"]:
        stock_by_key.setdefault((r["store_id"], r["article_id"]), []).append(r["stock_qty"])
    for r in data["order_records"]:
        demand_by_key.setdefault((r["store_id"], r["article_id"]), []).append(r["order_qty"])

    transfers = []
    for sku in skus:
        store_surplus = []
        for store in stores:
            k = (store["id"], sku["id"])
            avg_s = np.mean(stock_by_key.get(k, [0]))
            avg_d = np.mean(demand_by_key.get(k, [0]))
            store_surplus.append({"store_id": store["id"], "store_name": store["name"],
                "surplus": avg_s - avg_d, "avg_stock": avg_s, "avg_demand": avg_d})
        over = [s for s in store_surplus if s["surplus"] > 5]
        under = [s for s in store_surplus if s["surplus"] < -5]
        for src in over:
            for dst in under:
                qty = min(src["surplus"], abs(dst["surplus"]))
                if qty > 2:
                    transfers.append({"sku_id": sku["id"], "sku_name": sku["name"],
                        "from_store": src["store_id"], "from_name": src["store_name"],
                        "to_store": dst["store_id"], "to_name": dst["store_name"],
                        "transfer_qty": round(qty, 0), "priority": "high" if qty > 20 else "medium"})
    return {"transfers": transfers[:20],
        "metrics": {"stockouts_prevented": len([t for t in transfers if t["priority"]=="high"]),
            "total_value_shifted": sum(t["transfer_qty"] for t in transfers),
            "network_balance_score": 75.0, "model_loss": None},
        "store_summaries": []}


async def train_synthetic(db: AsyncSession) -> Dict:
    """Generate synthetic data and train the GNN model."""
    result = await db.execute(select(FulfillmentCentre))
    stores = result.scalars().all()
    if not stores:
        return {"error": "No stores configured. Add stores first."}

    store_dicts = [{"id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon} for s in stores]
    loop = asyncio.get_running_loop()

    # Generate synthetic data
    data = await loop.run_in_executor(_executor, _generate_synthetic_data, store_dicts)
    _model_state["data"] = data

    # Train GNN
    recs = await loop.run_in_executor(_executor, _train_gnn, data)
    _model_state["trained"] = True
    _model_state["recommendations"] = recs

    return {"status": "success", "message": "Synthetic data generated and GNN model trained.",
        "stores_processed": len(store_dicts), "skus_simulated": len(SKUS), "days_simulated": 30}


async def get_recommendations() -> Dict:
    """Return the latest GNN transfer recommendations."""
    if not _model_state["trained"]:
        return {"error": "Model not trained yet. Call POST /api/inventory/train-synthetic first."}
    return _model_state["recommendations"]


async def get_synthetic_data() -> Dict:
    """Return raw synthetic data for visualization."""
    if not _model_state["data"]:
        return {"error": "No synthetic data generated yet."}
    data = _model_state["data"]
    # Aggregate for frontend charts
    store_daily = {}
    for r in data["order_records"]:
        k = (r["store_id"], r["order_date"])
        store_daily.setdefault(k, {"store_id": r["store_id"], "store_name": r["store_name"],
            "date": r["order_date"], "total_orders": 0, "total_stock": 0})
        store_daily[k]["total_orders"] += r["order_qty"]
    for r in data["stock_records"]:
        k = (r["store_id"], r["date"])
        if k in store_daily:
            store_daily[k]["total_stock"] += r["stock_qty"]
    return {"daily_aggregates": list(store_daily.values()), "skus": data["skus"]}


# ── Real Inventory Rebalancing ───────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _rebalance_with_gnn(hubs: List[Dict], skus: List[Dict], inventory: List[Dict]) -> Dict:
    """
    Run GCN on real inventory data and produce cost-effective transfer recommendations.
    Transfers are weighted by haversine distance between hubs.
    """
    n_hubs = len(hubs)
    n_skus = len(skus)
    if n_hubs < 2 or n_skus == 0:
        return {"transfers": [], "metrics": {
            "stockouts_prevented": 0, "total_units_shifted": 0,
            "estimated_cost_savings": 0, "network_balance_score": 100.0, "model_loss": None,
        }, "hub_summaries": []}

    # Build lookup: (hub_id, sku_id) → quantity
    inv_map: Dict[tuple, int] = {}
    for inv in inventory:
        inv_map[(inv["hub_id"], inv["sku_id"])] = inv["quantity"]

    # Compute network-wide average per SKU
    sku_avg: Dict[str, float] = {}
    for sku in skus:
        vals = [inv_map.get((h["id"], sku["id"]), 0) for h in hubs]
        sku_avg[sku["id"]] = float(np.mean(vals)) if vals else 0.0

    try:
        import torch
        import torch.nn.functional as F
        from torch_geometric.data import Data
        from torch_geometric.nn import GCNConv

        # Build node features: each node = (hub, sku) pair
        # Features: [stock_qty, network_avg_for_sku, ratio, hub_lat_norm, hub_lon_norm]
        node_features = []
        node_targets = []
        node_map = {}
        idx = 0
        for hi, hub in enumerate(hubs):
            for si, sku in enumerate(skus):
                qty = inv_map.get((hub["id"], sku["id"]), 0)
                avg = sku_avg[sku["id"]]
                ratio = qty / (avg + 1e-6)
                node_features.append([float(qty), avg, ratio, hub["lat"] / 90.0, hub["lon"] / 180.0])
                node_targets.append(avg)  # Target: network average (balanced state)
                node_map[idx] = {"hub_id": hub["id"], "hub_name": hub["name"],
                                 "sku_id": sku["id"], "sku_name": sku["name"],
                                 "lat": hub["lat"], "lon": hub["lon"]}
                idx += 1

        x = torch.tensor(node_features, dtype=torch.float)
        y = torch.tensor(node_targets, dtype=torch.float)

        # Build edges: connect same-SKU nodes across hubs (fully connected per SKU)
        edge_src, edge_dst = [], []
        for si in range(n_skus):
            for hi in range(n_hubs):
                for hj in range(n_hubs):
                    if hi != hj:
                        edge_src.append(hi * n_skus + si)
                        edge_dst.append(hj * n_skus + si)
        edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
        graph_data = Data(x=x, edge_index=edge_index, y=y)

        # GCN model
        class BalanceGCN(torch.nn.Module):
            def __init__(self, in_ch, hidden, out_ch):
                super().__init__()
                self.conv1 = GCNConv(in_ch, hidden)
                self.conv2 = GCNConv(hidden, out_ch)
            def forward(self, data):
                x = F.relu(self.conv1(data.x, data.edge_index))
                x = self.conv2(x, data.edge_index)
                return x.squeeze(-1)

        model = BalanceGCN(5, 32, 1)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        model.train()
        for epoch in range(150):
            optimizer.zero_grad()
            pred = model(graph_data)
            loss = F.mse_loss(pred, graph_data.y)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            predicted_ideal = model(graph_data).numpy()

        final_loss = float(loss.item())

    except ImportError:
        logger.warning("torch_geometric not available, using heuristic for real inventory")
        # Heuristic fallback: ideal = network average
        predicted_ideal = np.array([sku_avg[skus[idx % n_skus]["id"]] for idx in range(n_hubs * n_skus)])
        final_loss = None

    # Pre-compute distance matrix between hubs
    dist_matrix: Dict[tuple, float] = {}
    for i, h1 in enumerate(hubs):
        for j, h2 in enumerate(hubs):
            if i != j:
                dist_matrix[(h1["id"], h2["id"])] = _haversine_km(h1["lat"], h1["lon"], h2["lat"], h2["lon"])

    # Generate transfer recommendations
    transfers = []
    for si, sku in enumerate(skus):
        hub_data = []
        for hi, hub in enumerate(hubs):
            ni = hi * n_skus + si
            actual = inv_map.get((hub["id"], sku["id"]), 0)
            ideal = float(predicted_ideal[ni])
            surplus = actual - ideal
            hub_data.append({
                "hub_id": hub["id"], "hub_name": hub["name"],
                "actual": actual, "ideal": round(ideal, 1), "surplus": round(surplus, 1),
                "lat": hub["lat"], "lon": hub["lon"],
            })

        overstocked = sorted([h for h in hub_data if h["surplus"] > 2], key=lambda x: -x["surplus"])
        understocked = sorted([h for h in hub_data if h["surplus"] < -2], key=lambda x: x["surplus"])

        for src in overstocked:
            for dst in understocked:
                qty = min(src["surplus"], abs(dst["surplus"]))
                if qty < 1:
                    continue
                dist = dist_matrix.get((src["hub_id"], dst["hub_id"]), 999)
                # Cost: ₹2 per unit per km (simplified logistics cost model)
                transfer_cost = round(qty * dist * 2.0, 0)
                # Cost-effectiveness score: higher = better (units moved per rupee)
                cost_effectiveness = round(qty / (transfer_cost + 1), 4) if transfer_cost > 0 else 999

                transfers.append({
                    "sku_id": sku["id"], "sku_name": sku["name"],
                    "from_hub": src["hub_id"], "from_name": src["hub_name"],
                    "to_hub": dst["hub_id"], "to_name": dst["hub_name"],
                    "transfer_qty": round(qty),
                    "distance_km": round(dist, 1),
                    "estimated_cost": transfer_cost,
                    "cost_effectiveness": cost_effectiveness,
                    "priority": "high" if qty > 20 else "medium" if qty > 5 else "low",
                })
                # Reduce available surplus/deficit for subsequent matches
                src["surplus"] -= qty
                dst["surplus"] += qty

    # Sort by cost-effectiveness (best deals first)
    transfers.sort(key=lambda t: -t["cost_effectiveness"])

    # Build hub summaries
    hub_summaries = []
    for hi, hub in enumerate(hubs):
        total_actual, total_ideal = 0, 0
        for si in range(n_skus):
            ni = hi * n_skus + si
            actual = inv_map.get((hub["id"], skus[si]["id"]), 0)
            total_actual += actual
            total_ideal += float(predicted_ideal[ni])
        diff = total_actual - total_ideal
        hub_summaries.append({
            "hub_id": hub["id"], "hub_name": hub["name"],
            "total_stock": total_actual,
            "ideal_stock": round(total_ideal),
            "health": "balanced" if abs(diff) < total_ideal * 0.15 else
                      "overstocked" if diff > 0 else "understocked",
        })

    total_shifted = sum(t["transfer_qty"] for t in transfers)
    total_cost = sum(t["estimated_cost"] for t in transfers)
    stockouts = sum(1 for s in hub_summaries if s["health"] == "understocked")

    return {
        "transfers": transfers[:30],
        "metrics": {
            "stockouts_prevented": stockouts,
            "total_units_shifted": round(total_shifted),
            "total_transfer_cost": round(total_cost),
            "network_balance_score": round(100 - (stockouts / max(1, len(hubs)) * 100), 1),
            "model_loss": round(final_loss, 4) if final_loss else None,
        },
        "hub_summaries": hub_summaries,
    }


async def rebalance_real_inventory(db: AsyncSession) -> Dict:
    """Read real hub inventory from DB and run GNN rebalancing."""
    # Fetch hubs
    hub_result = await db.execute(select(FulfillmentCentre))
    hubs_raw = hub_result.scalars().all()
    if len(hubs_raw) < 2:
        return {"error": "Need at least 2 hubs to rebalance. Add more hubs first."}

    hubs = [{"id": h.id, "name": h.name, "lat": h.lat, "lon": h.lon} for h in hubs_raw]

    # Fetch custom SKUs
    sku_result = await db.execute(select(CustomSKU))
    skus_raw = sku_result.scalars().all()
    if not skus_raw:
        return {"error": "No SKUs defined. Add SKUs to the catalogue first."}

    skus = [{"id": s.id, "name": s.name, "category": s.category, "unit_cost": s.unit_cost} for s in skus_raw]

    # Fetch inventory
    inv_result = await db.execute(select(HubInventory))
    inv_raw = inv_result.scalars().all()
    if not inv_raw:
        return {"error": "No inventory data. Add stock to hubs first."}

    inventory = [{"hub_id": i.hub_id, "sku_id": i.sku_id, "quantity": i.quantity} for i in inv_raw]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, _rebalance_with_gnn, hubs, skus, inventory)
    return result
