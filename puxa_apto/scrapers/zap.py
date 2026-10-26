
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..utils.extractors import extract_number, extract_price
from .base import BaseScraper

logger = logging.getLogger(__name__)


class ZapScraper(BaseScraper):

    def scrape_apartment(self, li_element) -> Optional[Dict]:
        try:
            link_elem = li_element.find("a", href=True)
            if not link_elem or link_elem["href"] == "#":
                return None

            link = link_elem.get("href", "")
            if not link.startswith("http"):
                link = urljoin("https://www.zapimoveis.com.br", link)

            title_elem = li_element.find("h2", {"data-cy": "rp-cardProperty-location-txt"})
            title = title_elem.get_text(strip=True) if title_elem else ""

            street_elem = li_element.find("p", {"data-cy": "rp-cardProperty-street-txt"})
            street = street_elem.get_text(strip=True) if street_elem else ""

            neighborhood = ""
            city = ""
            if title_elem:
                span_elem = title_elem.find("span")
                if span_elem:
                    span_elem.decompose()
                location_text = title_elem.get_text(strip=True)
                location_match = re.search(r"([^,]+),\s*(.+)", location_text)
                if location_match:
                    neighborhood = location_match.group(1).strip()
                    city = location_match.group(2).strip()

            area_elem = li_element.find("li", {"data-cy": "rp-cardProperty-propertyArea-txt"})
            area_text = area_elem.get_text(strip=True) if area_elem else ""
            area = extract_number(area_text)

            bedrooms_elem = li_element.find("li", {"data-cy": "rp-cardProperty-bedroomQuantity-txt"})
            bedrooms_text = bedrooms_elem.get_text(strip=True) if bedrooms_elem else ""
            bedrooms = extract_number(bedrooms_text)

            bathrooms_elem = li_element.find("li", {"data-cy": "rp-cardProperty-bathroomQuantity-txt"})
            bathrooms_text = bathrooms_elem.get_text(strip=True) if bathrooms_elem else ""
            bathrooms = extract_number(bathrooms_text)

            parking_elem = li_element.find("li", {"data-cy": "rp-cardProperty-parkingSpacesQuantity-txt"})
            parking_text = parking_elem.get_text(strip=True) if parking_elem else ""
            parking = extract_number(parking_text)

            price_elem = li_element.find("div", {"data-cy": "rp-cardProperty-price-txt"})
            price_text = ""
            condo_fee = None
            iptu = None

            if price_elem:
                first_p = price_elem.find("p")
                if first_p:
                    price_match = re.search(r"R\$\s*[\d.,]+", first_p.get_text(" ", strip=True))
                    if price_match:
                        price_text = price_match.group(0)
                details_text = price_elem.get_text(" ", strip=True)
                condo_match = re.search(r"Cond\.\s*R\$\s*([\d.]+)", details_text)
                iptu_match = re.search(r"IPTU\s*R\$\s*([\d.]+)", details_text)
                if condo_match:
                    condo_fee = extract_price(condo_match.group(0))
                if iptu_match:
                    iptu = extract_price(iptu_match.group(0))

            price = extract_price(price_text)

            apartment = {
                "title": title,
                "street": street,
                "neighborhood": neighborhood,
                "city": city,
                "area": area,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "parking": parking,
                "price": price,
                "condo_fee": condo_fee,
                "iptu": iptu,
                "link": link,
                "images": [],
            }

            return apartment
        except Exception as e:
            logger.error(f"Error processing Zap Imóveis apartment: {e}")
            return None

    def find_listing_elements(self, soup: BeautifulSoup) -> List:
        return soup.find_all("li", {"data-cy": "rp-property-cd"})
