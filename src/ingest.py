"""Ingestion service for TrendCast.

Downloads WFP Pakistan food prices CSV from HDX and saves an untouched raw snapshot
along with a cryptographic provenance manifest (source URL, sha256, row count, timestamp).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_WFP_URL = (
    "https://data.humdata.org/dataset/125455ff-c8a8-4f4b-9190-bf0e84559dc7/resource/"
    "8cf7a8a2-58a1-4c3f-bafe-f38af68d971b/download/wfp_food_prices_pak.csv"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_FILE = RAW_DIR / "wfp_food_prices_pakistan.csv"
MANIFEST_FILE = RAW_DIR / "manifest.json"


def compute_sha256(filepath: Path) -> str:
    """Compute sha256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def count_csv_rows(filepath: Path) -> int:
    """Count non-empty lines in CSV minus header."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = sum(1 for line in f if line.strip())
    return max(0, lines - 1)


def ingest_wfp_data(url: str = DEFAULT_WFP_URL, force: bool = False) -> dict[str, Any]:
    """Download and snapshot raw WFP food prices data with provenance."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if RAW_FILE.exists() and not force:
        logger.info("Raw file already exists at %s. Verifying integrity...", RAW_FILE)
        sha256 = compute_sha256(RAW_FILE)
        rows = count_csv_rows(RAW_FILE)
        logger.info("Existing raw file verified: %d rows, sha256: %s", rows, sha256[:12])
    else:
        logger.info("Downloading raw WFP food prices from %s ...", url)
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        with open(RAW_FILE, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

        sha256 = compute_sha256(RAW_FILE)
        rows = count_csv_rows(RAW_FILE)
        logger.info("Downloaded %d rows to %s (sha256: %s)", rows, RAW_FILE, sha256[:12])

    manifest_data = {
        "snapshot_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "source": "WFP_HDX",
                "name": "WFP Food Prices for Pakistan",
                "url": url,
                "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "sha256": sha256,
                "rows": rows,
                "filename": RAW_FILE.name,
            }
        ],
    }

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info("Manifest written to %s", MANIFEST_FILE)
    return manifest_data


if __name__ == "__main__":
    ingest_wfp_data()

