"""
City-Tier Traffic Validator & Customer ETA Calculator
=====================================================
Adjusts travel times by a city-density scaling factor (Metro vs Tier-2/3)
and provides a customer-facing ETA endpoint that finds the nearest active
store and returns a realistic estimated delivery time.

ETA Model
---------
Total ETA = Preparation Time + Transit Time × Traffic Factor

Where:
  - Preparation Time = 3-5 minutes (picking + packing in store)
  - Transit Time = driving time from ORS or haversine estimate
  - Traffic Factor = city-tier multiplier for congestion

City-Tier Factors (multipliers on transit time)
-----------------------------------------------
Metro (Mumbai, Bangalore, Delhi, …)    : 1.3 – 1.6×  (heavy traffic)
Tier-1 (Pune, Hyderabad, Chennai, …)   : 1.1 – 1.3×  (moderate traffic)
Tier-2/3 (Sangli, Kolhapur, Nashik, …) : 1.0 – 1.1×  (light traffic)
Unknown                                 : 1.15× (conservative mid-range)
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import FulfillmentCentre

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/reverse"

# ---------------------------------------------------------------------------
# Preparation time (seconds) — time to pick, pack, and hand off to rider
# ---------------------------------------------------------------------------
PREP_TIME_SEC = 180  # 3 minutes base prep time

# ---------------------------------------------------------------------------
# City-tier configuration — traffic congestion multipliers
# Higher = more congested = longer delivery
# ---------------------------------------------------------------------------
CITY_TIERS: Dict[str, Dict] = {
    # --- Metros (heavy traffic) ---
    "mumbai":    {"tier": "metro",  "factor": 1.5},
    "delhi":     {"tier": "metro",  "factor": 1.6},
    "new delhi": {"tier": "metro",  "factor": 1.6},
    "bangalore": {"tier": "metro",  "factor": 1.4},
    "bengaluru": {"tier": "metro",  "factor": 1.4},
    "kolkata":   {"tier": "metro",  "factor": 1.45},
    "chennai":   {"tier": "metro",  "factor": 1.35},
    # --- Tier 1 (moderate traffic) ---
    "pune":      {"tier": "tier1",  "factor": 1.2},
    "hyderabad": {"tier": "tier1",  "factor": 1.25},
    "ahmedabad": {"tier": "tier1",  "factor": 1.2},
    "jaipur":    {"tier": "tier1",  "factor": 1.15},
    "lucknow":   {"tier": "tier1",  "factor": 1.15},
    # --- Tier 2/3 (lighter traffic, but worse roads) ---
    "sangli":    {"tier": "tier2",  "factor": 1.05},
    "kolhapur":  {"tier": "tier2",  "factor": 1.05},
    "nashik":    {"tier": "tier2",  "factor": 1.1},
    "nagpur":    {"tier": "tier2",  "factor": 1.1},
    "aurangabad":{"tier": "tier2",  "factor": 1.05},
    "solapur":   {"tier": "tier2",  "factor": 1.0},
    "indore":    {"tier": "tier2",  "factor": 1.1},
    "bhopal":    {"tier": "tier2",  "factor": 1.1},
}
DEFAULT_FACTOR = 1.15

# In-memory reverse-geocode cache  (coord → city_name)
_city_cache: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two WGS-84 points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _reverse_geocode_city(lat: float, lon: float) -> Optional[str]:
    """
    Reverse-geocode via ORS to identify the city name.
    Returns lowercase city name or None.
    Uses centralized rate limiter + cache.
    """
    cache_k = f"{round(lat, 3)}:{round(lon, 3)}"
    if cache_k in _city_cache:
        return _city_cache[cache_k]

    from services.ors_limiter import ors_reverse_geocode
    city = ors_reverse_geocode(lat, lon)
    if city:
        _city_cache[cache_k] = city
    return city


def get_tier_factor(lat: float, lon: float) -> Tuple[float, str]:
    """
    Determine the city-tier scaling factor for a coordinate.

    Returns
    -------
    (factor, tier_label)
    """
    city = _reverse_geocode_city(lat, lon)
    if city and city in CITY_TIERS:
        entry = CITY_TIERS[city]
        return entry["factor"], entry["tier"]

    # Partial match (e.g. "pune city" → "pune")
    if city:
        for key, entry in CITY_TIERS.items():
            if key in city or city in key:
                return entry["factor"], entry["tier"]

    return DEFAULT_FACTOR, "unknown"


def _ors_driving_time(
    src_lat: float, src_lon: float,
    dst_lat: float, dst_lon: float,
) -> Optional[float]:
    """
    Query ORS Directions API for driving time in seconds between two points.
    Uses centralized rate limiter + cache. Returns None on failure.
    
    Fallback: Haversine distance / 20 km/h average urban speed
    (20 km/h accounts for turns, signals, one-ways in Indian cities)
    """
    if not ORS_API_KEY:
        dist = _haversine(src_lat, src_lon, dst_lat, dst_lon)
        return dist / (20_000 / 3600)  # 20 km/h → seconds

    from services.ors_limiter import ors_directions
    result = ors_directions(src_lon, src_lat, dst_lon, dst_lat)
    if result and "duration" in result:
        return result["duration"]

    # Fallback to haversine
    dist = _haversine(src_lat, src_lon, dst_lat, dst_lon)
    return dist / (20_000 / 3600)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def customer_eta(
    lat: float,
    lon: float,
    db: AsyncSession,
) -> Dict:
    """
    Find the nearest active store and return a realistic tier-adjusted ETA.

    Total ETA = Prep Time + (Transit Time × Traffic Factor)
    
    Returns
    -------
    dict
        ``{nearest_store_id, nearest_store_name, distance_m,
           base_transit_sec, tier_factor, tier_label, 
           prep_time_sec, estimated_time_sec}``
    """
    # 1.  Fetch all stores
    result = await db.execute(select(FulfillmentCentre))
    centres = result.scalars().all()
    if not centres:
        return {"error": "No active stores configured."}

    # 2.  Find nearest by Haversine
    nearest = min(
        centres,
        key=lambda c: _haversine(lat, lon, c.lat, c.lon),
    )
    distance_m = _haversine(lat, lon, nearest.lat, nearest.lon)

    # 3.  Driving time via ORS (offloaded)
    loop = asyncio.get_running_loop()
    base_transit = await loop.run_in_executor(
        _executor,
        _ors_driving_time,
        nearest.lat, nearest.lon,
        lat, lon,
    )

    # 4.  Apply tier factor to transit portion only
    factor, tier_label = get_tier_factor(lat, lon)
    transit_adjusted = (base_transit or 0) * factor
    
    # 5.  Total ETA = prep + adjusted transit
    total_eta = PREP_TIME_SEC + transit_adjusted

    return {
        "nearest_store_id": nearest.id,
        "nearest_store_name": nearest.name,
        "distance_m": round(distance_m, 1),
        "base_transit_sec": round(base_transit, 1) if base_transit else 0,
        "tier_factor": factor,
        "tier_label": tier_label,
        "prep_time_sec": PREP_TIME_SEC,
        "estimated_time_sec": round(total_eta, 1),
    }
