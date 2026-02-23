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

async def clear_cache():
    _local_cache.clear()

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
    G = ox.graph_from_point((lat, lon), dist=BUFFER_DIST_M, network_type=NETWORK_TYPE)
    return ox.project_graph(G)

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
    MAX_EFFECTIVE_SEC = {"green": 300, "blue": 450, "red": 600}
    scaled = {}
    for color, minutes in TIME_BANDS_MIN.items():
        base_sec = minutes * 60
        effective_sec = base_sec * ORS_INDIA_BASE_CORRECTION * tod_multiplier
        scaled[color] = int(max(60, min(effective_sec, MAX_EFFECTIVE_SEC[color])))

    unique_ranges = sorted(set(scaled.values()), reverse=True)
    payload = {
        "locations": [[lon, lat]],
        "range": unique_ranges,
        "range_type": "time",
        "smoothing": 0.1,
        "area_units": "m",
        "units": "m",
    }
    resp = requests.post(
        ORS_ISOCHRONE_URL,
        json=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    raw = {feat["properties"]["value"]: shape(feat["geometry"]) for feat in resp.json().get("features", [])}
    
    polygons = {}
    for color, sec in scaled.items():
        if raw.keys():
            best_key = min(raw.keys(), key=lambda k: abs(k - sec))
            polygons[color] = raw[best_key]
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

async def get_or_compute_polygons(centre: dict, mode: str) -> dict:
    cid = centre["id"]
    cache_key = f"poly:{cid}:{mode}"
    cached = _local_cache.get(cache_key)
    if cached:
        return {k: shape(v) for k, v in cached.items()}
    
    loop = asyncio.get_event_loop()
    if mode == "distance":
        polys = await loop.run_in_executor(executor, build_distance_polygons, centre["lat"], centre["lon"])
    else:
        if not ORS_API_KEY:
            return {}
        mult = traffic_multiplier_local(centre["lat"], centre["lon"])
        polys = await loop.run_in_executor(executor, build_time_polygons_ors, centre["lat"], centre["lon"], ORS_API_KEY, mult)
    
    if polys:
        cache_data = {k: v.__geo_interface__ for k, v in polys.items()}
        _local_cache[cache_key] = cache_data
    return polys

async def compute_coverages(centres: List[dict]):
    dist_polygons = {}
    time_polygons = {}
    
    for c in centres:
        cdist = await get_or_compute_polygons(c, "distance")
        ctime = await get_or_compute_polygons(c, "time")
        if cdist: dist_polygons[c["id"]] = cdist
        if ctime: time_polygons[c["id"]] = ctime
        
    loop = asyncio.get_event_loop()
    unique_dist = await loop.run_in_executor(executor, compute_unique_coverage, centres, dist_polygons)
    unique_time = await loop.run_in_executor(executor, compute_unique_coverage, centres, time_polygons)
    
    def serialize(unique_polys):
        res = {}
        for cid, bands in unique_polys.items():
            res[cid] = {b: poly.__geo_interface__ for b, poly in bands.items()}
        return res
        
    # Generate aggregate bounding boxes for the frontend to center the map easily
    return {
        "distance": serialize(unique_dist),
        "time": serialize(unique_time)
    }
