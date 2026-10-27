
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..utils import web
from ..utils.text import slugify

logger = logging.getLogger(__name__)

_MEDIA_KEY = re.compile(r"/([0-9a-f]{32})/")
_LISTING_ID = re.compile(r"\d{6,}")
_NEXT_F = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_RSC_ROW = re.compile(rb"([0-9a-f]+):")
_RSC_TEXT = re.compile(rb"T([0-9a-f]+),")
_RSC_REF = re.compile(r"^\$([0-9a-f]+)$")
# Agencies whose own sites we scrape: slug prefix of the portal advertiser name -> site.
_AGENCY_ADVERTISERS = {"leindecker-": "leindecker", "certa-": "certa"}
_AGENCY_CODE = re.compile(r"L0*(\d+)")


def _walk(node):
    """Yield every dict nested anywhere in a JSON value, parents before children."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _dig(node, *keys):
    """node[k1][k2]... or None when any level is missing or not a dict."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _ld_listings(node):
    """Yield every JSON-LD object that has a listing url and images."""
    for obj in _walk(node):
        if isinstance(obj.get("url"), str) and isinstance(obj.get("image"), list):
            yield obj


def listing_id(link: str) -> Optional[str]:
    """The site's listing id: the last run of 6+ digits in the link, ignoring its query."""
    ids = _LISTING_ID.findall(link.split("?", 1)[0])
    return ids[-1] if ids else None


def valid_point(lat, lon) -> bool:
    """Real coordinates; rejects missing values and the ≈(0,0) placeholders some sites emit."""
    numbers = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon))
    return numbers and not (abs(lat) < 1 and abs(lon) < 1)


def agency_ref(advertiser: Optional[str], external_id: Optional[str]) -> Optional[str]:
    """"certa:2270" for a portal listing by "Certa Aluguéis - Condomínios" with externalId "L02270";
    None unless the advertiser is an agency we scrape and the id is its code."""
    slug = slugify(advertiser or "")
    site = next((s for prefix, s in _AGENCY_ADVERTISERS.items() if slug.startswith(prefix)), None)
    match = _AGENCY_CODE.fullmatch(external_id or "")
    return f"{site}:{match.group(1)}" if site and match else None


def merge_details(apartment: Dict, details: Dict[str, Dict]) -> None:
    """Give the apartment its page details (coordinates, description, amenity codes, agency_ref,
    approximate_location)."""
    apartment.update(
        lat=None, lon=None, description="", amenity_codes=[], agency_ref=None, approximate_location=False
    )
    apartment.update(details.get(listing_id(apartment["link"]) or "", {}))


def _rsc_rows(text: str) -> Dict[str, str]:
    """Split a Next.js RSC flight payload into rows by id.

    A row is `<hex id>:<payload>`: either a JSON value ending at a newline, or
    `T<hex byte length>,<text>` whose text may itself contain newlines.
    """
    data = text.encode()
    rows = {}
    pos = 0
    while pos < len(data):
        row = _RSC_ROW.match(data, pos)
        if not row:
            newline = data.find(b"\n", pos)
            if newline < 0:
                break
            pos = newline + 1
            continue
        start = row.end()
        text_row = _RSC_TEXT.match(data, start)
        if text_row:
            start = text_row.end()
            end = start + int(text_row.group(1), 16)
            pos = end
        else:
            end = data.find(b"\n", start)
            end = len(data) if end < 0 else end
            pos = end + 1
        rows[row.group(1).decode()] = data[start:end].decode("utf-8", "replace")
    return rows


