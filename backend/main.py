from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
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

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down connections...")

# Include feature routers
app.include_router(routers.centres.router, prefix="/api/centres", tags=["Centres"])
app.include_router(routers.dispatch.router, prefix="/api", tags=["Dispatch & Logistics"])

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

