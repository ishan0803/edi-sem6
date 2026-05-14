from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# ── Existing Centre schemas ──────────────────────────────────────────────────

class CentreBase(BaseModel):
    name: str
    lat: float
    lon: float

class CentreCreate(CentreBase):
    pass

class CentreResponse(CentreBase):
    id: str
    colour_idx: int

    class Config:
        from_attributes = True


# ── Dispatch (VRP) schemas ───────────────────────────────────────────────────

class DispatchOrderItem(BaseModel):
    order_id: str
    lat: float
    lon: float
    address_text: str

class DispatchRequest(BaseModel):
    orders: List[DispatchOrderItem]
    available_riders: Optional[int] = None

class ETABreakdown(BaseModel):
    order_id: str
    lat: float
    lon: float
    address_text: str
    base_transit_sec: float
    tier_factor: float
    tier_label: str
    tier_adjusted_sec: float
    sap_sec: int
    sap_breakdown: Dict[str, Any]
    zafi_sec: int
    zafi_breakdown: Dict[str, Any]
    total_eta_sec: float

class RiderRoute(BaseModel):
    rider_id: int
    store_id: str
    store_name: str
    store_lat: float
    store_lon: float
    route: List[ETABreakdown]
    total_cost_sec: float

class DispatchResponse(BaseModel):
    riders: List[RiderRoute]
    meta: Dict[str, Any]


# ── Customer ETA schemas ─────────────────────────────────────────────────────

class CustomerETARequest(BaseModel):
    lat: float
    lon: float

class CustomerETAResponse(BaseModel):
    nearest_store_id: Optional[str] = None
    nearest_store_name: Optional[str] = None
    distance_m: Optional[float] = None
    base_transit_sec: Optional[float] = None
    tier_factor: Optional[float] = None
    tier_label: Optional[str] = None
    estimated_time_sec: Optional[float] = None
    error: Optional[str] = None


# ── Inventory / GNN schemas ──────────────────────────────────────────────────

class TrainSyntheticResponse(BaseModel):
    status: str
    message: Optional[str] = None
    stores_processed: Optional[int] = None
    skus_simulated: Optional[int] = None
    days_simulated: Optional[int] = None
    error: Optional[str] = None
