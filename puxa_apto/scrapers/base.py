
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from ..config import DEFAULT_HEADERS

logger = logging.getLogger(__name__)


class BaseScraper(ABC):

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or DEFAULT_HEADERS

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

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments = []
        page = 1

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page}...")

                response = requests.get(current_url, headers=self.headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "html.parser")
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

            except requests.RequestException as e:
                logger.error(f"Error making request on page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Error processing page {page}: {e}")
                break

        return apartments
