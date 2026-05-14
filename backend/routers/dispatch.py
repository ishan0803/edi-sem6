"""
Dispatch & Logistics Router
============================
Exposes the four new Quick Commerce endpoints:
  - POST /api/dispatch           → VRP-optimized multi-rider routing
  - POST /api/eta/customer       → Pin-to-ETA for customer location
  - POST /api/inventory/train-synthetic → Trigger synthetic data + GNN
  - GET  /api/inventory/recommendations → GNN transfer recommendations
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from database import get_db
from schemas import DispatchRequest, CustomerETARequest
from services.vrp_optimizer import dispatch_orders
from services.eta_calculator import customer_eta
from services.synthetic_gnn import train_synthetic, get_recommendations, get_synthetic_data

router = APIRouter()


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
