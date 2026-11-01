"""Listing dicts (the scraper shape) to the values one sheet row shows, keyed by column."""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from ..sites import SITES
from ..utils.text import slugify
from .amenities import amenity_names

CELL_LIMIT = 32767  # characters an Excel cell holds
_SPAN = re.compile(r"<span[^>]*>.*?</span>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_APPROXIMATE: Dict[Any, str] = {True: "Sim", False: "Não"}

# column key -> listing field copied as is
_FIELDS = {
    "rua": "street",
    "total": "total_price",
    "aluguel": "price",
    "condominio": "condo_fee",
    "iptu": "iptu",
    "area": "area",
    "quartos": "bedrooms",
    "banheiros": "bathrooms",
    "vagas": "parking",
    "anuncio": "link",
}


def _canonical_neighborhoods(listings: List[Dict]) -> Dict[str, str]:
    """slug -> the spelling with the most accents, so "Santa Cecilia" reads "Santa Cecília"."""
    best: Dict[str, str] = {}
    for name in (apt.get("neighborhood") or "" for apt in listings):
        slug = slugify(name)
        if slug not in best or _accents(name) > _accents(best[slug]):
            best[slug] = name
    return best


def _accents(text: str) -> int:
    return sum(not ch.isascii() for ch in text)


def _source(link: str) -> str:
    host = urlparse(link).netloc
    return next((site.name for site in SITES.values() if host.endswith(site.host)), host)


def _clean_description(html: Optional[str]) -> Optional[str]:
    if html is None:
        return None
    return _SPACE.sub(" ", _TAG.sub("", _SPAN.sub("", html))).strip()


def _cell_safe(value: Any) -> Any:
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)[:CELL_LIMIT]
    return value


def _meters(km: Optional[float]) -> Optional[int]:
    """Distances are saved in km rounded to 2 places, so this is whole metres in steps of 10."""
    return None if km is None else round(km * 1000)


def _row(apt: Dict, neighborhoods: Dict[str, str], distance_keys: List[str]) -> Dict[str, Any]:
    row: Dict[str, Any] = {key: apt.get(field) for key, field in _FIELDS.items()}
    row["bairro"] = neighborhoods[slugify(apt.get("neighborhood") or "")]
    row["rua"] = row["rua"] or ""
    row["categoria"] = None
    for key in ("distance_km", *distance_keys):
        row[key] = _meters(apt.get(key))  # None for older listings without this place
    row["comodidades"] = amenity_names(apt.get("amenity_codes") or [])
    row["descricao"] = _clean_description(apt.get("description"))
    row["fonte"] = _source(apt.get("link") or "")
    row["aprox"] = _APPROXIMATE.get(apt.get("approximate_location"), "")
    return {key: _cell_safe(value) for key, value in row.items()}


def display_rows(listings: List[Dict]) -> List[Dict[str, Any]]:
    """One dict per listing, cheapest total first; listings without a total go last. Distances,
    the nearest place's and one per place, are in metres under their listing keys."""
    neighborhoods = _canonical_neighborhoods(listings)
    distance_keys = list(dict.fromkeys(k for apt in listings for k in apt if k.startswith("distance_km_")))
    ordered = sorted(listings, key=lambda apt: (apt.get("total_price") is None, apt.get("total_price") or 0))
    return [_row(apt, neighborhoods, distance_keys) for apt in ordered]
