
import logging
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from ..models.apartment import Apartment

logger = logging.getLogger(__name__)


def create_apartment_fingerprint(
    apt: Dict, require_all_fields: bool = False
) -> Optional[str]:
    if isinstance(apt, Apartment):
        street = apt.street.strip().lower()
        neighborhood = apt.neighborhood.strip().lower()
        area = apt.area
        bedrooms = apt.bedrooms
        price = apt.price
    else:
        street = apt.get("street", "").strip().lower()
        neighborhood = apt.get("neighborhood", "").strip().lower()
        area = apt.get("area")
        bedrooms = apt.get("bedrooms")
        price = apt.get("price")

    if not street or not neighborhood:
        return None

    if require_all_fields:
        if not area or not bedrooms or not price:
            return None

    street_normalized = re.sub(r"[^\w\s]", "", street)
    street_normalized = re.sub(r"\s+", " ", street_normalized).strip()

    street_parts = street_normalized.split()
    if len(street_parts) > 0:
        street_key = " ".join(street_parts[:3])
    else:
        street_key = street_normalized[:40]

    neighborhood_normalized = re.sub(r"[^\w\s]", "", neighborhood)
    neighborhood_normalized = re.sub(r"\s+", " ", neighborhood_normalized).strip()

    parts = []

    if street_key:
        parts.append(street_key[:40])
    else:
        return None

    if neighborhood_normalized:
        parts.append(neighborhood_normalized[:30])
    else:
        return None

    if area:
        parts.append(str(int(area)))
    elif require_all_fields:
        return None
    else:
        parts.append("")

    if bedrooms:
        parts.append(str(int(bedrooms)))
    elif require_all_fields:
        return None
    else:
        parts.append("")

    if price:
        price_rounded = int(round(price / 1000) * 1000)
        parts.append(str(price_rounded))
    elif require_all_fields:
        return None
    else:
        parts.append("")

    fingerprint = "|".join(parts)
    return fingerprint if len(parts) >= 2 and parts[0] and parts[1] else None


_EMPTY = (None, "", [])


def drop_cross_posts(apartments: List[Dict]) -> List[Dict]:
    """Keep one listing per agency_ref: the agency's own copy when present, else the first seen.

    The kept copy's empty fields are filled from the dropped ones, e.g. coordinates the
    agency's map doesn't have yet. Listings without a ref pass through; order is kept.
    """
    copies: Dict[str, List[Dict]] = {}
    for apt in apartments:
        if apt.get("agency_ref"):
            copies.setdefault(apt["agency_ref"], []).append(apt)

    kept: Dict[str, Dict] = {}
    for ref, group in copies.items():
        host = ref.split(":")[0] + ".com.br"
        own = next((a for a in group if urlparse(a.get("link", "")).netloc.endswith(host)), group[0])
        for other in group:
            for key, value in other.items():
                if own.get(key) in _EMPTY and value not in _EMPTY:
                    own[key] = value
        kept[ref] = own
    return [a for a in apartments if not a.get("agency_ref") or kept[a["agency_ref"]] is a]


def filter_new_apartments(
    apartments: List[Dict],
    existing_links: Set[str],
    existing_fingerprints: Set[str],
    existing_refs: Set[str],
) -> List[Dict]:
    new_apartments = []
    duplicates_by_link = 0
    duplicates_by_fingerprint = 0
    duplicates_by_ref = 0
    skipped_no_data = 0

    for apt in apartments:
        link = apt.get("link", "")

        if not link:
            skipped_no_data += 1
            logger.warning(
                f"Apartment without link found. Saving anyway to avoid data loss. "
                f"Street: {apt.get('street', 'N/A')}, Neighborhood: {apt.get('neighborhood', 'N/A')}"
            )
            new_apartments.append(apt)
            continue

        is_duplicate = False
        ref = apt.get("agency_ref")

        if link in existing_links:
            is_duplicate = True
            duplicates_by_link += 1
        elif ref and ref in existing_refs:
            is_duplicate = True
            duplicates_by_ref += 1

        if not is_duplicate:
            fingerprint_full = create_apartment_fingerprint(apt, require_all_fields=True)
            fingerprint_partial = create_apartment_fingerprint(
                apt, require_all_fields=False
            )

            if fingerprint_full and fingerprint_full in existing_fingerprints:
                is_duplicate = True
                duplicates_by_fingerprint += 1
            elif fingerprint_partial and fingerprint_partial in existing_fingerprints:
                street = apt.get("street", "")
                neighborhood = apt.get("neighborhood", "")
                area = apt.get("area")
                bedrooms = apt.get("bedrooms")
                price = apt.get("price")

                if street and neighborhood and area and bedrooms and price:
                    is_duplicate = True
                    duplicates_by_fingerprint += 1

        if not is_duplicate:
            new_apartments.append(apt)
            existing_links.add(link)
            if ref:
                existing_refs.add(ref)

            fingerprint = create_apartment_fingerprint(apt, require_all_fields=True)
            if not fingerprint:
                fingerprint = create_apartment_fingerprint(apt, require_all_fields=False)
            if fingerprint:
                existing_fingerprints.add(fingerprint)

    if duplicates_by_link > 0 or duplicates_by_fingerprint > 0 or duplicates_by_ref > 0:
        logger.info(
            f"Duplicates detected: {duplicates_by_link} by link, {duplicates_by_fingerprint} by fingerprint, "
            f"{duplicates_by_ref} by agency code"
        )
    if skipped_no_data > 0:
        logger.warning(
            f"{skipped_no_data} apartments without links were saved to avoid data loss"
        )

    return new_apartments
