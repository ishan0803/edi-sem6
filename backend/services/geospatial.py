import os
import json
import logging
import asyncio
from typing import List, Dict, Optional
import concurrent.futures

import networkx as nx
import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point, shape

ox.settings.use_cache = True
ox.settings.cache_folder = '/tmp/osmnx_cache'
ox.settings.log_console = True
from shapely.ops import unary_union
import requests
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

_local_cache = {}
_graph_cache = {}

DISTANCE_BANDS = {
    "green": 2_000,
    "blue": 5_000,
    "red": 10_000,
}
TIME_BANDS_MIN = {
    "green": 10,
    "blue": 15,
    "red": 20,
}

ORS_INDIA_BASE_CORRECTION = 0.55
ORS_ISOCHRONE_URL = "https://api.openrouteservice.org/v2/isochrones/driving-car"
BUFFER_DIST_M = 10_500
NETWORK_TYPE = "drive"
ORS_API_KEY = os.getenv("ORS_API_KEY")

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

async def clear_cache(db=None, centre_id: str = None):
    """Clear in-memory cache. If db provided, also clear persisted coverage."""
    _local_cache.clear()
    _graph_cache.clear()
    if db:
        from sqlalchemy import delete as sa_delete
        from models import CoverageCache
        if centre_id:
            await db.execute(sa_delete(CoverageCache).where(CoverageCache.centre_id == centre_id))
        else:
            await db.execute(sa_delete(CoverageCache))
        await db.commit()

def _get_local_datetime(lat: float, lon: float) -> datetime:
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lat=lat, lng=lon) or "UTC"
    tz = pytz.timezone(tz_name)
    return datetime.now(tz)

def traffic_multiplier_local(lat: float, lon: float) -> float:
    local_dt = _get_local_datetime(lat, lon)
    hour = local_dt.hour
    is_weekend = local_dt.weekday() >= 5

    peak_hours = {8, 9, 17, 18}
    shoulder_hours = {7, 10, 11, 16, 19, 20}

    if is_weekend:
        base = 0.70 if hour in peak_hours else (0.85 if hour in shoulder_hours else 0.95)
    else:
        base = 0.50 if hour in peak_hours else (0.70 if hour in shoulder_hours else 0.90)
    return base

# OSMNX Graph processing
def fetch_graph(lat: float, lon: float) -> nx.MultiDiGraph:
    key = (round(lat, 5), round(lon, 5))
    if key in _graph_cache:
        logger.info(f"Graph cache hit for {key}")
        return _graph_cache[key]
    logger.info(f"Graph cache miss for {key}, downloading from Overpass...")
    G = ox.graph_from_point((lat, lon), dist=BUFFER_DIST_M, network_type=NETWORK_TYPE)
    projected = ox.project_graph(G)
    _graph_cache[key] = projected
    return projected

def nearest_node(G: nx.MultiDiGraph, lat: float, lon: float) -> int:
    gdf_nodes = ox.graph_to_gdfs(G, edges=False)
    point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(gdf_nodes.crs).iloc[0]
    return ox.nearest_nodes(G, point.x, point.y)

def edges_to_buffered_polygon_wgs84(G: nx.MultiDiGraph, reachable_nodes: set, buffer_m: float = 35):
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)
    mask = (
        gdf_edges.index.get_level_values("u").isin(reachable_nodes)
        & gdf_edges.index.get_level_values("v").isin(reachable_nodes)
    )
    reachable_edges = gdf_edges[mask]
    if reachable_edges.empty:
        node_geoms = gdf_nodes.loc[list(reachable_nodes), "geometry"]
        union = unary_union([g.buffer(buffer_m) for g in node_geoms])
    else:
        buffered = reachable_edges.geometry.buffer(buffer_m)
        union = unary_union(buffered)
    return gpd.GeoSeries([union], crs=gdf_edges.crs).to_crs("EPSG:4326").iloc[0]

def build_distance_polygons(lat: float, lon: float) -> dict:
    G = fetch_graph(lat, lon)
    source_node = nearest_node(G, lat, lon)
    polygons = {}
    for color, dist_m in DISTANCE_BANDS.items():
        lengths = nx.single_source_dijkstra_path_length(G, source_node, cutoff=dist_m, weight="length")
        reachable = set(lengths.keys())
        if not reachable: continue
        poly = edges_to_buffered_polygon_wgs84(G, reachable, buffer_m=35)
        if poly and not poly.is_empty:
            polygons[color] = poly
    return polygons

