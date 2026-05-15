"""
Z-Axis Friction Index (ZAFI) Service — Transformer Edition
==========================================================
Extracts vertical-access penalties (floor level, building type, security gates)
directly from the delivery address text using a transformer QA model +
regex patterns. No external API calls needed.

Architecture
------------
1. Regex layer  — fast, reliable extraction of floor/level numbers
2. Transformer layer — HuggingFace QA pipeline (distilbert) for building type
                       and floor extraction when regex misses
3. Keyword layer — deterministic building type from known keywords

Penalty Matrix
--------------
Building Type    | Security Delay
-----------------+---------------
apartment/tower  | 120 s
commercial/office|  90 s
house/villa      |  30 s
other / unknown  |  60 s

Elevator wait: ``floor × 25 s`` (capped at 15 floors → max 375 s)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# ---------------------------------------------------------------------------
# Lazy-loaded transformer model
# ---------------------------------------------------------------------------
_qa_pipeline = None
_qa_load_attempted = False


def _get_qa_pipeline():
    """Lazy-load the HuggingFace QA pipeline (distilbert — ~250 MB)."""
    global _qa_pipeline, _qa_load_attempted
    if _qa_load_attempted:
        return _qa_pipeline
    _qa_load_attempted = True
    try:
        from transformers import pipeline
        _qa_pipeline = pipeline(
            "question-answering",
            model="distilbert/distilbert-base-cased-distilled-squad",
            device=-1,  # CPU only
        )
        logger.info("ZAFI transformer QA pipeline loaded (distilbert-squad)")
    except Exception as exc:
        logger.warning("ZAFI transformer unavailable (%s) — using regex-only mode", exc)
        _qa_pipeline = None
    return _qa_pipeline


# ---------------------------------------------------------------------------
# In-memory cache (address hash → result)
# ---------------------------------------------------------------------------
_zafi_cache: Dict[str, Dict] = {}


# ---------------------------------------------------------------------------
# Security delay lookup
# ---------------------------------------------------------------------------
_SECURITY_DELAYS: Dict[str, int] = {
    "apartment": 120, "apartments": 120, "tower": 120, "highrise": 120,
    "residential": 120, "complex": 120, "society": 100,
    "commercial": 90, "office": 90, "mall": 90, "plaza": 90,
    "retail": 90, "corporate": 90,
    "house": 30, "villa": 30, "bungalow": 30, "independent": 30,
    "cottage": 30, "row house": 30,
    "gated": 100, "gated community": 100,
}
_DEFAULT_SECURITY = 45
_MAX_FLOORS = 15
_SECONDS_PER_FLOOR = 25  # elevator wait + walk per floor


# ---------------------------------------------------------------------------
# Regex patterns for floor/level extraction
# ---------------------------------------------------------------------------
_RE_FLOOR_PATTERNS = [
    # "3rd floor", "floor 5", "5th flr", "Floor #3"
    re.compile(
        r"(?:floor|flr|flr\.?)\s*#?\s*(\d{1,3})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3})(?:st|nd|rd|th)\s*(?:floor|flr|flr\.?|storey|story)",
        re.IGNORECASE,
    ),
    # "level 5", "L3", "Level-2"
    re.compile(
        r"(?:level|lvl|lv)\s*[-#]?\s*(\d{1,3})",
        re.IGNORECASE,
    ),
    # Flat/unit with implied floor: "Flat 302" → floor 3, "apt 1504" → floor 15
    re.compile(
        r"(?:flat|apt|unit|room|no\.?)\s*[-#]?\s*(\d{2,4})\b",
        re.IGNORECASE,
    ),
    # Standalone large number that could be flat: "302," or "1504,"
    re.compile(
        r"\b(\d{3,4})\s*[,/]",
    ),
]

# Building type keywords
_BUILDING_TYPE_KEYWORDS = {
    "apartment": ["apartment", "flat", "apt", "residential complex", "housing society",
                   "society", "bhk", "1bhk", "2bhk", "3bhk"],
    "tower": ["tower", "heights", "highrise", "high-rise", "skyscraper", "floors"],
    "commercial": ["office", "commercial", "business park", "tech park", "corporate",
                    "co-working", "coworking", "workspace"],
    "mall": ["mall", "plaza", "shopping", "retail", "market complex"],
    "house": ["house", "villa", "bungalow", "independent", "row house", "rowhouse",
              "cottage", "duplex", "penthouse ground"],
    "gated": ["gated community", "gated", "township", "enclave"],
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class ZAFIResult:
    penalty_seconds: int
    building_type: Optional[str]
    floor_extracted: int
    security_delay: int
    elevator_delay: int
    extraction_method: str  # "regex", "transformer", "keyword", "none"

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Floor extraction from flat/unit number
# ---------------------------------------------------------------------------
def _floor_from_flat_number(flat_num: int) -> int:
    """Infer floor from Indian flat numbering: 302 → floor 3, 1504 → floor 15."""
    if flat_num < 100:
        return 0  # ground floor or unit number
    s = str(flat_num)
    if len(s) == 3:
        return int(s[0])      # 302 → 3
    elif len(s) == 4:
        return int(s[:2])     # 1504 → 15
    return 0


def _extract_floor_regex(text: str) -> Tuple[int, bool]:
    """
    Extract floor number using regex patterns.
    Returns (floor_number, is_direct) where is_direct means the match was
    explicitly a floor reference (not inferred from flat number).
    """
    # Try direct floor patterns first (patterns 0-2)
    for i, pat in enumerate(_RE_FLOOR_PATTERNS[:3]):
        m = pat.search(text)
        if m:
            floor = min(int(m.group(1)), _MAX_FLOORS)
            return floor, True

    # Try flat-number-based inference (patterns 3-4)
    for pat in _RE_FLOOR_PATTERNS[3:]:
        m = pat.search(text)
        if m:
            flat_num = int(m.group(1))
            floor = _floor_from_flat_number(flat_num)
            if floor > 0:
                return min(floor, _MAX_FLOORS), False

    return 0, False


def _extract_building_type_keywords(text: str) -> Optional[str]:
    """Extract building type using keyword matching."""
    text_lower = text.lower()
    for btype, keywords in _BUILDING_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return btype
    return None


def _extract_with_transformer(text: str) -> Tuple[int, Optional[str]]:
    """
    Use the transformer QA pipeline to extract floor and building type
    from address text. Returns (floor, building_type).
    """
    qa = _get_qa_pipeline()
    if qa is None:
        return 0, None

    floor = 0
    btype = None

    try:
        # Question 1: What floor?
        floor_answer = qa(
            question="What floor or level number is the delivery on?",
            context=text,
        )
        if floor_answer and floor_answer.get("score", 0) > 0.15:
            # Extract digits from answer
            digits = re.findall(r"\d+", floor_answer["answer"])
            if digits:
                floor = min(int(digits[0]), _MAX_FLOORS)
                logger.debug("Transformer floor: %d (score=%.2f, answer='%s')",
                           floor, floor_answer["score"], floor_answer["answer"])

        # Question 2: What type of building?
        type_answer = qa(
            question="What type of building is this address in?",
            context=text,
        )
        if type_answer and type_answer.get("score", 0) > 0.1:
            answer_lower = type_answer["answer"].lower().strip()
            # Map to known types
            for known_type, keywords in _BUILDING_TYPE_KEYWORDS.items():
                if answer_lower in keywords or any(kw in answer_lower for kw in keywords):
                    btype = known_type
                    break
            if not btype and answer_lower:
                # Check against security delays keys
                for key in _SECURITY_DELAYS:
                    if key in answer_lower or answer_lower in key:
                        btype = key
                        break
            logger.debug("Transformer building type: %s (score=%.2f, answer='%s')",
                       btype, type_answer["score"], type_answer["answer"])

    except Exception as exc:
        logger.debug("Transformer extraction failed: %s", exc)

    return floor, btype


# ---------------------------------------------------------------------------
# Main analysis (CPU-bound, run in thread pool)
# ---------------------------------------------------------------------------
def _analyse_address(address_text: str) -> ZAFIResult:
    """
    Synchronous address analysis for ZAFI.
    Priority: regex > transformer > keyword > default
    """
    text = address_text.strip()
    if not text:
        return ZAFIResult(0, None, 0, 0, 0, "none")

    method = "none"
    floor = 0
    btype = None

    # ── Layer 1: Regex extraction (fast, reliable) ────────────────────────
    regex_floor, is_direct = _extract_floor_regex(text)
    keyword_btype = _extract_building_type_keywords(text)

    if regex_floor > 0:
        floor = regex_floor
        method = "regex"
    if keyword_btype:
        btype = keyword_btype
        if method == "none":
            method = "keyword"

    # ── Layer 2: Transformer enhancement (if regex found nothing) ─────────
    if floor == 0 or btype is None:
        tx_floor, tx_btype = _extract_with_transformer(text)
        if floor == 0 and tx_floor > 0:
            floor = tx_floor
            method = "transformer"
        if btype is None and tx_btype:
            btype = tx_btype
            if method == "none":
                method = "transformer"

    # ── Layer 3: Compute penalties ────────────────────────────────────────
    security = _SECURITY_DELAYS.get(btype, _DEFAULT_SECURITY) if btype else _DEFAULT_SECURITY
    elevator = floor * _SECONDS_PER_FLOOR

    return ZAFIResult(
        penalty_seconds=security + elevator,
        building_type=btype,
        floor_extracted=floor,
        security_delay=security,
        elevator_delay=elevator,
        extraction_method=method,
    )


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def compute_zafi(lat: float, lon: float, address_text: str = "") -> Dict:
    """
    Compute the Z-Axis Friction Index from the address text.

    Uses regex + transformer (distilbert QA) to extract floor number
    and building type, then calculates delivery friction penalty.

    Parameters
    ----------
    lat, lon : float
        Coordinates (used for cache key)
    address_text : str
        The delivery address text to analyse

    Returns
    -------
    dict
        ``{penalty_seconds, building_type, floor_extracted,
           security_delay, elevator_delay, extraction_method}``
    """
    # Cache key: hash of address + rounded coords
    cache_key = hashlib.md5(
        f"{round(lat, 3)}:{round(lon, 3)}:{address_text.lower().strip()}".encode()
    ).hexdigest()

    if cache_key in _zafi_cache:
        return _zafi_cache[cache_key]

    loop = asyncio.get_running_loop()
    result: ZAFIResult = await loop.run_in_executor(
        _executor, _analyse_address, address_text
    )
    payload = result.to_dict()

    # Cache the result
    _zafi_cache[cache_key] = payload

    # Cap cache size
    if len(_zafi_cache) > 500:
        oldest = next(iter(_zafi_cache))
        del _zafi_cache[oldest]

    return payload