class BaseScraper(ABC):

    def __init__(self, url: str):
        self.url = url

    @abstractmethod
    def scrape_apartment(self, element) -> Optional[Dict]:
        pass

    @abstractmethod
    def find_listing_elements(self, soup: BeautifulSoup) -> List:
        pass

    def get_next_page_url(self, current_url: str, page_num: int) -> str:
        parsed = urlparse(current_url)
        query_params = parse_qs(parsed.query)
        query_params["pagina"] = [str(page_num)]
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)

    def has_next_page(self, soup: BeautifulSoup) -> bool:
        next_button = soup.find("a", {"aria-label": lambda x: x and "Próxima" in x if x else False})
        if next_button:
            return not next_button.get("aria-disabled") == "true"

        next_link = soup.find("a", href=lambda x: x and "pagina=" in x if x else False)
        if next_link:
            return True

        return False

    @staticmethod
    def link_grouped_cards(soup: BeautifulSoup) -> None:
        """Give grouped cards their listing URL.

        VivaReal/Zap render a unit advertised by several agencies as one card with href="#"
        (a modal opens on click). The page's JSON-LD still lists its URL, with the same images.
        """
        url_by_media = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except ValueError:
                continue
            for listing in _ld_listings(data):
                for image in listing["image"]:
                    match = _MEDIA_KEY.search(image) if isinstance(image, str) else None
                    if match:
                        url_by_media.setdefault(match.group(1), listing["url"])

        for card in soup.find_all("a", href="#"):
            for img in card.find_all("img", src=True):
                match = _MEDIA_KEY.search(img["src"])
                if match and match.group(1) in url_by_media:
                    card["href"] = url_by_media[match.group(1)]
                    break

    def page_details(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """Coordinates, description and amenity codes per listing id, from the RSC flight data.

        VivaReal/Zap ship their listing objects in `self.__next_f.push([1, "..."])` scripts.
        """
        flight = []
        for script in soup.find_all("script"):
            source = script.string or ""
            if "self.__next_f.push" not in source:
                continue
            for chunk in _NEXT_F.findall(source):
                try:
                    flight.append(json.loads('"' + chunk + '"'))
                except ValueError:
                    continue
        rows = _rsc_rows("".join(flight))

        details: Dict[str, Dict] = {}
        for row in rows.values():
            if '"usableAreas"' not in row:
                continue
            try:
                data = json.loads(row)
            except ValueError:
                continue
            for obj in _walk(data):
                amenities = obj.get("amenities")
                if not (isinstance(amenities, dict) and "usableAreas" in amenities and obj.get("id")):
                    continue
                description = obj.get("description") or ""
                if isinstance(description, str) and _RSC_REF.match(description):
                    description = rows.get(description[1:], "")
                values = amenities.get("values")
                entry = {
                    "description": description if isinstance(description, str) else "",
                    "amenity_codes": [str(v) for v in values] if isinstance(values, list) else [],
                    "agency_ref": agency_ref(_dig(obj, "advertiser", "name"), obj.get("externalId")),
                    # Hidden address: the portal gives a rounded placeholder point, not the flat's.
                    "approximate_location": _dig(obj, "address", "isApproximateLocation") is True,
                }
                lat = _dig(obj, "address", "coordinates", "latitude")
                lon = _dig(obj, "address", "coordinates", "longitude")
                if valid_point(lat, lon):
                    entry.update(lat=lat, lon=lon)
                # A listing can appear in several rows; keep the first non-empty value per field.
                known = details.setdefault(str(obj["id"]), {})
                for key, value in entry.items():
                    if not known.get(key):
                        known[key] = value
        return details

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments = []
        page = 1

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page}...")

                soup = BeautifulSoup(web.fetch_page(current_url), "html.parser")
                self.link_grouped_cards(soup)
                details = self.page_details(soup)
                listing_elements = self.find_listing_elements(soup)

                if not listing_elements:
                    logger.info(f"No apartments found on page {page}. Finishing.")
                    break

                logger.info(f"Found {len(listing_elements)} apartments on page {page}")

                page_apartments = []
                for elem in listing_elements:
                    apartment = self.scrape_apartment(elem)
                    if apartment:
                        merge_details(apartment, details)
                        page_apartments.append(apartment)

                apartments.extend(page_apartments)
                logger.info(f"Total accumulated: {len(apartments)} apartments\n")

                if max_pages and page >= max_pages:
                    logger.info(f"Page limit of {max_pages} reached.")
                    break

                if not self.has_next_page(soup):
                    logger.info("No more pages available.")
                    break

                page += 1
                time.sleep(1)

            except web.RequestException as e:
                logger.error(f"Error making request on page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Error processing page {page}: {e}")
                break

        return apartments
