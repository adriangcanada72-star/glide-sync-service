"""
BCLDB Product Catalog → Glide Sync Service
============================================
A web service that accepts a new BCLDB CSV extract,
compares it against the current Glide Product Catalog,
and pushes adds/updates/deletes via the Glide API.

Deploy to Railway, Render, or any Python host.
Point your Glide "Upload" button to this service's URL.
"""

import asyncio
import csv
import io
import os
import time
import json
import logging
from datetime import datetime
from collections import OrderedDict
from typing import Optional

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import consumer_card

# ─────────────────────────────────────────────
# CONFIG — set these as environment variables on your host
# ─────────────────────────────────────────────
GLIDE_API_TOKEN = os.environ.get("GLIDE_API_TOKEN", "")
GLIDE_APP_ID = os.environ.get("GLIDE_APP_ID", "")
GLIDE_TABLE_ID = os.environ.get("GLIDE_TABLE_ID", "")
GLIDE_TABLE_NAME = os.environ.get("GLIDE_TABLE_NAME", "native-table-Product Catalog")
UPLOAD_SECRET = os.environ.get("UPLOAD_SECRET", "")  # Optional: protect the upload page
PORT = int(os.environ.get("PORT", 8000))

# API endpoints
GLIDE_V2_BASE = "https://api.glideapps.com"
GLIDE_LEGACY_API = "https://api.glideapp.io/api/function/mutateTables"

# Sync settings
BATCH_SIZE = 100
KEY_COLUMN = "SKU"

COMPARE_COLUMNS = [
    "PRODUCT_NAME", "BRAND_NAME", "SPECIES", "SUBCATEGORY",
    "PER_RETAIL_UNIT_THC_MIN", "PER_RETAIL_UNIT_THC_MAX",
    "PER_RETAIL_UNIT_CBD_MIN", "PER_RETAIL_UNIT_CBD_MAX",
    "TERPENE_1_TYPE", "TERPENE_2_TYPE", "TERPENE_3_TYPE",
    "ECOMM_LONG_DESCRIPTION", "WSL_LIFECYCLE_STATUS",
    "WHOLESALE_PRICE_PER_UNIT",
]

ALL_COLUMNS = [
    "SKU", "PRODUCT_NAME", "BRAND_NAME", "BC_INDIGENOUS_PRODUCT",
    "SUBCATEGORY", "CLASS", "ORIGIN_COUNTRY", "ORIGIN_REGION",
    "ORIGIN_SUBREGION", "SU_QTY_IN_EACH_CASE", "SU_CODE",
    "SU_CODE_TYPE", "CASE_CODE", "CASE_CODE_TYPE",
    "SU_PRODUCT_NET_SIZE", "SU_PRODUCT_NET_SIZE_UOM",
    "SU_VOLUME_EQUIVALENCY", "SU_VOLUME_EQUIVALENCY_UOM",
    "CASE_WEIGHT", "CASE_WEIGHT_UOM", "STRAIN", "SPECIES",
    "PER_ACTIVATION_CBD_MAX", "PER_ACTIVATION_CBD_MIN",
    "PER_ACTIVATION_CBD_UOM", "PER_ACTIVATION_THC_MAX",
    "PER_ACTIVATION_THC_MIN", "PER_ACTIVATION_THC_UOM",
    "PER_DISCRETE_UNIT_CBD_MAX", "PER_DISCRETE_UNIT_CBD_MIN",
    "PER_DISCRETE_UNIT_CBD_UOM", "PER_DISCRETE_UNIT_THC_MAX",
    "PER_DISCRETE_UNIT_THC_MIN", "PER_DISCRETE_UNIT_THC_UOM",
    "PER_RETAIL_UNIT_CBD_MAX", "PER_RETAIL_UNIT_CBD_MIN",
    "PER_RETAIL_UNIT_CBD_UOM", "PER_RETAIL_UNIT_THC_MAX",
    "PER_RETAIL_UNIT_THC_MIN", "PER_RETAIL_UNIT_THC_UOM",
    "EXTRACTION_PROCESS", "PACKAGING_MATERIAL",
    "CONSUMPTION_METHOD", "HARVESTING_METHOD", "GROWING_METHOD",
    "TERPENE_1_TYPE", "TERPENE_2_TYPE", "TERPENE_3_TYPE",
    "NUMBER_OF_CONSUMER_ITEMS", "CONSUMER_ITEM_SIZE",
    "CONSUMER_ITEM_SIZE_UOM", "ECOMM_SHORT_DESCRIPTION",
    "ECOMM_LONG_DESCRIPTION", "WSL_LIFECYCLE_STATUS",
    "WHOLESALE_PRICE_PER_UNIT",
]

# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────
app = FastAPI(title="BCLDB Sync Service", version="1.0")
templates = Jinja2Templates(directory="templates")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync")


# ─────────────────────────────────────────────
# CSV PARSING
# ─────────────────────────────────────────────
def parse_csv(content: bytes) -> OrderedDict:
    """Parse CSV/TSV bytes into a dict keyed by SKU, auto-detecting encoding and delimiter."""
    # Try encodings — UTF-16 first (original BCLDB format), then UTF-8 variants (resaved)
    encodings = ["utf-16", "utf-8-sig", "utf-8", "cp1252", "latin-1"]
    text = None
    used_encoding = None

    for enc in encodings:
        try:
            decoded = content.decode(enc)
            # Strip any BOM characters
            decoded = decoded.replace('\ufeff', '')
            # Sanity check — must contain our key column name
            if KEY_COLUMN in decoded:
                text = decoded
                used_encoding = enc
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if text is None:
        text = content.decode("latin-1").replace('\ufeff', '')
        used_encoding = "latin-1 (fallback)"
        logger.warning(f"Key column '{KEY_COLUMN}' not found in any encoding, using fallback")

    logger.info(f"CSV decoded with encoding: {used_encoding}")

    # Auto-detect delimiter: tab (original BCLDB) vs comma (resaved CSV)
    first_line = text.split('\n')[0] if text else ''
    if '\t' in first_line:
        delimiter = '\t'
        logger.info("Detected delimiter: TAB (original BCLDB format)")
    else:
        delimiter = ','
        logger.info("Detected delimiter: COMMA (standard CSV)")

    # Parse the file
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    products = OrderedDict()
    for row in reader:
        sku = row.get(KEY_COLUMN, "").strip()
        if sku:
            products[sku] = {k: (v.strip() if v else "") for k, v in row.items()}

    logger.info(f"Parsed {len(products)} products from file")
    return products


