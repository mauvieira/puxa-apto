import re
import unicodedata
from math import cos, radians
from typing import Callable, Dict, List
from urllib.parse import urlencode

from .settings import Point, SearchSettings

SITES = ("vivareal", "chaves", "imovelweb", "zap")


def slugify(text: str) -> str:
    """"Santa Cecília" -> "santa-cecilia"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def viewport(center: Point, radius_km: float) -> str:
    """Bounding box around center as VivaReal/Zap expect it: east,north|west,south."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * cos(radians(center.lat)))
    return (
        f"{center.lon + dlon:.4f},{center.lat + dlat:.4f}"
        f"|{center.lon - dlon:.4f},{center.lat - dlat:.4f}"
    )


def _map_query(settings: SearchSettings) -> str:
    params = {
        "transacao": settings.transaction,
        "tipos": "apartamento_residencial",
        "viewport": viewport(settings.center, settings.radius_km),
    }
    if settings.max_price is not None:
        params["precoMaximo"] = int(settings.max_price)
    if settings.min_area is not None:
        params["areaMinima"] = settings.min_area
    if settings.bedrooms:
        params["quartos"] = ",".join(str(b) for b in sorted(settings.bedrooms))
    return urlencode(params)


def _vivareal(settings: SearchSettings) -> List[str]:
    if settings.center is None:
        return []
    return [
        f"https://www.vivareal.com.br/{settings.transaction}/brasil/apartamento_residencial/?"
        + _map_query(settings)
    ]


def _zap(settings: SearchSettings) -> List[str]:
    if settings.center is None:
        return []
    return [f"https://www.zapimoveis.com.br/{settings.transaction}/?" + _map_query(settings)]


def _chaves(settings: SearchSettings) -> List[str]:
    if not settings.neighborhoods:
        return []
    segment = {"aluguel": "apartamentos-para-alugar", "venda": "apartamentos-a-venda"}[
        settings.transaction
    ]
    place = f"{settings.state.lower()}-{slugify(settings.city)}"
    return [
        f"https://www.chavesnamao.com.br/{segment}/{place}/{slugify(n)}/"
        for n in settings.neighborhoods
    ]


def _imovelweb(settings: SearchSettings) -> List[str]:
    if not settings.neighborhoods:
        return []
    city = slugify(settings.city)
    slug = "-".join(f"{slugify(n)}-{city}" for n in settings.neighborhoods)
    return [f"https://www.imovelweb.com.br/apartamentos-{settings.transaction}-{slug}.html"]


_URL_BUILDERS: Dict[str, Callable[[SearchSettings], List[str]]] = {
    "vivareal": _vivareal,
    "zap": _zap,
    "chaves": _chaves,
    "imovelweb": _imovelweb,
}


def resolve_urls(site: str, settings: SearchSettings, cli_urls: List[str]) -> List[str]:
    """CLI URLs win over configured URLs, which win over URLs built from the search area."""
    return cli_urls or getattr(settings.urls, site) or _URL_BUILDERS[site](settings)


def apply_criteria(apartments: List[Dict], settings: SearchSettings) -> List[Dict]:
    """Drop listings whose known values violate the filters; unknown values are kept."""
    excluded = {slugify(n) for n in settings.exclude_neighborhoods}

    def keep(apt: Dict) -> bool:
        if slugify(apt.get("neighborhood") or "") in excluded:
            return False
        price, area, bedrooms = apt.get("price"), apt.get("area"), apt.get("bedrooms")
        if settings.max_price is not None and price is not None and price > settings.max_price:
            return False
        if settings.min_area is not None and area is not None and area < settings.min_area:
            return False
        if settings.bedrooms and bedrooms is not None and bedrooms not in settings.bedrooms:
            return False
        return True

    return [apt for apt in apartments if keep(apt)]
