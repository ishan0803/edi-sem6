"""
Z-Axis Friction Index (ZAFI) Service
=====================================
Queries OpenStreetMap building data via OSMnx to estimate vertical-access
delays (security gates, elevator waits) at the delivery destination.

Results are aggressively cached in Redis using a geohash key derived from
the destination coordinates so that repeat queries for nearby addresses
avoid hitting the Overpass API.

Penalty Matrix
--------------
Building Type    | Security Delay
-----------------+---------------
apartment/residential | 120 s
commercial/office     |  90 s
house                 |  30 s
other / unknown       |  60 s

Elevator wait: ``levels × 30 s`` (capped at 10 levels → max 300 s)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# ---------------------------------------------------------------------------
# Redis setup (optional — degrades gracefully if unavailable)
# ---------------------------------------------------------------------------
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as _redis_mod
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = _redis_mod.from_url(url, decode_responses=True)
            _redis_client.ping()
            logger.info("ZAFI Redis cache connected at %s", url)
        except Exception as exc:
            logger.warning("ZAFI Redis unavailable (%s) — running without cache.", exc)
            _redis_client = "UNAVAILABLE"
    return _redis_client


def _cache_key(lat: float, lon: float) -> str:
    """Return a Redis key based on a geohash of the coordinates (precision 7 ≈ ±76 m)."""
    try:
        import geohash2
        gh = geohash2.encode(lat, lon, precision=7)
    except ImportError:
        gh = f"{round(lat, 4)}:{round(lon, 4)}"
    return f"zafi:{gh}"


# ---------------------------------------------------------------------------
# Security delay lookup
# ---------------------------------------------------------------------------
_SECURITY_DELAYS: Dict[str, int] = {
    "apartments": 120,
    "apartment": 120,
    "residential": 120,
    "commercial": 90,
    "office": 90,
    "retail": 90,
    "house": 30,
    "detached": 30,
    "bungalow": 30,
    "terrace": 30,
}
_DEFAULT_SECURITY = 60
_MAX_LEVELS = 10
_SECONDS_PER_LEVEL = 30


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class ZAFIResult:
    penalty_seconds: int
    building_type: Optional[str]
    levels: int
    security_delay: int
    elevator_delay: int

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core OSMnx query (CPU + network bound, run in thread pool)
# ---------------------------------------------------------------------------
def _query_building(lat: float, lon: float) -> ZAFIResult:
    """
    Synchronous call to OSMnx → Overpass API.  Always wrapped by
    ``run_in_executor`` from the async surface.
    """
    try:
        import osmnx as ox

        gdf = ox.features_from_point(
            (lat, lon),
            tags={"building": True},
            dist=50,
        )

        if gdf.empty:
            return ZAFIResult(0, None, 0, 0, 0)

        # Take the nearest building row
        row = gdf.iloc[0]

        # --- Building type ---
        btype_raw = str(row.get("building", "yes")).lower().strip()
        btype = btype_raw if btype_raw != "yes" else None

        # --- Levels ---
        levels_raw = row.get("building:levels", 0)
        try:
            levels = min(int(float(str(levels_raw))), _MAX_LEVELS)
        except (ValueError, TypeError):
            levels = 0

        # --- Penalties ---
        security = _SECURITY_DELAYS.get(btype, _DEFAULT_SECURITY) if btype else 0
        elevator = levels * _SECONDS_PER_LEVEL

        return ZAFIResult(
            penalty_seconds=security + elevator,
            building_type=btype,
            levels=levels,
            security_delay=security,
            elevator_delay=elevator,
        )

    except Exception as exc:
        logger.warning("ZAFI OSMnx query failed for (%.5f, %.5f): %s", lat, lon, exc)
        return ZAFIResult(0, None, 0, 0, 0)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def compute_zafi(lat: float, lon: float) -> Dict:
    """
    Compute the Z-Axis Friction Index for the given coordinates.

    Checks Redis cache first; on a miss, queries Overpass via OSMnx and
    stores the result for 24 hours.

    Returns
    -------
    dict
        ``{penalty_seconds, building_type, levels, security_delay, elevator_delay}``
    """
    cache_k = _cache_key(lat, lon)
    rds = _get_redis()

    # --- Cache hit ---
    if rds and rds != "UNAVAILABLE":
        try:
            cached = rds.get(cache_k)
            if cached:
                logger.debug("ZAFI cache hit for %s", cache_k)
                return json.loads(cached)
        except Exception:
            pass

    # --- Cache miss → query OSMnx in thread pool ---
    loop = asyncio.get_running_loop()
    result: ZAFIResult = await loop.run_in_executor(_executor, _query_building, lat, lon)
    payload = result.to_dict()

    # --- Store in cache ---
    if rds and rds != "UNAVAILABLE":
        try:
            rds.setex(cache_k, 86_400, json.dumps(payload))  # 24 h TTL
        except Exception:
            pass

    return payload
