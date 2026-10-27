

import csv
import json
import logging
import os
from datetime import datetime
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


def save_to_json(apartments: List[Dict], filename: str = "apartamentos.json") -> List[Dict]:
    """Append to the JSON file (the accumulated history) and return its full contents."""
    saved = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            saved = json.load(f)
    if not apartments:
        logger.info("No data to save to JSON.")
        return saved

    saved.extend(apartments)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

    logger.info(f"Data saved to JSON: {filename} ({len(apartments)} new records)")
    return saved


def save_to_csv(apartments: List[Dict], filename: str = "apartamentos.csv") -> None:
    if not apartments:
        logger.info("No data to save to CSV.")
        return

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

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for apt in apartments:
            row = {}
            for field in fieldnames:
                value = apt.get(field, "")
                row[field] = ";".join(value) if isinstance(value, list) else value
            writer.writerow(row)

    logger.info(f"Data saved to CSV: {filename} ({len(apartments)} records)")


def save_new_apartments_csv(apartments: List[Dict]) -> str: 
    if not apartments:
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"apartamentos_novos_{timestamp}.csv"
    save_to_csv(apartments, filename)
    return filename
