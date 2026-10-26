
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..utils import web

logger = logging.getLogger(__name__)

_MEDIA_KEY = re.compile(r"/([0-9a-f]{32})/")


def _ld_listings(node):
    """Yield every JSON-LD object that has a listing url and images."""
    if isinstance(node, dict):
        if isinstance(node.get("url"), str) and isinstance(node.get("image"), list):
            yield node
        for value in node.values():
            yield from _ld_listings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ld_listings(value)


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

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments = []
        page = 1

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page}...")

                soup = BeautifulSoup(web.fetch_page(current_url), "html.parser")
                self.link_grouped_cards(soup)
                listing_elements = self.find_listing_elements(soup)

                if not listing_elements:
                    logger.info(f"No apartments found on page {page}. Finishing.")
                    break

                logger.info(f"Found {len(listing_elements)} apartments on page {page}")

                page_apartments = []
                for elem in listing_elements:
                    apartment = self.scrape_apartment(elem)
                    if apartment:
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
