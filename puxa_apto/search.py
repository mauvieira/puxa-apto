from math import asin, cos, radians, sin, sqrt
from typing import Callable, Dict, List, Optional
from urllib.parse import urlencode

from .settings import Place, Point, SearchSettings
from .utils.text import slugify

SITES = ("vivareal", "chaves", "imovelweb", "zap")
EARTH_RADIUS_KM = 6371.0


def distance_column(place: Place) -> str:
    """"Campus Saúde" -> "distance_km_campus_saude"."""
    return "distance_km_" + slugify(place.name).replace("-", "_")


def haversine_km(a: Point, lat: float, lon: float) -> float:
    dlat, dlon = radians(lat - a.lat), radians(lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(lat)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def viewport(places: List[Point], radius_km: float) -> str:
    """Box covering radius_km around every place, as VivaReal/Zap expect it: east,north|west,south."""
    dlat = radius_km / 111.32
    east = max(p.lon + radius_km / (111.32 * cos(radians(p.lat))) for p in places)
    west = min(p.lon - radius_km / (111.32 * cos(radians(p.lat))) for p in places)
    north = max(p.lat for p in places) + dlat
    south = min(p.lat for p in places) - dlat
    return f"{east:.4f},{north:.4f}|{west:.4f},{south:.4f}"


def _price_cap(settings: SearchSettings) -> Optional[float]:
    """The tightest rent cap to send to the sites. Rent <= total, so max_total caps rent too."""
    caps = [c for c in (settings.max_price, settings.max_total) if c is not None]
    return min(caps) if caps else None


def _map_query(settings: SearchSettings) -> str:
    params = {
        "transacao": settings.transaction,
        "tipos": "apartamento_residencial",
        "viewport": viewport(settings.places, settings.radius_km),
    }
    cap = _price_cap(settings)
    if cap is not None:
        params["precoMaximo"] = int(cap)
    if settings.min_area is not None:
        params["areaMinima"] = settings.min_area
    if settings.bedrooms:
        params["quartos"] = ",".join(str(b) for b in sorted(settings.bedrooms))
    return urlencode(params)


def _vivareal(settings: SearchSettings) -> List[str]:
    if not settings.places:
        return []
    return [
        f"https://www.vivareal.com.br/{settings.transaction}/brasil/apartamento_residencial/?"
        + _map_query(settings)
    ]


def _zap(settings: SearchSettings) -> List[str]:
    if not settings.places:
        return []
    return [f"https://www.zapimoveis.com.br/{settings.transaction}/?" + _map_query(settings)]


def _chaves(settings: SearchSettings) -> List[str]:
    if not settings.neighborhoods:
        return []
    segment = {"aluguel": "apartamentos-para-alugar", "venda": "apartamentos-a-venda"}[
        settings.transaction
    ]
    place = f"{settings.state.lower()}-{slugify(settings.city)}"
    cap = _price_cap(settings)
    parts = []
    if cap is not None:
        parts.append(f"pmax:{int(cap)}")
    if settings.min_area is not None:
        parts.append(f"amin:{settings.min_area}")
    query = "?" + urlencode({"filtro": ",".join(parts)}) if parts else ""
    return [
        f"https://www.chavesnamao.com.br/{segment}/{place}/{slugify(n)}/{query}"
        for n in settings.neighborhoods
    ]


def _imovelweb(settings: SearchSettings) -> List[str]:
    if not settings.neighborhoods:
        return []
    city = slugify(settings.city)
    slug = "-".join(f"{slugify(n)}-{city}" for n in settings.neighborhoods)
    cap = _price_cap(settings)
    filters = []
    if len(settings.bedrooms) == 1:
        filters.append(f"{settings.bedrooms[0]}-quartos")  # ImovelWeb's N-quartos means exactly N
    if settings.min_area is not None:
        filters.append(f"mais-{settings.min_area}-m2-util")
    if cap is not None:
        filters.append(f"menos-{int(cap)}-reales")
    suffix = "".join("-" + f for f in filters)
    return [f"https://www.imovelweb.com.br/apartamentos-{settings.transaction}-{slug}{suffix}.html"]


_URL_BUILDERS: Dict[str, Callable[[SearchSettings], List[str]]] = {
    "vivareal": _vivareal,
    "zap": _zap,
    "chaves": _chaves,
    "imovelweb": _imovelweb,
}


def resolve_urls(site: str, settings: SearchSettings, cli_urls: List[str]) -> List[str]:
    """CLI URLs win over configured URLs, which win over URLs built from the search area."""
    return cli_urls or getattr(settings.urls, site) or _URL_BUILDERS[site](settings)


def annotate(apartments: List[Dict], settings: SearchSettings) -> None:
    """Add total_price (rent + condo), each listing's distance to every place, and to the
    nearest one (`distance_km`)."""
    columns = [(place, distance_column(place)) for place in settings.places]
    for apt in apartments:
        price = apt.get("price")
        apt["total_price"] = price + (apt.get("condo_fee") or 0) if price is not None else None
        lat, lon = apt.get("lat"), apt.get("lon")
        known = lat is not None and lon is not None
        for place, column in columns:
            apt[column] = round(haversine_km(place, lat, lon), 2) if known else None
        distances = [apt[column] for _, column in columns if apt[column] is not None]
        apt["distance_km"] = min(distances) if distances else None


def apply_criteria(apartments: List[Dict], settings: SearchSettings) -> List[Dict]:
    """Drop listings whose known values violate the filters or lie beyond radius_km of every
    place; unknown values are kept."""
    excluded = {slugify(n) for n in settings.exclude_neighborhoods}

    def keep(apt: Dict) -> bool:
        if slugify(apt.get("neighborhood") or "") in excluded:
            return False
        price, area, bedrooms = apt.get("price"), apt.get("area"), apt.get("bedrooms")
        distance, total = apt.get("distance_km"), apt.get("total_price")
        if settings.places and distance is not None and distance > settings.radius_km:
            return False
        if settings.max_price is not None and price is not None and price > settings.max_price:
            return False
        if settings.max_total is not None and total is not None and total > settings.max_total:
            return False
        if settings.min_area is not None and area is not None and area < settings.min_area:
            return False
        if settings.bedrooms and bedrooms is not None and bedrooms not in settings.bedrooms:
            return False
        return True

    return [apt for apt in apartments if keep(apt)]
