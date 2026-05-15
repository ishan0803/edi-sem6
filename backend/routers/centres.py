from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any
import uuid

from database import get_db
from models import FulfillmentCentre
from schemas import CentreCreate, CentreResponse
from services.geospatial import compute_coverages, clear_cache

router = APIRouter()

@router.get("/", response_model=List[CentreResponse])
async def get_centres(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FulfillmentCentre))
    return result.scalars().all()

@router.post("/", response_model=CentreResponse)
async def add_centre(centre: CentreCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FulfillmentCentre))
    existing = result.scalars().all()
    color_idx = len(existing) % 3
    
    new_id = str(uuid.uuid4())[:8]
    new_centre = FulfillmentCentre(
        id=new_id,
        name=centre.name,
        lat=centre.lat,
        lon=centre.lon,
        colour_idx=color_idx
    )
    db.add(new_centre)
    await db.commit()
    await db.refresh(new_centre)
    
    # Auto-seed inventory for new hub (if demo SKUs exist)
    from services.seed_data import seed_inventory_for_hub
    await seed_inventory_for_hub(new_id, db)
    
    # Clear all coverage cache (unique coverage depends on all centres)
    await clear_cache(db)
    return new_centre

@router.delete("/{centre_id}")
async def delete_centre(centre_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FulfillmentCentre).where(FulfillmentCentre.id == centre_id))
    centre = result.scalars().first()
    if not centre:
        raise HTTPException(status_code=404, detail="Centre not found")
    
    await db.delete(centre)
    await db.commit()
    
    # Clear all coverage cache (unique coverage depends on all centres)
    await clear_cache(db)
    return {"status": "deleted"}

@router.get("/coverage", response_model=Dict[str, Any])
async def get_coverage(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FulfillmentCentre))
    centres = result.scalars().all()
    
    if not centres:
        return {"distance": {}, "time": {}}
        
    c_dicts = [{"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon} for c in centres]
    coverage = await compute_coverages(c_dicts, db)
    return coverage
