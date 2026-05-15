"""
ORS Rate Limiter & Response Cache
==================================
Centralized module that:
  1. Enforces per-minute rate limits matching the ORS free tier
  2. Caches responses in-memory with configurable TTL to avoid repeat calls
  3. Adds configurable delay between consecutive API calls

All ORS calls across the app should go through this module.

ORS Free Tier Limits (daily / per minute):
  Directions:     2,000 / 40
  Isochrones:       500 / 20
  Matrix:           500 / 40
  Geocoding:      1,000 / 100
  Reverse geocode:1,000 / 100
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

ORS_API_KEY = os.getenv("ORS_API_KEY", "")
_executor = ThreadPoolExecutor(max_workers=2)

# ── Per-minute rate limits (conservative: 80% of actual to leave headroom) ───
RATE_LIMITS: Dict[str, int] = {
    "directions": 32,       # actual 40/min
    "isochrones": 16,       # actual 20/min
    "matrix": 32,           # actual 40/min
    "geocode": 80,          # actual 100/min
    "reverse_geocode": 80,  # actual 100/min
}

# Minimum delay between consecutive calls to same endpoint (seconds)
MIN_CALL_GAP: Dict[str, float] = {
    "directions": 1.6,      # ~37/min max
    "isochrones": 3.2,      # ~18/min max
    "matrix": 1.6,          # ~37/min max
    "geocode": 0.8,         # ~75/min max
    "reverse_geocode": 0.8, # ~75/min max
}

# Cache TTL in seconds (1 hour default — ORS data doesn't change often)
CACHE_TTL = int(os.getenv("ORS_CACHE_TTL", "3600"))

# ── Internal state ───────────────────────────────────────────────────────────
_call_timestamps: Dict[str, list] = defaultdict(list)
_last_call_time: Dict[str, float] = defaultdict(float)
_response_cache: Dict[str, tuple] = {}   # key → (response_data, cached_at)
_lock = asyncio.Lock() if True else None  # placeholder, real lock created lazily
_sync_locks: Dict[str, float] = defaultdict(float)


def _cache_key(endpoint: str, payload: Any) -> str:
    """Generate a deterministic cache key from endpoint + request payload."""
    raw = json.dumps({"ep": endpoint, "p": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _is_cached(key: str) -> Optional[Any]:
    """Return cached response if fresh, else None."""
    if key in _response_cache:
        data, cached_at = _response_cache[key]
        if time.time() - cached_at < CACHE_TTL:
            logger.debug("ORS cache HIT: %s", key[:12])
            return data
        else:
            del _response_cache[key]
    return None


def _store_cache(key: str, data: Any):
    """Store response in cache."""
    _response_cache[key] = (data, time.time())
    # Evict old entries if cache grows too large (>500 entries)
    if len(_response_cache) > 500:
        oldest_key = min(_response_cache, key=lambda k: _response_cache[k][1])
        del _response_cache[oldest_key]


def _enforce_rate_limit_sync(endpoint: str):
    """
    Synchronous rate limiter — sleeps if needed to stay within limits.
    Called from within ThreadPoolExecutor workers.
    """
    now = time.time()

    # 1. Enforce minimum gap between calls
    gap = MIN_CALL_GAP.get(endpoint, 1.5)
    last = _sync_locks[endpoint]
    elapsed = now - last
    if elapsed < gap:
        wait = gap - elapsed
        logger.info("ORS rate limit: waiting %.1fs before %s call", wait, endpoint)
        time.sleep(wait)

    # 2. Enforce per-minute window
    limit = RATE_LIMITS.get(endpoint, 30)
    window = _call_timestamps[endpoint]
    cutoff = time.time() - 60
    _call_timestamps[endpoint] = [t for t in window if t > cutoff]

    if len(_call_timestamps[endpoint]) >= limit:
        oldest = min(_call_timestamps[endpoint])
        wait = 60 - (time.time() - oldest) + 0.5
        if wait > 0:
            logger.warning("ORS rate limit: %s at %d/%d calls/min, sleeping %.1fs",
                         endpoint, len(_call_timestamps[endpoint]), limit, wait)
            time.sleep(wait)

    _call_timestamps[endpoint].append(time.time())
    _sync_locks[endpoint] = time.time()


# ── Public API: rate-limited, cached ORS calls ───────────────────────────────

def ors_directions(src_lon: float, src_lat: float, dst_lon: float, dst_lat: float) -> Optional[Dict]:
    """
    Rate-limited, cached ORS Directions call.
    Returns the first route's summary or None.
    """
    if not ORS_API_KEY:
        return None

    payload = {"coordinates": [[src_lon, src_lat], [dst_lon, dst_lat]]}
    ck = _cache_key("directions", payload)
    cached = _is_cached(ck)
    if cached is not None:
        return cached

    _enforce_rate_limit_sync("directions")
    try:
        resp = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            json=payload,
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes", [])
        result = routes[0]["summary"] if routes else None
        _store_cache(ck, result)
        return result
    except Exception as exc:
        logger.warning("ORS directions failed: %s", exc)
        return None


def ors_isochrones(lon: float, lat: float, ranges: list, api_key: str = "") -> Optional[Dict]:
    """
    Rate-limited, cached ORS Isochrones call.
    Returns dict of {range_value: geojson_geometry}.
    """
    key = api_key or ORS_API_KEY
    if not key:
        return None

    payload = {
        "locations": [[lon, lat]],
        "range": sorted(set(ranges), reverse=True),
        "range_type": "time",
        "smoothing": 0.1,
        "area_units": "m",
        "units": "m",
    }
    ck = _cache_key("isochrones", payload)
    cached = _is_cached(ck)
    if cached is not None:
        return cached

    _enforce_rate_limit_sync("isochrones")
    try:
        resp = requests.post(
            "https://api.openrouteservice.org/v2/isochrones/driving-car",
            json=payload,
            headers={"Authorization": key, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        from shapely.geometry import shape
        result = {feat["properties"]["value"]: shape(feat["geometry"])
                  for feat in resp.json().get("features", [])}
        # Can't cache shapely objects directly, cache the raw features
        raw_result = {feat["properties"]["value"]: feat["geometry"]
                      for feat in resp.json().get("features", [])}
        _store_cache(ck, raw_result)
        return result
    except Exception as exc:
        logger.warning("ORS isochrones failed: %s", exc)
        return None


def ors_matrix(coordinates: list) -> Optional[list]:
    """
    Rate-limited, cached ORS Matrix call.
    Returns duration matrix or None.
    """
    if not ORS_API_KEY or len(coordinates) < 2:
        return None

    payload = {"locations": coordinates, "metrics": ["duration"], "units": "m"}
    ck = _cache_key("matrix", payload)
    cached = _is_cached(ck)
    if cached is not None:
        return cached

    _enforce_rate_limit_sync("matrix")
    try:
        resp = requests.post(
            "https://api.openrouteservice.org/v2/matrix/driving-car",
            json=payload,
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json().get("durations")
        _store_cache(ck, result)
        return result
    except Exception as exc:
        logger.warning("ORS matrix failed: %s", exc)
        return None


def ors_reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Rate-limited, cached ORS reverse geocode.
    Returns lowercase city name or None.
    """
    if not ORS_API_KEY:
        return None

    params = {"point.lat": lat, "point.lon": lon, "size": 1}
    ck = _cache_key("reverse_geocode", params)
    cached = _is_cached(ck)
    if cached is not None:
        return cached

    _enforce_rate_limit_sync("reverse_geocode")
    try:
        resp = requests.get(
            "https://api.openrouteservice.org/geocode/reverse",
            params=params,
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
            _store_cache(ck, city)
            return city
    except Exception as exc:
        logger.warning("ORS reverse geocode failed: %s", exc)

    return None


def get_cache_stats() -> Dict:
    """Return cache statistics for monitoring."""
    return {
        "cached_responses": len(_response_cache),
        "call_counts_last_minute": {
            ep: len([t for t in ts if t > time.time() - 60])
            for ep, ts in _call_timestamps.items()
        },
    }