# ─────────────────────────────────────────────
# GLIDE API CLIENT
# ─────────────────────────────────────────────
class GlideClient:
    """Handles all communication with the Glide API."""

    def __init__(self):
        self.token = GLIDE_API_TOKEN
        self.app_id = GLIDE_APP_ID
        self.table_id = GLIDE_TABLE_ID
        self.table_name = GLIDE_TABLE_NAME
        self.client = httpx.AsyncClient(timeout=30.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.app_id and self.table_id)

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def get_current_rows(self) -> OrderedDict:
        """Fetch all current rows from Glide Product Catalog."""
        if not self.is_configured:
            return OrderedDict()

        all_rows = []
        continuation = None

        while True:
            payload = {
                "appID": self.app_id,
                "queries": [{"tableName": self.table_name}],
            }
            if continuation:
                payload["queries"][0]["startAt"] = continuation

            response = await self.client.post(
                "https://api.glideapp.io/api/function/queryTables",
                headers=self.headers,
                json=payload,
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch rows: {response.status_code} {response.text[:200]}")
                break

            data = response.json()
            if data and len(data) > 0:
                rows = data[0].get("rows", [])
                all_rows.extend(rows)
                cont = data[0].get("next")
                if cont:
                    continuation = cont
                else:
                    break
            else:
                break

        # Convert to SKU-keyed dict
        products = OrderedDict()
        for row in all_rows:
            sku = str(row.get(KEY_COLUMN, row.get("SKU", ""))).strip()
            if sku:
                row["_row_id"] = row.get("$rowID", "")
                products[sku] = row

        logger.info(f"Fetched {len(products)} current products from Glide")
        return products

    async def execute_mutations(self, mutations: list) -> dict:
        """Execute a batch of mutations via the legacy API."""
        results = {"success": 0, "failed": 0, "errors": []}

        for i in range(0, len(mutations), BATCH_SIZE):
            batch = mutations[i:i + BATCH_SIZE]
            payload = {
                "appID": self.app_id,
                "mutations": batch,
            }

            try:
                response = await self.client.post(
                    GLIDE_LEGACY_API,
                    headers=self.headers,
                    json=payload,
                )

                if response.status_code == 200:
                    results["success"] += len(batch)
                    logger.info(f"Batch {i // BATCH_SIZE + 1}: {len(batch)} mutations OK")
                else:
                    results["failed"] += len(batch)
                    error_msg = f"Batch {i // BATCH_SIZE + 1}: HTTP {response.status_code}"
                    results["errors"].append(error_msg)
                    logger.error(f"{error_msg}: {response.text[:200]}")

            except Exception as e:
                results["failed"] += len(batch)
                results["errors"].append(str(e))
                logger.error(f"Batch error: {e}")

            # Rate limiting — pause between batches
            if i + BATCH_SIZE < len(mutations):
                await asyncio.sleep(1)

        return results

    async def close(self):
        await self.client.aclose()


glide = GlideClient()


# ─────────────────────────────────────────────
# COMPARISON ENGINE
# ─────────────────────────────────────────────
def compare_catalogs(new_data: dict, current_data: dict) -> dict:
    """Compare new extract against current catalog."""
    new_skus = set(new_data.keys())
    current_skus = set(current_data.keys())

    to_add = []
    to_update = []
    to_delete = []
    unchanged = []

    for sku in sorted(new_skus - current_skus):
        to_add.append({"sku": sku, "data": new_data[sku]})

    for sku in sorted(current_skus - new_skus):
        to_delete.append({
            "sku": sku,
            "name": current_data[sku].get("PRODUCT_NAME", "?"),
            "brand": current_data[sku].get("BRAND_NAME", "?"),
            "row_id": current_data[sku].get("_row_id", current_data[sku].get("Row ID", "")),
        })

    for sku in sorted(new_skus & current_skus):
        changes = {}
        for col in COMPARE_COLUMNS:
            new_val = new_data[sku].get(col, "")
            cur_val = current_data[sku].get(col, "")
            if new_val != cur_val:
                changes[col] = {"old": cur_val, "new": new_val}

        if changes:
            to_update.append({
                "sku": sku,
                "name": new_data[sku].get("PRODUCT_NAME", "?"),
                "changes": changes,
                "full_data": new_data[sku],
                "row_id": current_data[sku].get("_row_id", current_data[sku].get("Row ID", "")),
            })
        else:
            unchanged.append(sku)

    return {
        "to_add": to_add,
        "to_update": to_update,
        "to_delete": to_delete,
        "unchanged_count": len(unchanged),
        "summary": {
            "new_total": len(new_data),
            "current_total": len(current_data),
            "add": len(to_add),
            "update": len(to_update),
            "delete": len(to_delete),
            "unchanged": len(unchanged),
        },
    }


def build_mutations(comparison: dict) -> list:
    """Build Glide API mutation payloads from comparison results."""
    mutations = []

    for item in comparison["to_add"]:
        col_values = {col: item["data"].get(col, "") for col in ALL_COLUMNS}
        mutations.append({
            "kind": "add-row-to-table",
            "tableName": GLIDE_TABLE_NAME,
            "columnValues": col_values,
        })

    for item in comparison["to_update"]:
        if item.get("row_id"):
            mutations.append({
                "kind": "set-columns-in-row",
                "tableName": GLIDE_TABLE_NAME,
                "rowID": item["row_id"],
                "columnValues": {col: vals["new"] for col, vals in item["changes"].items()},
            })

    for item in comparison["to_delete"]:
        if item.get("row_id"):
            mutations.append({
                "kind": "delete-row",
                "tableName": GLIDE_TABLE_NAME,
                "rowID": item["row_id"],
            })

    return mutations


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Serve the upload page."""
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "api_configured": glide.is_configured,
    })


@app.post("/sync")
async def sync_catalog(
    file: UploadFile = File(...),
    mode: str = "preview",  # "preview" or "live"
    secret: str = "",
):
    """
    Main sync endpoint.
    - mode=preview: compare and report only (no API calls)
    - mode=live: compare and push changes to Glide
    """
    # Optional secret check
    if UPLOAD_SECRET and secret != UPLOAD_SECRET:
        raise HTTPException(status_code=403, detail="Invalid upload secret")

    # Validate file
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    logger.info(f"Received file: {file.filename} (mode: {mode})")

    # Parse uploaded CSV
    content = await file.read()
    try:
        new_data = parse_csv(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not new_data:
        raise HTTPException(status_code=400, detail="No products found in CSV")

    logger.info(f"Parsed {len(new_data)} products from upload")

    # Capture the consumer catalog from this same parse — no Glide API needed.
    # Runs on preview as well as live, so /card is populated either way.
    try:
        slim = consumer_card.build_slim_catalog(new_data, source_file=file.filename)
        consumer_card.save_catalog(slim)
    except Exception as e:
        logger.error(f"Consumer catalog build failed (sync continues): {e}")

    # Get current data from Glide
    if glide.is_configured:
        current_data = await glide.get_current_rows()
    else:
        current_data = OrderedDict()
        logger.warning("Glide API not configured — running in preview-only mode")

    # Compare
    comparison = compare_catalogs(new_data, current_data)
    summary = comparison["summary"]

    # Build response
    result = {
        "status": "preview",
        "timestamp": datetime.now().isoformat(),
        "file": file.filename,
        "summary": summary,
        "details": {
            "new_products": [
                {"sku": item["sku"], "name": item["data"].get("PRODUCT_NAME", "?")}
                for item in comparison["to_add"][:50]
            ],
            "updated_products": [
                {
                    "sku": item["sku"],
                    "name": item.get("name", "?"),
                    "changes": {col: vals for col, vals in item["changes"].items()},
                }
                for item in comparison["to_update"][:50]
            ],
            "deleted_products": [
                {"sku": item["sku"], "name": item.get("name", "?")}
                for item in comparison["to_delete"][:50]
            ],
        },
    }

    # Execute if live mode
    if mode == "live" and glide.is_configured:
        mutations = build_mutations(comparison)
        if mutations:
            logger.info(f"Executing {len(mutations)} mutations...")
            exec_result = await glide.execute_mutations(mutations)
            result["status"] = "completed"
            result["execution"] = exec_result
        else:
            result["status"] = "no_changes"
    elif mode == "live" and not glide.is_configured:
        result["status"] = "error"
        result["error"] = "Glide API not configured. Set GLIDE_API_TOKEN, GLIDE_APP_ID, and GLIDE_TABLE_ID environment variables."

    return JSONResponse(result)


@app.get("/card")
async def get_card(code: str = ""):
    """
    Consumer product lookup by scanned barcode.
      GET /card?code=628188006371
    Returns the product JSON for the hockey card, or 404 if unknown.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing ?code= parameter")

    product = consumer_card.lookup_card(code)

    if product is None:
        if not consumer_card.catalog_status()["loaded"]:
            raise HTTPException(
                status_code=503,
                detail="Catalog not loaded yet. Upload a BCLDB CSV to populate it.",
            )
        raise HTTPException(status_code=404, detail=f"No product found for code {code}")

    return JSONResponse(product, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/card/status")
async def card_status():
    """Diagnostics: is the consumer catalog loaded, and how big is it?"""
    return consumer_card.catalog_status()


@app.get("/health")
async def health():
    """Health check endpoint."""
    status = consumer_card.catalog_status()
    return {
        "status": "ok",
        "api_configured": glide.is_configured,
        "catalog_loaded": status["loaded"],
        "catalog_products": status["product_count"],
        "timestamp": datetime.now().isoformat(),
    }


@app.on_event("startup")
async def startup():
    """Load the persisted consumer catalog, if a volume is mounted."""
    consumer_card.load_catalog()


@app.on_event("shutdown")
async def shutdown():
    await glide.close()


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
