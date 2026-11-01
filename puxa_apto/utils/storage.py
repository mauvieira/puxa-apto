

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .fingerprint import create_apartment_fingerprint

logger = logging.getLogger(__name__)


def load_existing_apartments(
    json_file: str = "apartamentos.json", csv_file: str = "apartamentos.csv"
) -> Tuple[Set[str], Set[str], Set[str]]:
    existing_links = set()
    existing_fingerprints = set()
    existing_refs = set()

    if os.path.exists(json_file):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for apt in existing:
                    link = apt.get("link", "")
                    if link:
                        existing_links.add(link)
                    if apt.get("agency_ref"):
                        existing_refs.add(apt["agency_ref"])
                    fingerprint = create_apartment_fingerprint(apt)
                    if fingerprint:
                        existing_fingerprints.add(fingerprint)
        except Exception as e:
            logger.warning(f"Error loading {json_file}: {e}")

    if os.path.exists(csv_file):
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    link = row.get("link", "")
                    if link:
                        existing_links.add(link)
                    if row.get("agency_ref"):
                        existing_refs.add(row["agency_ref"])

                    apt_dict = {
                        "street": row.get("street", ""),
                        "neighborhood": row.get("neighborhood", ""),
                        "area": (
                            int(row["area"])
                            if row.get("area") and row["area"].isdigit()
                            else None
                        ),
                        "bedrooms": (
                            int(row["bedrooms"])
                            if row.get("bedrooms") and row["bedrooms"].isdigit()
                            else None
                        ),
                        "price": (
                            float(row["price"])
                            if row.get("price")
                            and row["price"].replace(".", "").isdigit()
                            else None
                        ),
                    }
                    fingerprint = create_apartment_fingerprint(apt_dict)
                    if fingerprint:
                        existing_fingerprints.add(fingerprint)
        except Exception as e:
            logger.warning(f"Error loading {csv_file}: {e}")

    return existing_links, existing_fingerprints, existing_refs


def save_to_json(apartments: List[Dict], filename: str = "apartamentos.json") -> None:
    """Append to the JSON file (the accumulated history)."""
    saved = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            saved = json.load(f)
    if not apartments:
        logger.info("No data to save to JSON.")
        return

    saved.extend(apartments)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

    logger.info(f"Data saved to JSON: {filename} ({len(apartments)} new records)")


def csv_fieldnames(apartments: List[Dict]) -> List[str]:
    """CSV columns for `apartments`: fixed fields, one distance column per place, then any other key."""
    fieldnames = [
        "link",
        "agency_ref",
        "title",
        "street",
        "neighborhood",
        "city",
        "area",
        "bedrooms",
        "bathrooms",
        "parking",
        "price",
        "condo_fee",
        "iptu",
        "total_price",
        "distance_km",
    ]
    # One distance column per reference place, named after it, in first-seen order.
    fieldnames += dict.fromkeys(k for apt in apartments for k in apt if k.startswith("distance_km_"))
    fieldnames += ["approximate_location", "lat", "lon", "amenity_codes", "description", "images"]
    # Any other field the listings carry, so the CSV holds everything the JSON does.
    fieldnames += [k for k in dict.fromkeys(k for apt in apartments for k in apt) if k not in fieldnames]
    return fieldnames


def _csv_row(apt: Dict, fieldnames: List[str]) -> Dict:
    row = {}
    for field in fieldnames:
        value = apt.get(field, "")
        row[field] = ";".join(value) if isinstance(value, list) else value
    return row


def save_to_csv(apartments: List[Dict], filename: str = "apartamentos.csv") -> None:
    if not apartments:
        logger.info("No data to save to CSV.")
        return

    fieldnames = csv_fieldnames(apartments)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_csv_row(apt, fieldnames) for apt in apartments)

    logger.info(f"Data saved to CSV: {filename} ({len(apartments)} records)")


def append_to_csv(apartments: List[Dict], filename: str) -> str:
    """Append `apartments` to `filename` and return the path written.

    A missing or empty file gets a header first. An existing file keeps its header and column order
    untouched; rows are written in that order. If its columns differ from these listings' (e.g. the
    places changed), the file is left alone and the listings go to a new sibling file instead."""
    if not apartments:
        return ""

    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        save_to_csv(apartments, filename)
        return filename

    with open(filename, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])

    if len(header) != len(set(header)) or set(header) != set(csv_fieldnames(apartments)):
        path = Path(filename)
        stem = f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fallback = path.with_name(f"{stem}{path.suffix}")
        n = 2
        while fallback.exists():
            fallback = path.with_name(f"{stem}_{n}{path.suffix}")
            n += 1
        save_to_csv(apartments, str(fallback))
        logger.warning(f"{filename} has different columns; new listings saved to {fallback}")
        return str(fallback)

    with open(filename, "rb") as f:
        f.seek(-1, os.SEEK_END)
        needs_separator = f.read(1) != b"\n"

    with open(filename, "a", newline="", encoding="utf-8") as f:
        if needs_separator:
            f.write("\r\n")
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writerows(_csv_row(apt, header) for apt in apartments)

    logger.info(f"Data appended to CSV: {filename} ({len(apartments)} records)")
    return filename


def save_new_apartments_csv(apartments: List[Dict]) -> str: 
    if not apartments:
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"apartamentos_novos_{timestamp}.csv"
    save_to_csv(apartments, filename)
    return filename
