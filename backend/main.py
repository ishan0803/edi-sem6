from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models  # Ensure all models are registered with Base.metadata
import routers.centres
import routers.dispatch
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Quick Commerce Logistics Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    logger.info("Starting up FastAPI and syncing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed demo data (idempotent — only runs if DB is empty)
    from database import AsyncSessionLocal
    from services.seed_data import seed_demo_data
    async with AsyncSessionLocal() as db:
        await seed_demo_data(db)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down connections...")

# Include feature routers
app.include_router(routers.centres.router, prefix="/api/centres", tags=["Centres"])
app.include_router(routers.dispatch.router, prefix="/api", tags=["Dispatch & Logistics"])

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/ors-stats")
async def ors_stats():
    """Monitor ORS API usage and cache stats."""
    from services.ors_limiter import get_cache_stats
    return get_cache_stats()
