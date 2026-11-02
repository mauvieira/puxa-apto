"""Listings saved by `scrape` (JSON history or CSV) back in the dict shape the scrapers produce."""

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .workbook import XlsxExportError


def _number(text: str, cast: Callable[[float], float]) -> Optional[float]:
    try:
        return cast(float(text)) if text else None
    except ValueError:
        return None


def _integer(text: str) -> Optional[float]:
    return _number(text, int)


def _float(text: str) -> Optional[float]:
    return _number(text, float)


def _items(text: str) -> List[str]:
    return [item for item in text.split(";") if item]  # save_to_csv joins lists with ";"


def _flag(text: str) -> Optional[bool]:
    return {"True": True, "False": False}.get(text)


# CSV column -> parser; columns not named here (and not distances) stay strings.
_PARSERS: Dict[str, Callable[[str], Any]] = {
    **dict.fromkeys(("area", "bedrooms", "bathrooms", "parking"), _integer),
    **dict.fromkeys(("price", "condo_fee", "iptu", "total_price", "lat", "lon"), _float),
    **dict.fromkeys(("amenity_codes", "images"), _items),
    "approximate_location": _flag,
}


def _parser(key: str) -> Callable[[str], Any]:
    return _PARSERS.get(key) or (_float if key.startswith("distance_km") else str)


def _from_csv_row(row: Dict[Optional[str], Optional[str]]) -> Dict:
    # A ragged row puts missing cells as None and extra ones under the key None.
    return {key: _parser(key)(text or "") for key, text in row.items() if key is not None}


def read_listings(path: Path) -> List[Dict]:
    """Listings in a `.json` history or a `.csv` written by save_to_csv."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            listings = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            listings = None
        if not isinstance(listings, list) or not all(isinstance(a, dict) for a in listings):
            raise XlsxExportError(f"Expected a JSON list of listings: {path}")
        return listings
    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [_from_csv_row(row) for row in csv.DictReader(f)]
    raise XlsxExportError(f"Expected a .json or .csv listings file: {path}")
