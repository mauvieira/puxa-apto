from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup

from ..utils.extractors import extract_number, extract_price
from .agency import AgencyScraper, card_code, fees, new_apartment, unique_texts


def _text(node, selector: str) -> str:
    element = node.select_one(selector)
    return element.get_text(" ", strip=True) if element else ""


def _items(card) -> Dict:
    """`p.its`: "3 quartos • 77m² • 1 vaga"."""
    found = {}
    for item in _text(card, "p.its").split("•"):
        if "m²" in item:
            found["area"] = extract_number(item)
        elif "quarto" in item:
            found["bedrooms"] = extract_number(item)
        elif "vaga" in item:
            found["parking"] = extract_number(item)
    return found


def _street(soup: BeautifulSoup) -> str:
    """`span.titulomapa`: "Localização" then "General João Telles, 165 - Bom Fim, Porto Alegre"."""
    span = soup.select_one("span.titulomapa")
    lines = span.get_text("\n", strip=True).splitlines() if span else []
    return lines[-1].split(" - ")[0].strip() if lines else ""


def _fee_pair(li) -> Tuple[str, str]:
    return li.select_one("span.left").get_text(strip=True), li.select_one("span.right").get_text(strip=True)


class CertaScraper(AgencyScraper):
    site = "certa"
    card_selector = "div.div_imovel"

    def parse_card(self, card) -> Optional[Tuple[str, Dict]]:
        code = card_code(card)
        anchor = card.select_one('a[href*="/imovel/"]')
        if not (code and anchor):
            return None  # also the empty placeholder card each page has
        return code, new_apartment(
            title=anchor.get("title", ""),
            link=anchor["href"],
            neighborhood=_text(card, "h3"),
            price=extract_price(_text(card, "div.va")),
            **_items(card),
        )

    def parse_detail(self, soup: BeautifulSoup) -> Dict:
        details = fees(
            _fee_pair(li)
            for li in soup.select("li")
            if li.select_one("span.left") and li.select_one("span.right")
        )
        description = soup.select_one("div.texto-ficha")
        if description:
            details["description"] = description.get_text("\n", strip=True)
        details["amenity_codes"] = unique_texts(soup.select("div.infra ul.checks li"))
        street = _street(soup)
        if street:
            details["street"] = street
        return details