def build_time_polygons_ors(lat: float, lon: float, api_key: str, tod_multiplier: float) -> dict:
    from services.ors_limiter import ors_isochrones
    MAX_EFFECTIVE_SEC = {"green": 300, "blue": 450, "red": 600}
    scaled = {}
    for color, minutes in TIME_BANDS_MIN.items():
        base_sec = minutes * 60
        effective_sec = base_sec * ORS_INDIA_BASE_CORRECTION * tod_multiplier
        scaled[color] = int(max(60, min(effective_sec, MAX_EFFECTIVE_SEC[color])))

    unique_ranges = sorted(set(scaled.values()), reverse=True)
    raw = ors_isochrones(lon, lat, unique_ranges, api_key)
    if not raw:
        return {}

    polygons = {}
    for color, sec in scaled.items():
        if raw.keys():
            best_key = min(raw.keys(), key=lambda k: abs(k - sec))
            poly = raw[best_key]
            # If it came from cache it's a dict (GeoJSON), convert to shapely
            if isinstance(poly, dict):
                poly = shape(poly)
            polygons[color] = poly
    return polygons

def compute_unique_coverage(centres: List[dict], polygons_by_centre: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    unique = {c["id"]: {} for c in centres}
    for centre in centres:
        cid = centre["id"]
        if cid not in polygons_by_centre: continue
        for band, polygon in polygons_by_centre[cid].items():
            unique_polygon = polygon
            other_polygons = []
            for other in centres:
                if other["id"] == cid or other["id"] not in polygons_by_centre or band not in polygons_by_centre[other["id"]]:
                    continue
                other_polygons.append(polygons_by_centre[other["id"]][band])
            
            if other_polygons:
                try:
                    union_others = unary_union(other_polygons)
                    unique_polygon = unique_polygon.difference(union_others)
                except Exception:
                    pass
            if unique_polygon and not unique_polygon.is_empty:
                unique[cid][band] = unique_polygon
    return unique

async def get_or_compute_polygons(centre: dict, mode: str, db=None) -> dict:
    """Load polygons from memory cache → DB cache → fresh compute."""
    cid = centre["id"]
    cache_key = f"poly:{cid}:{mode}"

    # 1. Check in-memory cache
    cached = _local_cache.get(cache_key)
    if cached:
        return {k: shape(v) for k, v in cached.items()}

    # 2. Check DB cache
    if db:
        from sqlalchemy import select as sa_select
        from models import CoverageCache
        result = await db.execute(
            sa_select(CoverageCache).where(
                CoverageCache.centre_id == cid,
                CoverageCache.mode == mode,
            )
        )
        db_rows = result.scalars().all()
        if db_rows:
            logger.info("Coverage DB cache HIT for %s/%s (%d bands)", cid, mode, len(db_rows))
            polys = {}
            cache_data = {}
            for row in db_rows:
                geo = json.loads(row.geojson)
                polys[row.band] = shape(geo)
                cache_data[row.band] = geo
            _local_cache[cache_key] = cache_data
            return polys

    # 3. Fresh compute
    logger.info("Coverage MISS for %s/%s — computing fresh", cid, mode)
    loop = asyncio.get_event_loop()
    if mode == "distance":
        polys = await loop.run_in_executor(executor, build_distance_polygons, centre["lat"], centre["lon"])
    else:
        if not ORS_API_KEY:
            return {}
        mult = traffic_multiplier_local(centre["lat"], centre["lon"])
        polys = await loop.run_in_executor(executor, build_time_polygons_ors, centre["lat"], centre["lon"], ORS_API_KEY, mult)

    # 4. Persist to memory + DB
    if polys:
        cache_data = {k: v.__geo_interface__ for k, v in polys.items()}
        _local_cache[cache_key] = cache_data
        if db:
            from models import CoverageCache
            for band, geo in cache_data.items():
                db.add(CoverageCache(
                    centre_id=cid, mode=mode, band=band,
                    geojson=json.dumps(geo),
                ))
            await db.commit()
            logger.info("Coverage PERSISTED for %s/%s (%d bands)", cid, mode, len(cache_data))
    return polys

async def compute_coverages(centres: List[dict], db=None):
    dist_polygons = {}
    time_polygons = {}

    for i, c in enumerate(centres):
        cdist = await get_or_compute_polygons(c, "distance", db)
        ctime = await get_or_compute_polygons(c, "time", db)
        if cdist: dist_polygons[c["id"]] = cdist
        if ctime: time_polygons[c["id"]] = ctime
        # Rate-limit: wait between centres to avoid ORS throttling
        # (only needed when actually hitting ORS — skip if all cached)
        if i < len(centres) - 1 and (not cdist or not ctime):
            await asyncio.sleep(3.5)

    loop = asyncio.get_event_loop()
    unique_dist = await loop.run_in_executor(executor, compute_unique_coverage, centres, dist_polygons)
    unique_time = await loop.run_in_executor(executor, compute_unique_coverage, centres, time_polygons)

    def serialize(unique_polys):
        res = {}
        for cid, bands in unique_polys.items():
            res[cid] = {b: poly.__geo_interface__ for b, poly in bands.items()}
        return res

    return {
        "distance": serialize(unique_dist),
        "time": serialize(unique_time)
    }
