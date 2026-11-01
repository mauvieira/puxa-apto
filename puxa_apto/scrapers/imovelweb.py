
import json
import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..utils import web
from ..utils.extractors import extract_number, extract_price
from .base import BaseScraper, _dig, _walk, merge_details, valid_point

logger = logging.getLogger(__name__)


class ImovelWebScraper(BaseScraper):

    def scrape_apartment(self, div_element) -> Optional[Dict]:  # pyright: ignore[reportIncompatibleMethodOverride] -- baseline: predates type checking  # sensors: function-lines=75, complexity=24, statements=55 -- baseline: predates sensors; lower via refactor-tick
        try:
            link = div_element.get("data-to-posting", "")
            if not link:
                link_elem = div_element.find("a", href=lambda x: x and "/propriedades/" in x if x else False)
                link = link_elem.get("href", "") if link_elem else ""

            if link:
                # The query carries per-position tracking params that break link-based dedup.
                link = urljoin("https://www.imovelweb.com.br", link.split("?", 1)[0])

            if not link:
                return None

            price_elem = div_element.find(attrs={"data-qa": "POSTING_CARD_PRICE"})
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = extract_price(price_text)

            expenses_elem = div_element.find(attrs={"data-qa": "expensas"})
            condo_fee = None
            iptu = None

            if expenses_elem:
                expenses_text = expenses_elem.get_text(strip=True)
                condo_match = re.search(r"R\$\s*([\d.]+)\s*Condominio", expenses_text, re.IGNORECASE)
                if condo_match:
                    condo_fee = extract_price(condo_match.group(0))

                iptu_match = re.search(r"R\$\s*([\d.]+)\s*IPTU", expenses_text, re.IGNORECASE)
                if iptu_match:
                    iptu = extract_price(iptu_match.group(0))

            location_elem = div_element.find(attrs={"data-qa": "POSTING_CARD_LOCATION"})
            neighborhood = ""
            city = ""

            if location_elem:
                location_text = location_elem.get_text(strip=True)
                location_match = re.search(r"([^,]+),\s*(.+)", location_text)
                if location_match:
                    neighborhood = location_match.group(1).strip()
                    city = location_match.group(2).strip()

            address_elem = div_element.find(
                class_=lambda x: x and "postingLocations-module__location-address" in x
            )
            street = address_elem.get_text(strip=True) if address_elem else ""

            features_elem = div_element.find("h3", {"data-qa": "POSTING_CARD_FEATURES"})
            area = None
            bedrooms = None
            bathrooms = None
            parking = None

            if features_elem:
                features_spans = features_elem.find_all(
                    "span", class_=lambda x: x and "postingMainFeatures-module__posting-main-features-span" in x
                )
                for span in features_spans:
                    text = span.get_text(strip=True).lower()
                    if "m²" in text or "tot" in text:
                        area = extract_number(text)
                    elif "quarto" in text:
                        bedrooms = extract_number(text)
                    elif "banheiro" in text:
                        bathrooms = extract_number(text)
                    elif "vaga" in text:
                        parking = extract_number(text)

            apartment = {
                "title": "",
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
            logger.error(f"Error processing ImovelWeb apartment: {e}")
            return None

    def page_details(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """Coordinates and description per posting id, from `window.__PRELOADED_STATE__`."""
        script = soup.find("script", id="preloadedData")
        source = (script.string or "") if script else ""
        try:
            state, _ = json.JSONDecoder().raw_decode(source, source.index("{"))
        except ValueError:
            return {}

        details: Dict[str, Dict] = {}
        for obj in _walk(state):
            location = obj.get("postingLocation")
            if not (obj.get("postingId") and isinstance(location, dict)):
                continue
            description = obj.get("descriptionNormalized")
            entry = {"description": description if isinstance(description, str) else ""}
            geolocation = _dig(location, "postingGeolocation", "geolocation")
            lat, lon = _dig(geolocation, "latitude"), _dig(geolocation, "longitude")
            if valid_point(lat, lon):
                entry.update(lat=lat, lon=lon)  # pyright: ignore[reportArgumentType] -- baseline: predates type checking
            details[str(obj["postingId"])] = entry
        return details

    def find_listing_elements(self, soup: BeautifulSoup) -> List:
        listing_elements = soup.find_all("div", {"data-qa": "posting PROPERTY"})

        if not listing_elements:
            listing_elements = soup.find_all(  # pyright: ignore[reportCallIssue] -- baseline: bs4 stubs reject lambda/attribute filters
                "div", class_=lambda x: x and "postingCardLayout-module__posting-card-layout" in x  # pyright: ignore[reportArgumentType] -- baseline: bs4 stubs reject lambda/attribute filters
            )

        return listing_elements

    def get_next_page_url(self, current_url: str, page_num: int) -> str:
        if page_num == 1:
            return current_url

        if "-pagina-" in current_url:
            return re.sub(r"-pagina-\d+", f"-pagina-{page_num}", current_url)
        elif current_url.endswith(".html"):
            return current_url.replace(".html", f"-pagina-{page_num}.html")
        elif "?" in current_url:
            return f"{current_url}&pagina={page_num}"
        else:
            return f"{current_url}?pagina={page_num}"

    def has_next_page(self, soup: BeautifulSoup) -> bool:  # sensors: complexity=23, nesting=6 -- baseline: predates sensors; lower via refactor-tick
        paging_container = soup.find("div", class_=lambda x: x and "paging-module__container-paging" in x)  # pyright: ignore[reportCallIssue, reportArgumentType] -- baseline: bs4 stubs reject lambda/attribute filters
        if paging_container:
            page_links = paging_container.find_all(
                "a", {"data-qa": lambda x: x and x.startswith("PAGING_") if x else False}
            )
            current_page_num = None
            max_page_num = None

            for link in page_links:
                data_qa = link.get("data-qa", "")
                if data_qa.startswith("PAGING_"):
                    try:
                        page_num_str = data_qa.replace("PAGING_", "")
                        if page_num_str.isdigit():
                            page_num = int(page_num_str)
                            classes = link.get("class", [])
                            if "paging-module__page-item-current" in str(classes):
                                current_page_num = page_num
                            if max_page_num is None or page_num > max_page_num:
                                max_page_num = page_num
                    except (ValueError, AttributeError):
                        pass

            if current_page_num is not None and max_page_num is not None:
                if current_page_num < max_page_num:
                    logger.debug(f"Current page: {current_page_num}, Max: {max_page_num}")
                    return True
                else:
                    logger.debug(f"Last page reached: {current_page_num}")
                    return False
            else:
                next_arrow = paging_container.find("a", {"data-qa": "PAGING_NEXT"})
                if next_arrow:
                    href = next_arrow.get("href", "")
                    classes = next_arrow.get("class", [])
                    disabled = (
                        "disabled" in str(classes)
                        or "paging-module__page-item-disabled" in str(classes)
                        or not href
                        or href == ""
                        or href == "#"
                    )
                    if not disabled and href and href != "#":
                        return True
                    else:
                        logger.debug("Next button disabled or no href")
                        return False
                else:
                    logger.debug("No next button found")
                    return False
        else:
            logger.debug("Pagination container not found")
            return False

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:  # sensors: function-lines=61, complexity=16, statements=54, nesting=5 -- baseline: predates sensors; lower via refactor-tick
        apartments = []
        page = 1
        previous_count = 0
        no_new_results_count = 0

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page} of ImovelWeb...")

                soup = BeautifulSoup(web.fetch_page(current_url), "lxml")
                details = self.page_details(soup)
                listing_elements = self.find_listing_elements(soup)
                current_count = len(listing_elements)

                if current_count == 0:
                    logger.info(f"No apartments found on page {page}. Finishing.")
                    break

                logger.info(f"Found {current_count} apartments on page {page}")

                page_apartments = []
                seen_links = set()
                for div_elem in listing_elements:
                    apartment = self.scrape_apartment(div_elem)
                    if apartment:
                        merge_details(apartment, details)
                        link = apartment.get("link", "")
                        if link and link not in seen_links:
                            seen_links.add(link)
                            page_apartments.append(apartment)

                if len(page_apartments) == 0:
                    no_new_results_count += 1
                    if no_new_results_count >= 2:
                        logger.info("No new apartments found in last 2 pages. Finishing.")
                        break
                else:
                    no_new_results_count = 0

                apartments.extend(page_apartments)
                logger.info(
                    f"Total accumulated ImovelWeb: {len(apartments)} apartments "
                    f"(new: {len(page_apartments)})\n"
                )

                if max_pages and page >= max_pages:
                    logger.info(f"Page limit of {max_pages} reached.")
                    break

                if current_count < previous_count:
                    logger.info("Number of results decreased. Finishing.")
                    break

                has_next = self.has_next_page(soup)

                if not has_next:
                    logger.info(f"No more pages available on ImovelWeb (current page: {page}).")
                    break

                previous_count = current_count
                page += 1
                time.sleep(1.5)

            except web.RequestException as e:
                logger.error(f"Error making request on page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Error processing page {page}: {e}")
                import traceback
                traceback.print_exc()
                break

        return apartments
