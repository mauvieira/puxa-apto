
import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse, urljoin

import requests
from bs4 import BeautifulSoup

from ..config import DEFAULT_HEADERS
from ..utils.extractors import extract_number, extract_price

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logger = logging.getLogger(__name__)


class ChavesScraper:
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, use_selenium: bool = True):
        self.url = url
        self.headers = headers or DEFAULT_HEADERS
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE

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
                        city = location_match.group(2).strip().replace("/PR", "").strip()

            area_elem = link_elem.find("p", title=lambda x: x and "Área útil" in x if x else False)
            area_text = area_elem.get_text(strip=True) if area_elem else ""
            area = extract_number(area_text)

            bedrooms_elem = link_elem.find("p", title=lambda x: x and "Quartos" in x if x else False)
            bedrooms_text = bedrooms_elem.get_text(strip=True) if bedrooms_elem else ""
            bedrooms = extract_number(bedrooms_text)

            bathrooms_elem = link_elem.find("p", title=lambda x: x and "Banheiro" in x if x else False)
            bathrooms_text = bathrooms_elem.get_text(strip=True) if bathrooms_elem else ""
            bathrooms = extract_number(bathrooms_text)

            parking_elem = link_elem.find("p", title=lambda x: x and "Garagens" in x if x else False)
            parking_text = parking_elem.get_text(strip=True) if parking_elem else ""
            parking = extract_number(parking_text)

            price_elem = link_elem.find("p", class_=lambda x: x and "style_price__Dk6Z9" in x)
            price_text = ""
            condo_fee = None
            iptu = None

            if price_elem:
                price_b = price_elem.find("b")
                if price_b:
                    price_text = price_b.get_text(strip=True)

                price_text_full = price_elem.get_text()

                condo_span = price_elem.find("span", string=lambda x: x and "Condomínio" in x if x else False)
                if condo_span:
                    condo_value_span = condo_span.find_next("span")
                    if condo_value_span:
                        condo_text = condo_value_span.get_text(strip=True)
                        condo_fee = extract_price(condo_text)

                iptu_match = re.search(r"Iptu[:\s]*R\$\s*([\d.]+)", price_text_full, re.IGNORECASE)
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
            logger.error(f"Error processing Chaves na Mão apartment: {e}")
            return None

    def get_next_page_url(self, current_url: str, page_num: int) -> str:
        parsed = urlparse(current_url)
        query_params = parse_qs(parsed.query)

        filtro = query_params.get("filtro", [""])[0]
        if filtro:
            if "pagina%3A" in filtro:
                filtro = re.sub(r"pagina%3A\d+", f"pagina%3A{page_num}", filtro)
            else:
                filtro = f"{filtro}%2Cpagina%3A{page_num}"
        else:
            filtro = f"pagina%3A{page_num}"

        query_params["filtro"] = [filtro]
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)

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

    def scrape_selenium(self) -> List[Dict]:
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available. Trying alternative method...")
            return self.scrape_requests()

        logger.info("Using Selenium to load dynamic content...")
        apartments = []

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        driver = None
        try:
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as chrome_error:
                logger.error(f"Error starting ChromeDriver: {chrome_error}")
                logger.info("Trying alternative method without Selenium...")
                return self.scrape_requests()

            driver.get(self.url)

            logger.info("Waiting for initial load...")
            time.sleep(3)

            seen_ids = set()
            no_new_items_count = 0
            scroll_pause_time = 2.5
            max_scrolls = 25

            for scroll_attempt in range(max_scrolls):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause_time)

                soup = BeautifulSoup(driver.page_source, "html.parser")
                listing_elements = soup.find_all("div", {"data-template": "list"})

                new_items_count = 0
                for elem in listing_elements:
                    elem_id = elem.get("id", "")
                    if elem_id and elem_id not in seen_ids:
                        seen_ids.add(elem_id)
                        new_items_count += 1

                current_count = len(listing_elements)
                unique_count = len(seen_ids)

                logger.info(
                    f"Scroll {scroll_attempt + 1}: {current_count} visible elements, "
                    f"{unique_count} unique (new: {new_items_count})"
                )

                if new_items_count == 0:
                    no_new_items_count += 1
                    if no_new_items_count >= 3:
                        logger.info("No new elements loaded in last 3 attempts. Finishing scroll.")
                        break
                else:
                    no_new_items_count = 0

                if unique_count >= 100:
                    logger.info("Safety limit reached (100+ unique elements). Finishing.")
                    break

                if scroll_attempt > 0 and scroll_attempt % 5 == 0:
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(scroll_pause_time)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            listing_elements = soup.find_all("div", {"data-template": "list"})

            logger.info(f"\nProcessing {len(listing_elements)} apartments found...")

            seen_links = set()
            for div_elem in listing_elements:
                apartment = self.scrape_apartment(div_elem)
                if apartment:
                    link = apartment.get("link", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        apartments.append(apartment)

            logger.info(f"Total unique apartments: {len(apartments)}")

        except Exception as e:
            logger.error(f"Error using Selenium: {e}")
            import traceback
            traceback.print_exc()
            logger.info("Trying alternative method without Selenium...")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            return self.scrape_requests()
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

        return apartments

    def scrape_requests(self, max_pages: Optional[int] = None) -> List[Dict]:
        apartments = []
        page = 1
        previous_count = 0
        no_new_results_count = 0

        while True:
            try:
                current_url = self.get_next_page_url(self.url, page) if page > 1 else self.url
                logger.info(f"Processing page {page} of Chaves na Mão...")

                response = requests.get(current_url, headers=self.headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "html.parser")

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

            except requests.RequestException as e:
                logger.error(f"Error making request on page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Error processing page {page}: {e}")
                import traceback
                traceback.print_exc()
                break

        return apartments

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]:
        if self.use_selenium:
            return self.scrape_selenium()
        else:
            return self.scrape_requests(max_pages)
