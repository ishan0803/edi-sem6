"""
Dispatch & Logistics Router
============================
Exposes all Quick Commerce endpoints:
  - POST /api/dispatch           → VRP-optimized multi-rider routing
  - POST /api/eta/customer       → Pin-to-ETA for customer location
  - POST /api/inventory/train-synthetic → Trigger synthetic data + GNN
  - GET  /api/inventory/recommendations → GNN transfer recommendations
  - GET  /api/inventory/data      → Synthetic chart data
  - CRUD /api/skus/*              → Custom SKU catalogue
  - CRUD /api/inventory/*         → Real hub inventory management
  - POST /api/inventory/rebalance → GNN rebalance on real inventory
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sa_delete
from typing import Dict, Any, List

from database import get_db
from schemas import (
    DispatchRequest, CustomerETARequest, SKUCreate, SKUResponse,
    StockUpsert, StockResponse, HubInventorySummary,
)
from models import CustomSKU, HubInventory, FulfillmentCentre
from services.vrp_optimizer import dispatch_orders
from services.eta_calculator import customer_eta
from services.synthetic_gnn import train_synthetic, get_recommendations, get_synthetic_data, rebalance_real_inventory

router = APIRouter()


# ── Dispatch & ETA ───────────────────────────────────────────────────────────

@router.post("/dispatch", response_model=Dict[str, Any])
async def api_dispatch(payload: DispatchRequest, db: AsyncSession = Depends(get_db)):
    """
    Accept a list of orders and return OR-Tools-optimized rider routes
    with fully broken-down ETAs (Base, Tier-Adjusted, SAP, ZAFI).
    """
    orders = [o.model_dump() for o in payload.orders]
    result = await dispatch_orders(orders, db, payload.available_riders)
    return result


@router.post("/eta/customer", response_model=Dict[str, Any])
async def api_customer_eta(payload: CustomerETARequest, db: AsyncSession = Depends(get_db)):
    """
    Accept a customer lat/lon, find the nearest active store,
    and return a tier-adjusted estimated delivery time.
    """
    result = await customer_eta(payload.lat, payload.lon, db)
    return result


# ── Synthetic GNN (legacy, still works) ──────────────────────────────────────

@router.post("/inventory/train-synthetic", response_model=Dict[str, Any])
async def api_train_synthetic(db: AsyncSession = Depends(get_db)):
    """
    Trigger synthetic data generation and GNN model training.
    Simulates 30 days of demand across all active stores.
    """
    result = await train_synthetic(db)
    return result


@router.get("/inventory/recommendations", response_model=Dict[str, Any])
async def api_inventory_recommendations():
    """
    Return the latest GNN-generated inventory transfer recommendations
    and network health metrics.
    """
    result = await get_recommendations()
    return result


@router.get("/inventory/data", response_model=Dict[str, Any])
async def api_inventory_data():
    """
    Return aggregated synthetic stock vs order data for frontend charting.
    """
    result = await get_synthetic_data()
    return result


# ── Custom SKU Catalogue ─────────────────────────────────────────────────────

@router.get("/skus", response_model=List[SKUResponse])
async def list_skus(db: AsyncSession = Depends(get_db)):
    """Return all custom SKUs."""
    result = await db.execute(select(CustomSKU).order_by(CustomSKU.name))
    return result.scalars().all()


@router.post("/skus", response_model=SKUResponse)
async def create_sku(payload: SKUCreate, db: AsyncSession = Depends(get_db)):
    """Add a new SKU to the catalogue."""
    # Check for duplicate ID
    existing = await db.get(CustomSKU, payload.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"SKU '{payload.id}' already exists.")
    sku = CustomSKU(id=payload.id, name=payload.name, category=payload.category, unit_cost=payload.unit_cost)
    db.add(sku)
    await db.commit()
    await db.refresh(sku)
    return sku


@router.delete("/skus/{sku_id}")
async def delete_sku(sku_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a SKU and all associated inventory records."""
    sku = await db.get(CustomSKU, sku_id)
    if not sku:
        raise HTTPException(status_code=404, detail="SKU not found.")
    # Cascade: remove inventory for this SKU
    await db.execute(sa_delete(HubInventory).where(HubInventory.sku_id == sku_id))
    await db.delete(sku)
    await db.commit()
    return {"status": "deleted", "sku_id": sku_id}


