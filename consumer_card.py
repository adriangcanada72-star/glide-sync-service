"""
Consumer Card Module — The Terpene Sommelier
=============================================
Adds a consumer-facing product lookup to the BCLDB sync service.

  • Captures a slim catalog whenever a BCLDB CSV is synced (no Glide API needed)
  • Persists it to disk (mount a Railway Volume at /data to survive restarts)
  • Serves  GET /card?code=<GTIN>  →  JSON for the consumer hockey card

The barcode on a cannabis package is a GS1 code whose (01) field is a GTIN-14.
Phones read it as 12–14 digits; the BCLDB SU_CODE column holds the same value.
We normalise both sides by stripping leading zeros before matching.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("card")

# Mount a Railway Volume at /data so the catalog survives restarts/redeploys.
CATALOG_PATH = os.environ.get("CATALOG_PATH", "/data/catalog.json")

# In-memory index: normalised GTIN -> product dict
_INDEX: dict = {}
_META: dict = {"loaded_at": None, "product_count": 0, "source_file": None}


# ─────────────────────────────────────────────
# TERPENE NAME NORMALISATION
# ─────────────────────────────────────────────
# BCLDB writes terpene names inconsistently:
#   "Caryophyllene"        -> needs its Greek prefix  -> "Beta-Caryophyllene"
#   "Beta_Caryophyllene"   -> underscore to hyphen    -> "Beta-Caryophyllene"
#   "Germacrene_B"         -> underscore to hyphen    -> "Germacrene-B"
# Anything unrecognised passes through unchanged (same as the ELSE branch
# in the Glide If→Then→Else column).

BARE_NAME_PREFIX = {
    "caryophyllene": "Beta-Caryophyllene",
    "humulene": "Alpha-Humulene",
    "myrcene": "Beta-Myrcene",
    "pinene": "Alpha-Pinene",
    "bisabolol": "Alpha-Bisabolol",
    "farnesene": "Beta-Farnesene",
}


def normalise_terpene(raw: str) -> str:
    """Turn a raw BCLDB terpene name into its proper display name."""
    if not raw:
        return ""
    name = raw.strip()
    if not name:
        return ""

    # Rule 1 — a bare name that conventionally carries a Greek prefix
    key = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    if key in BARE_NAME_PREFIX:
        return BARE_NAME_PREFIX[key]

    # Rule 2 — underscores are hyphens ("Beta_Pinene" -> "Beta-Pinene")
    if "_" in name:
        parts = [p for p in name.split("_") if p]
        return "-".join(p[:1].upper() + p[1:] for p in parts)

    # Otherwise leave it exactly as BCLDB supplied it
    return name


# ─────────────────────────────────────────────
# CODE NORMALISATION
# ─────────────────────────────────────────────
def normalise_code(code: str) -> str:
    """Keep digits only, drop leading zeros. '00628188006371' -> '628188006371'."""
    if not code:
        return ""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return digits.lstrip("0")


# ─────────────────────────────────────────────
# BUILD THE SLIM CONSUMER CATALOG
# ─────────────────────────────────────────────
def _num(v: str):
    """'240' -> 240.0, '' -> None"""
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _int_or_none(v):
    """'-4' -> -4  |  '' -> None. TRIAX scores are integers from -5 to +5."""
    try:
        s = str(v).strip()
        return int(float(s)) if s else None
    except (TypeError, ValueError):
        return None


def _tidy(n: float) -> str:
    """24.0 -> '24'   |   0.5 -> '0.5'"""
    return str(int(n)) if n == int(n) else f"{n:g}"


def _fmt_potency(lo: str, hi: str, uom: str) -> str:
    """
    BCLDB ships potency in two unit systems:
      • mg/g  — flower, pre-rolls, extracts, seeds.  ÷10 gives the familiar %.
                (240 mg/g -> 24% ;  870–930 mg/g -> 87–93%)
      • mg    — edibles, beverages, topicals.  Shown as an absolute dose.
    """
    lo_n, hi_n = _num(lo), _num(hi)
    if lo_n is None and hi_n is None:
        return ""

    uom = (uom or "").strip().lower()
    if uom == "mg/g":
        lo_n = lo_n / 10 if lo_n is not None else None
        hi_n = hi_n / 10 if hi_n is not None else None
        unit = "%"
    else:                       # "mg" (or anything unexpected — keep the raw unit)
        unit = uom if uom else ""

    if lo_n is not None and hi_n is not None and lo_n != hi_n:
        return f"{_tidy(lo_n)}–{_tidy(hi_n)}{unit}"
    val = hi_n if lo_n is None else lo_n
    return f"{_tidy(val)}{unit}"


def build_slim_catalog(products: dict, source_file: str = "") -> dict:
    """
    From the full BCLDB parse (SKU -> row dict), build the consumer index
    keyed by normalised SU_CODE. Only the columns the card actually shows.
    """
    index = {}
    skipped_no_code = 0
    has_triax = 0

    for sku, row in products.items():
        code = normalise_code(row.get("SU_CODE", ""))
        if not code:
            skipped_no_code += 1
            continue

        terps = [
            normalise_terpene(row.get("TERPENE_1_TYPE", "")),
            normalise_terpene(row.get("TERPENE_2_TYPE", "")),
            normalise_terpene(row.get("TERPENE_3_TYPE", "")),
        ]

        entry = {
            "sku": sku,
            "name": row.get("PRODUCT_NAME", "").strip(),
            "brand": row.get("BRAND_NAME", "").strip(),
            "category": row.get("SUBCATEGORY", "").strip(),
            "klass": row.get("CLASS", "").strip(),
            "species": row.get("SPECIES", "").strip(),      # Indica / Sativa / Hybrid
            "strain": row.get("STRAIN", "").strip(),
            "size": (row.get("SU_PRODUCT_NET_SIZE", "").strip() + " " +
                     row.get("SU_PRODUCT_NET_SIZE_UOM", "").strip()).strip(),
            "thc": _fmt_potency(row.get("PER_RETAIL_UNIT_THC_MIN", ""),
                                row.get("PER_RETAIL_UNIT_THC_MAX", ""),
                                row.get("PER_RETAIL_UNIT_THC_UOM", "")),
            "cbd": _fmt_potency(row.get("PER_RETAIL_UNIT_CBD_MIN", ""),
                                row.get("PER_RETAIL_UNIT_CBD_MAX", ""),
                                row.get("PER_RETAIL_UNIT_CBD_UOM", "")),
            "terpenes": [t for t in terps if t],
            "description": row.get("ECOMM_LONG_DESCRIPTION", "").strip(),
            "logo": row.get("Brand Logo", "").strip(),
        }

        # TRIAX — present only when the upload is a Glide catalog export.
        # These are the main app's own computed values, so the consumer card
        # can never disagree with the staff app.
        cer = _int_or_none(row.get("Cerebral_Final"))
        som = _int_or_none(row.get("Somatic_Final"))
        ovr = _int_or_none(row.get("Overall_Final"))
        if cer is not None or som is not None or ovr is not None:
            entry["triax"] = {
                "cerebral": cer,
                "somatic": som,
                "overall": ovr,
                "cerebral_desc": row.get("Cerebral_Descriptor", "").strip(),
                "somatic_desc": row.get("Somatic_Descriptor", "").strip(),
                "overall_desc": row.get("Overall_Descriptor", "").strip(),
                "leaning": row.get("Leaning", "").strip(),   # e.g. "Indica Leaning"
            }
            has_triax += 1

        index[code] = entry

    logger.info(
        f"Slim catalog built: {len(index)} products indexed by SU_CODE "
        f"({skipped_no_code} skipped — no SU_CODE; {has_triax} with TRIAX)"
    )

    return {
        "meta": {
            "built_at": datetime.now().isoformat(),
            "product_count": len(index),
            "skipped_no_code": skipped_no_code,
            "with_triax": has_triax,
            "source_file": source_file,
        },
        "products": index,
    }


# ─────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────
def save_catalog(catalog: dict) -> bool:
    """Write the slim catalog to disk. Safe if the volume isn't mounted."""
    global _INDEX, _META
    _INDEX = catalog["products"]
    _META = catalog["meta"]
    _META["loaded_at"] = datetime.now().isoformat()

    try:
        os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
        tmp = CATALOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False)
        os.replace(tmp, CATALOG_PATH)          # atomic: never a half-written file
        logger.info(f"Catalog saved to {CATALOG_PATH} ({len(_INDEX)} products)")
        return True
    except Exception as e:
        # In-memory index still works until the next restart.
        logger.warning(f"Could not persist catalog to {CATALOG_PATH}: {e}")
        return False


def load_catalog() -> bool:
    """Load the catalog from disk at startup."""
    global _INDEX, _META
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        _INDEX = catalog.get("products", {})
        _META = catalog.get("meta", {})
        _META["loaded_at"] = datetime.now().isoformat()
        logger.info(f"Catalog loaded from disk: {len(_INDEX)} products")
        return True
    except FileNotFoundError:
        logger.warning(
            f"No catalog at {CATALOG_PATH} yet — upload a BCLDB CSV to populate it."
        )
        return False
    except Exception as e:
        logger.error(f"Failed to load catalog: {e}")
        return False


# ─────────────────────────────────────────────
# LOOKUP
# ─────────────────────────────────────────────
def lookup_card(code: str) -> Optional[dict]:
    """Find a product by scanned barcode (GTIN). Returns None if unknown."""
    key = normalise_code(code)
    if not key:
        return None
    return _INDEX.get(key)


def catalog_status() -> dict:
    return {
        "loaded": bool(_INDEX),
        "product_count": len(_INDEX),
        "meta": _META,
        "catalog_path": CATALOG_PATH,
    }
