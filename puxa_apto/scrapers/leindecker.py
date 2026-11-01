import json
from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup

from ..utils.extractors import extract_number, extract_price
from .agency import AgencyScraper, card_code, fees, new_apartment, unique_texts


def _text(node, selector: str) -> str:
    element = node.select_one(selector)
    return element.get_text(" ", strip=True) if element else ""


def _items(card) -> Dict:
    """`ul.itens li`: "52m²", "2 dormitórios", "1 vaga"."""
    found = {}
    for li in card.select("ul.itens li"):
        text = li.get_text(" ", strip=True)
        if "m²" in text:
            found["area"] = extract_number(text)
        elif "dormit" in text:
            found["bedrooms"] = extract_number(text)
        elif "vaga" in text:
            found["parking"] = extract_number(text)
    return found


def _street(soup: BeautifulSoup) -> str:
    """From the listing's JSON-LD "address": "Rua Vasco da Gama - Bom Fim, Porto Alegre - RS".

    The agency's own address is a PostalAddress object, so only string addresses count.
    strict=False: descriptions carry raw newlines.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "", strict=False)
        except ValueError:
            continue
        address = data.get("address") if isinstance(data, dict) else None
        if isinstance(address, str):
            return address.split(" - ")[0].strip()
    return ""


class LeindeckerScraper(AgencyScraper):
    site = "leindecker"
    card_selector = "div.imovelb"

    def parse_card(self, card) -> Optional[Tuple[str, Dict]]:
        code = card_code(card)
        anchor = card.select_one(".title a[href]")
        if not (code and anchor):
            return None
        return code, new_apartment(
            title=anchor.get("title", ""),
            link=anchor["href"],
            neighborhood=_text(card, ".title h3 b"),
            price=extract_price(_text(card, "span.vals span")),
            **_items(card),
        )

    def parse_detail(self, soup: BeautifulSoup) -> Dict:
        details = fees(
            (li.small.get_text(strip=True), li.find("span").get_text(strip=True))
            for li in soup.select("li")
            if li.small and li.find("span")
        )
        description = soup.select_one("div.desc-ficha div.tex")
        if description:
            details["description"] = description.get_text("\n", strip=True)
        details["amenity_codes"] = unique_texts(soup.select("div.caracteristicas li"))
        street = _street(soup)
        if street:
            details["street"] = street
        return details