# ── Real Hub Inventory CRUD ──────────────────────────────────────────────────

@router.get("/inventory/all", response_model=List[HubInventorySummary])
async def get_all_inventory(db: AsyncSession = Depends(get_db)):
    """Get inventory grouped by hub with SKU names resolved."""
    hubs_result = await db.execute(select(FulfillmentCentre).order_by(FulfillmentCentre.name))
    hubs = hubs_result.scalars().all()

    inv_result = await db.execute(select(HubInventory).order_by(HubInventory.hub_id, HubInventory.sku_id))
    all_inv = inv_result.scalars().all()

    sku_result = await db.execute(select(CustomSKU))
    sku_map = {s.id: s.name for s in sku_result.scalars().all()}

    hub_map = {h.id: h.name for h in hubs}

    # Group by hub
    grouped: dict = {}
    for inv in all_inv:
        if inv.hub_id not in grouped:
            grouped[inv.hub_id] = []
        grouped[inv.hub_id].append(StockResponse(
            id=inv.id, hub_id=inv.hub_id, sku_id=inv.sku_id,
            quantity=inv.quantity,
            hub_name=hub_map.get(inv.hub_id, inv.hub_id),
            sku_name=sku_map.get(inv.sku_id, inv.sku_id),
        ))

    summaries = []
    for hub in hubs:
        items = grouped.get(hub.id, [])
        summaries.append(HubInventorySummary(
            hub_id=hub.id, hub_name=hub.name,
            total_skus=len(items),
            total_quantity=sum(i.quantity for i in items),
            items=items,
        ))
    return summaries


@router.post("/inventory/stock", response_model=StockResponse)
async def upsert_stock(payload: StockUpsert, db: AsyncSession = Depends(get_db)):
    """Add or update stock for a hub + SKU combo. If it exists, update quantity."""
    # Validate hub exists
    hub = await db.get(FulfillmentCentre, payload.hub_id)
    if not hub:
        raise HTTPException(status_code=404, detail=f"Hub '{payload.hub_id}' not found.")
    # Validate SKU exists
    sku = await db.get(CustomSKU, payload.sku_id)
    if not sku:
        raise HTTPException(status_code=404, detail=f"SKU '{payload.sku_id}' not found.")

    # Check for existing record
    result = await db.execute(
        select(HubInventory).where(
            HubInventory.hub_id == payload.hub_id,
            HubInventory.sku_id == payload.sku_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity = payload.quantity
        await db.commit()
        await db.refresh(existing)
        return StockResponse(
            id=existing.id, hub_id=existing.hub_id, sku_id=existing.sku_id,
            quantity=existing.quantity, hub_name=hub.name, sku_name=sku.name,
        )
    else:
        record = HubInventory(hub_id=payload.hub_id, sku_id=payload.sku_id, quantity=payload.quantity)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return StockResponse(
            id=record.id, hub_id=record.hub_id, sku_id=record.sku_id,
            quantity=record.quantity, hub_name=hub.name, sku_name=sku.name,
        )


@router.delete("/inventory/stock/{record_id}")
async def delete_stock(record_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a specific inventory record."""
    record = await db.get(HubInventory, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Stock record not found.")
    await db.delete(record)
    await db.commit()
    return {"status": "deleted", "id": record_id}


# ── GNN Rebalance on Real Inventory ─────────────────────────────────────────

@router.post("/inventory/rebalance", response_model=Dict[str, Any])
async def api_rebalance(db: AsyncSession = Depends(get_db)):
    """
    Run the GNN rebalancing engine on real hub inventory data.
    Returns cost-effective transfer recommendations weighted by distance.
    """
    result = await rebalance_real_inventory(db)
    return result
