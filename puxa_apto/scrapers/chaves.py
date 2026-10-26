
import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse, urljoin

from bs4 import BeautifulSoup

from ..utils import web
from ..utils.extractors import extract_number, extract_price

logger = logging.getLogger(__name__)


class ChavesScraper:
    def __init__(self, url: str):
        self.url = url

    def scrape_apartment(self, div_element) -> Optional[Dict]:
        try:
            link_elem = div_element.find("a", href=True)
            if not link_elem:
                return None

            link = link_elem.get("href", "")
            if not link.startswith("http"):
                link = urljoin("https://www.chavesnamao.com.br", link)

            title_elem = link_elem.find("h2", class_=lambda x: x and "styles_title__L3Xot" in x)
            title = title_elem.get_text(strip=True) if title_elem else ""

            address_elem = link_elem.find("address")
            street = ""
            neighborhood = ""
            city = ""

            if address_elem:
                address_ps = address_elem.find_all("p")
                if len(address_ps) >= 1:
                    street = address_ps[0].get_text(strip=True)
                if len(address_ps) >= 2:
                    location_text = address_ps[1].get_text(strip=True)
                    location_match = re.search(r"([^,]+),\s*(.+)", location_text)
                    if location_match:
                        neighborhood = location_match.group(1).strip()
                        city = re.sub(r"/[A-Z]{2}$", "", location_match.group(2).strip()).strip()

            area_elem = link_elem.find("p", title=lambda x: x and "área útil" in x.lower())
            area_text = area_elem.get_text(strip=True) if area_elem else ""
            area = extract_number(area_text)

            bedrooms_elem = link_elem.find("p", title=lambda x: x and "quarto" in x.lower())
            bedrooms_text = bedrooms_elem.get_text(strip=True) if bedrooms_elem else ""
            bedrooms = extract_number(bedrooms_text)

            bathrooms_elem = link_elem.find("p", title=lambda x: x and "banheiro" in x.lower())
            bathrooms_text = bathrooms_elem.get_text(strip=True) if bathrooms_elem else ""
            bathrooms = extract_number(bathrooms_text)

            parking_elem = link_elem.find("p", title=lambda x: x and "garage" in x.lower())
            parking_text = parking_elem.get_text(strip=True) if parking_elem else ""
            parking = extract_number(parking_text)

            price_elem = link_elem.find("p", class_=lambda x: x and "style_price__" in x)
            price_text = ""
            condo_fee = None
            iptu = None

            if price_elem:
                price_b = price_elem.find("b")
                if price_b:
                    price_text = price_b.get_text(strip=True)

                price_text_full = price_elem.get_text()

                condo_span = price_elem.find("span", {"aria-label": "Condomínio"})
                if condo_span:
                    condo_value_span = condo_span.find("span")
                    if condo_value_span:
                        condo_text = condo_value_span.get_text(strip=True)
                        condo_fee = extract_price(condo_text)

                iptu_match = re.search(r"Iptu[:\s]*R\$\s*([\d.]+)", price_text_full, re.IGNORECASE)
                if iptu_match:
                    iptu = extract_price(iptu_match.group(0))

            price = extract_price(price_text)

            # Most cards are streamed (React Suspense) and arrive without the detail
            # markup; their link title still carries the summary, e.g.
            # "... para alugar na Rua X, 80, Santa Cecília, Porto Alegre, 90 m2 por R$ 4.400"
            summary = link_elem.get("title", "")
            if price is None:
                price_match = re.search(r"por R\$\s*([\d.,]+)", summary)
                price = extract_price(price_match.group(1)) if price_match else None
            if area is None:
                area_match = re.search(r"(\d+)\s*m2", summary)
                area = int(area_match.group(1)) if area_match else None
            if bedrooms is None:
                bedrooms_match = re.search(r"(\d+)\s*quartos?", summary)
                bedrooms = int(bedrooms_match.group(1)) if bedrooms_match else None
            if not street:
                address_match = re.search(r"\bn[ao] (.+), ([^,]+), ([^,]+), \d+\s*m2", summary)
                if address_match:
                    street = address_match.group(1).strip()
                    neighborhood = address_match.group(2).strip()
                    city = address_match.group(3).strip()
            if not title:
                title = summary

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
            logger.error(f"Error processing Chaves na Mão apartment: {e}")
            return None

    def get_next_page_url(self, current_url: str, page_num: int) -> str:
        parsed = urlparse(current_url)
        query_params = parse_qs(parsed.query)
        query_params["pg"] = [str(page_num)]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def has_next_page(self, soup: BeautifulSoup, current_count: int, previous_count: int) -> bool:
        if current_count == 0:
            return False

        if current_count < previous_count:
            return False

        next_button = soup.find("a", string=lambda x: x and "Próxima" in x if x else False)
        if next_button:
            disabled = next_button.get("disabled") or "disabled" in str(next_button.get("class", []))
            if not disabled:
                return True

        pagination = soup.find("nav", class_=lambda x: x and "pagination" in str(x).lower() if x else False)
        if pagination:
            next_link = pagination.find("a", string=lambda x: x and ("Próxima" in x or ">" in x) if x else False)
            if next_link and not next_link.get("disabled"):
                return True

        return True

    @staticmethod
    def inline_streamed_segments(soup: BeautifulSoup) -> None:
        """Move React-streamed card details (hidden <div id="S:x">) into their <template id="P:x">.

        The browser does this swap client-side; without it, price and condo fee are missing
        from cards whose details arrive in a later stream chunk.
        """
        for template in soup.find_all("template", id=lambda x: x and x.startswith("P:")):
            segment = soup.find("div", id="S:" + template["id"][2:])
            if segment:
                template.replace_with(segment.extract())

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments = []
        page = 1
        previous_count = 0
        no_new_results_count = 0

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page} of Chaves na Mão...")

                soup = BeautifulSoup(web.fetch_page(current_url), "html.parser")
                self.inline_streamed_segments(soup)

                listing_elements = soup.find_all("div", {"data-template": "list"})
                current_count = len(listing_elements)

                if current_count == 0:
                    logger.info(f"No apartments found on page {page}. Finishing.")
                    break

                logger.info(f"Found {current_count} apartments on page {page}")

                page_apartments = []
                for div_elem in listing_elements:
                    apartment = self.scrape_apartment(div_elem)
                    if apartment:
                        link = apartment.get("link", "")
                        if not any(apt.get("link") == link for apt in apartments):
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
                    f"Total accumulated Chaves na Mão: {len(apartments)} apartments "
                    f"(new: {len(page_apartments)})\n"
                )

                if max_pages and page >= max_pages:
                    logger.info(f"Page limit of {max_pages} reached.")
                    break

                if current_count < previous_count or (current_count == previous_count and len(page_apartments) == 0):
                    logger.info("Number of results decreased or no new results. Finishing.")
                    break

                if not self.has_next_page(soup, current_count, previous_count) and len(page_apartments) == 0:
                    logger.info("No more pages available on Chaves na Mão.")
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
