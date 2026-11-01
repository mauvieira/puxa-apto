"""Shared loop for Porto Alegre agency sites on the same platform (Leindecker, Certa).

Their search pages list cards plus an inline `locations` array with every result's
coordinates; each listing's detail page adds condo fee, IPTU, street, description and
amenities.
"""

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

from ..utils import web
from ..utils.extractors import extract_price
from .base import valid_point

logger = logging.getLogger(__name__)

_LOCATION = re.compile(r'\["(\d+)",\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*\d+\]')
_PAGE = re.compile(r"/\d+/?$")


def map_points(html: str) -> Dict[str, Tuple[float, float]]:
    """Coordinates per listing code, from the page's `locations = [["<code>", lat, lon, 4], ...]`."""
    return {str(int(code)): (float(lat), float(lon)) for code, lat, lon in _LOCATION.findall(html)}


def page_url(url: str, page: int) -> str:
    """The page number is always the URL's last path segment."""
    if _PAGE.search(url):
        return _PAGE.sub(f"/{page}/", url)
    return url.rstrip("/") + f"/{page}/"


def new_apartment(**fields) -> Dict:
    """A listing with every key the CSV/JSON output expects; `fields` override the defaults."""
    apartment = {
        "title": "",
        "street": "",
        "neighborhood": "",
        "city": "Porto Alegre",
        "area": None,
        "bedrooms": None,
        "bathrooms": None,
        "parking": None,
        "price": None,
        "condo_fee": None,
        "iptu": None,
        "link": "",
        "images": [],
        "lat": None,
        "lon": None,
        "description": "",
        "amenity_codes": [],
        "agency_ref": None,
        "approximate_location": False,
    }
    apartment.update(fields)
    return apartment


def card_code(card) -> Optional[str]:
    element = card.select_one("[data-codigo]")
    code = element.get("data-codigo", "") if element else ""
    return str(int(code)) if code.isdigit() else None


def unique_texts(elements) -> List[str]:
    """Each element's whitespace-normalized text, without a leading "|", empties and repeats."""
    texts = (" ".join(el.get_text(" ", strip=True).lstrip("|").split()) for el in elements)
    return list(dict.fromkeys(t for t in texts if t))


def fees(pairs: Iterable[Tuple[str, str]]) -> Dict:
    """condo_fee / iptu from (label, value text) pairs; other labels are ignored."""
    found = {}
    for label, value in pairs:
        if label.startswith("Condom"):
            found["condo_fee"] = extract_price(value)
        elif label.startswith("IPTU"):
            found["iptu"] = extract_price(value)
    return found


class AgencyScraper(ABC):
    site: str  # agency_ref prefix
    card_selector: str

    def __init__(self, url: str):
        self.url = url

    @abstractmethod
    def parse_card(self, card) -> Optional[Tuple[str, Dict]]:
        """(code, apartment from new_apartment), or None when the card has no code or link."""

    @abstractmethod
    def parse_detail(self, soup: BeautifulSoup) -> Dict:
        """Only the keys found among street, condo_fee, iptu, description, amenity_codes."""

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments: List[Dict] = []
        seen: Set[str] = set()
        page = 1
        while not (max_pages and page > max_pages):
            try:
                html = web.fetch_page(page_url(self.url, page)).decode("utf-8", "replace")
            except web.RequestException as e:
                logger.error(f"Error making request on page {page}: {e}")
                break
            page_apartments = self._page(html, seen)
            if not page_apartments:
                break
            logger.info(f"Found {len(page_apartments)} apartments on page {page}")
            apartments.extend(page_apartments)
            page += 1
            time.sleep(1)
        return apartments

    def _page(self, html: str, seen: Set[str]) -> List[Dict]:
        points = map_points(html)
        apartments = []
        for card in BeautifulSoup(html, "html.parser").select(self.card_selector):
            apartment = self._listing(card, points)
            if apartment is None or apartment["link"] in seen:
                continue
            seen.add(apartment["link"])
            apartment.update(self._details(apartment["link"]))
            apartments.append(apartment)
        return apartments

    def _listing(self, card, points: Dict[str, Tuple[float, float]]) -> Optional[Dict]:
        try:
            parsed = self.parse_card(card)
        except Exception as e:
            logger.error(f"Error processing {self.site} card: {e}")
            return None
        if parsed is None:
            return None
        code, apartment = parsed
        lat, lon = points.get(code, (None, None))
        if valid_point(lat, lon):
            apartment.update(lat=lat, lon=lon)
        apartment["agency_ref"] = f"{self.site}:{code}"
        return apartment

    def _details(self, link: str) -> Dict:
        try:
            return self.parse_detail(BeautifulSoup(web.fetch_page(link), "html.parser"))
        except Exception as e:
            logger.warning(f"Error reading listing {link}: {e}")
            return {}
        finally:
            time.sleep(0.5)
