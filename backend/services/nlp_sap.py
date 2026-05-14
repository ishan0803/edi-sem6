"""
Semantic Address Penalty (SAP) Service
======================================
NLP micro-service that parses unstructured Indian addresses and calculates
a search-time penalty for the delivery rider based on missing structural
elements and ambiguous landmark references.

Penalty Matrix
--------------
- Missing house / flat number : +60 s
- Missing pincode (6-digit)  : +30 s
- Landmark keyword detected   : +120 s  (e.g. "near", "behind", "opp")
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded spaCy model (imported on first call to avoid slow startup)
# ---------------------------------------------------------------------------
_nlp = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_nlp():
    """Lazy-load en_core_web_sm so the import cost is paid once."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy en_core_web_sm loaded successfully.")
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not found. "
                "SAP will fall back to regex-only mode."
            )
            _nlp = "FALLBACK"
    return _nlp


# ---------------------------------------------------------------------------
# Regex patterns for Indian address components
# ---------------------------------------------------------------------------
# Matches flat/house numbers like "302", "A-12", "Flat 302", "House No. 45"
_RE_HOUSE_NUMBER = re.compile(
    r"""
    (?:^|\b)                         # word boundary or start
    (?:flat|house|plot|door|apt|unit  # common prefixes
       |no\.?|number|bldg|building)?
    \s*[-:#]?\s*                     # optional separator
    \d{1,5}                          # the actual number
    (?:\s*[-/]\s*[A-Za-z0-9]{1,4})?  # optional sub-unit (e.g. 12-A)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Indian 6-digit pincode
_RE_PINCODE = re.compile(r"\b[1-9]\d{5}\b")

# Landmark keywords that signal ambiguous, natural-language directions
_LANDMARK_KEYWORDS = re.compile(
    r"\b(?:near|behind|opp(?:osite)?|beside|next\s+to|adjacent\s+to|"
    r"in\s+front\s+of|close\s+to|across\s+from|facing|above|below)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Penalty dataclass
# ---------------------------------------------------------------------------
@dataclass
class SAPResult:
    """Breakdown of the Semantic Address Penalty."""
    penalty_seconds: int
    missing_house_number: bool
    missing_pincode: bool
    has_landmark_ref: bool

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core analysis (CPU-bound, runs in thread pool)
# ---------------------------------------------------------------------------
def _analyse_address(address_text: str) -> SAPResult:
    """
    Synchronous address analysis.  Heavy regex + optional spaCy NER.
    Called via ``run_in_executor`` to keep the event loop free.
    """
    text = address_text.strip()
    penalty = 0

    # --- 1.  House / Flat number ---
    has_house = bool(_RE_HOUSE_NUMBER.search(text))
    if not has_house:
        penalty += 60

    # --- 2.  Pincode ---
    has_pincode = bool(_RE_PINCODE.search(text))
    if not has_pincode:
        penalty += 30

    # --- 3.  Landmark keywords ---
    has_landmark = bool(_LANDMARK_KEYWORDS.search(text))
    if has_landmark:
        penalty += 120

    # --- 4.  Optional spaCy NER pass for entity richness ---
    nlp = _get_nlp()
    if nlp and nlp != "FALLBACK":
        try:
            doc = nlp(text)
            # If spaCy finds a GPE (city/state) but no LOC or FAC, the
            # address is likely area-level only → add small extra penalty.
            labels = {ent.label_ for ent in doc.ents}
            if "GPE" in labels and "FAC" not in labels and "LOC" not in labels:
                penalty += 15
        except Exception as exc:
            logger.debug("spaCy NER pass failed: %s", exc)

    return SAPResult(
        penalty_seconds=penalty,
        missing_house_number=not has_house,
        missing_pincode=not has_pincode,
        has_landmark_ref=has_landmark,
    )


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def compute_sap(address_text: str) -> Dict:
    """
    Compute the Semantic Address Penalty for *address_text*.

    Returns
    -------
    dict
        ``{penalty_seconds, missing_house_number, missing_pincode, has_landmark_ref}``
    """
    loop = asyncio.get_running_loop()
    result: SAPResult = await loop.run_in_executor(
        _executor, _analyse_address, address_text
    )
    return result.to_dict()
