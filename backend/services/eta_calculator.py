"""
City-Tier Traffic Validator & Customer ETA Calculator
=====================================================
Adjusts ORS travel times by a city-density scaling factor (Metro vs Tier-2/3)
and provides a customer-facing ETA endpoint that finds the nearest active
store and returns a tier-adjusted estimated delivery time.

City-Tier Factors
-----------------
Metro (Pune, Mumbai, Bangalore, Delhi, …)  : 1.0 – 1.2×
Tier-2/3 (Sangli, Kolhapur, Nashik, …)     : 0.5 – 0.7×
Unknown                                      : 0.8× (conservative mid-range)
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
# City-tier configuration (extensible)
# ---------------------------------------------------------------------------
CITY_TIERS: Dict[str, Dict] = {
    # --- Metros ---
    "pune":      {"tier": "metro",  "factor": 1.0},
    "mumbai":    {"tier": "metro",  "factor": 1.1},
    "bangalore": {"tier": "metro",  "factor": 1.15},
    "bengaluru": {"tier": "metro",  "factor": 1.15},
    "delhi":     {"tier": "metro",  "factor": 1.2},
    "new delhi": {"tier": "metro",  "factor": 1.2},
    "hyderabad": {"tier": "metro",  "factor": 1.05},
    "chennai":   {"tier": "metro",  "factor": 1.1},
    "kolkata":   {"tier": "metro",  "factor": 1.1},
    # --- Tier 2/3 ---
    "sangli":    {"tier": "tier2",  "factor": 0.6},
    "kolhapur":  {"tier": "tier2",  "factor": 0.65},
    "nashik":    {"tier": "tier2",  "factor": 0.7},
    "nagpur":    {"tier": "tier2",  "factor": 0.7},
    "aurangabad":{"tier": "tier2",  "factor": 0.65},
    "solapur":   {"tier": "tier2",  "factor": 0.6},
    "jaipur":    {"tier": "tier2",  "factor": 0.75},
    "lucknow":   {"tier": "tier2",  "factor": 0.7},
    "indore":    {"tier": "tier2",  "factor": 0.7},
    "bhopal":    {"tier": "tier2",  "factor": 0.65},
}
DEFAULT_FACTOR = 0.8

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
    """
    cache_k = f"{round(lat, 3)}:{round(lon, 3)}"
    if cache_k in _city_cache:
        return _city_cache[cache_k]

    if not ORS_API_KEY:
        return None

    try:
        resp = requests.get(
            ORS_GEOCODE_URL,
            params={"point.lat": lat, "point.lon": lon, "size": 1},
            headers={"Authorization": ORS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            props = features[0].get("properties", {})
            city = (
                props.get("locality")
                or props.get("county")
                or props.get("region")
                or ""
            ).lower().strip()
            _city_cache[cache_k] = city
            return city
    except Exception as exc:
        logger.warning("Reverse geocode failed: %s", exc)

    return None


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
    Returns None on failure.
    """
    if not ORS_API_KEY:
        # Estimate from haversine: assume 25 km/h average urban speed
        dist = _haversine(src_lat, src_lon, dst_lat, dst_lon)
        return dist / (25_000 / 3600)  # seconds

    try:
        resp = requests.post(
            ORS_DIRECTIONS_URL,
            json={
                "coordinates": [
                    [src_lon, src_lat],
                    [dst_lon, dst_lat],
                ],
            },
            headers={
                "Authorization": ORS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        routes = resp.json().get("routes", [])
        if routes:
            return routes[0]["summary"]["duration"]
    except Exception as exc:
        logger.warning("ORS directions failed: %s", exc)

    # Fallback
    dist = _haversine(src_lat, src_lon, dst_lat, dst_lon)
    return dist / (25_000 / 3600)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def customer_eta(
    lat: float,
    lon: float,
    db: AsyncSession,
) -> Dict:
    """
    Find the nearest active store and return a tier-adjusted ETA.

    Returns
    -------
    dict
        ``{nearest_store_id, nearest_store_name, distance_m,
           base_transit_sec, tier_factor, tier_label, estimated_time_sec}``
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

    # 4.  Apply tier factor
    factor, tier_label = get_tier_factor(lat, lon)
    adjusted = base_transit * factor if base_transit else 0

    return {
        "nearest_store_id": nearest.id,
        "nearest_store_name": nearest.name,
        "distance_m": round(distance_m, 1),
        "base_transit_sec": round(base_transit, 1) if base_transit else 0,
        "tier_factor": factor,
        "tier_label": tier_label,
        "estimated_time_sec": round(adjusted, 1),
    }
