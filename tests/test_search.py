import os
from math import acos, cos, radians, sin
from urllib.parse import parse_qs, urlsplit

import pytest

from puxa_apto.search import (
    annotate,
    apply_criteria,
    distance_column,
    haversine_km,
    viewport,
)
from puxa_apto.settings import Place, Point, SearchSettings
from puxa_apto.sites import resolve_urls

FAMED = Place(name="Famed", lat=-30.0330, lon=-51.2070)
PORTO_ALEGRE = {"state": "RS", "city": "Porto Alegre", "neighborhoods": ["Santa Cecília", "Bom Fim"]}


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """SearchSettings reads PUXA_* env vars and .env; keep both out of these tests."""
    for name in list(os.environ):
        if name.startswith("PUXA_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


def settings(**values) -> SearchSettings:
    return SearchSettings(**values)


def built(site, **values):
    return resolve_urls(site, settings(**values), [])


def query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# --- geometry ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "column"),
    [
        ("Famed", "distance_km_famed"),
        ("Campus Saúde", "distance_km_campus_saude"),
        ("Hospital de Clínicas - HCPA", "distance_km_hospital_de_clinicas_hcpa"),
    ],
)
def test_distance_column_is_a_snake_case_ascii_name(name, column):
    assert distance_column(Place(name=name, lat=0, lon=0)) == column


def spherical_law_of_cosines_km(lat1, lon1, lat2, lon2):
    p1, p2 = radians(lat1), radians(lat2)
    return 6371.0 * acos(min(1.0, sin(p1) * sin(p2) + cos(p1) * cos(p2) * cos(radians(lon2 - lon1))))


@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param((0, 0), (1, 0), id="one-degree-of-latitude"),
        pytest.param((60, 10), (60, 11), id="one-degree-of-longitude-at-60N"),
        pytest.param((-30.0330, -51.2070), (-30.0369, -51.2098), id="famed-to-hps"),
        pytest.param((-30.0330, -51.2070), (-25.4284, -49.2733), id="porto-alegre-to-curitiba"),
    ],
)
def test_haversine_matches_the_great_circle_distance(a, b):
    expected = spherical_law_of_cosines_km(*a, *b)
    assert haversine_km(Point(lat=a[0], lon=a[1]), *b) == pytest.approx(expected, rel=1e-6)
    assert haversine_km(Point(lat=b[0], lon=b[1]), *a) == pytest.approx(expected, rel=1e-6)


def test_haversine_of_a_point_to_itself_is_zero():
    assert haversine_km(FAMED, FAMED.lat, FAMED.lon) == 0


@pytest.mark.parametrize(
    ("places", "box"),
    [
        pytest.param([(0, 0)], "1.0000,1.0000|-1.0000,-1.0000", id="equator"),
        pytest.param([(60, 10)], "12.0000,61.0000|8.0000,59.0000", id="longitude-widens-with-latitude"),
        pytest.param([(0, 10.5), (60, 10)], "12.0000,61.0000|8.0000,-1.0000", id="covers-every-place"),
    ],
)
def test_viewport_is_east_north_west_south_around_every_place(places, box):
    # 111.32 km is one degree of latitude, so the box extends exactly one degree north/south.
    assert viewport([Point(lat=lat, lon=lon) for lat, lon in places], 111.32) == box


# --- URL resolution ----------------------------------------------------------------------


def test_cli_urls_beat_configured_urls_which_beat_built_ones():
    configured = settings(places=[FAMED], urls={"vivareal": ["https://configured"]})
    plain = settings(places=[FAMED])

    assert resolve_urls("vivareal", configured, ["https://cli"]) == ["https://cli"]
    assert resolve_urls("vivareal", configured, []) == ["https://configured"]
    assert resolve_urls("vivareal", plain, []) == built("vivareal", places=[FAMED])
    assert resolve_urls("zap", configured, []) == built("zap", places=[FAMED])


@pytest.mark.parametrize(
    ("site", "transaction", "prefix"),
    [
        ("vivareal", "aluguel", "https://www.vivareal.com.br/aluguel/brasil/apartamento_residencial/?"),
        ("vivareal", "venda", "https://www.vivareal.com.br/venda/brasil/apartamento_residencial/?"),
        ("zap", "aluguel", "https://www.zapimoveis.com.br/aluguel/?"),
        ("zap", "venda", "https://www.zapimoveis.com.br/venda/?"),
    ],
)
def test_map_portals_search_the_viewport_around_the_places(site, transaction, prefix):
    places: list[Point] = [FAMED, Place(name="HPS", lat=-30.0369, lon=-51.2098)]

    (url,) = built(site, transaction=transaction, places=places, radius_km=2)

    assert url.startswith(prefix)
    assert query(url) == {
        "transacao": transaction,
        "tipos": "apartamento_residencial",
        "viewport": viewport(places, 2),
    }


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        pytest.param({"max_price": 3000}, {"precoMaximo": "3000"}, id="max-price"),
        pytest.param({"max_total": 1800}, {"precoMaximo": "1800"}, id="max-total-caps-rent"),
        pytest.param({"max_price": 3000, "max_total": 1800}, {"precoMaximo": "1800"}, id="tighter-total"),
        pytest.param({"max_price": 1500, "max_total": 1800}, {"precoMaximo": "1500"}, id="tighter-price"),
        pytest.param({"max_price": 2500.9}, {"precoMaximo": "2500"}, id="cap-truncated"),
        pytest.param({"min_area": 40}, {"areaMinima": "40"}, id="min-area"),
        pytest.param({"bedrooms": [3, 1]}, {"quartos": "1,3"}, id="bedrooms-sorted"),
    ],
)
def test_map_portal_filters(filters, expected):
    for site in ("vivareal", "zap"):
        (url,) = built(site, places=[FAMED], **filters)
        filter_params = {k: v for k, v in query(url).items() if k not in ("transacao", "tipos", "viewport")}
        assert filter_params == expected


@pytest.mark.parametrize("site", ["vivareal", "zap"])
def test_map_portals_need_places(site):
    assert built(site, **PORTO_ALEGRE) == []


@pytest.mark.parametrize(
    ("values", "urls"),
    [
        pytest.param(
            {"transaction": "aluguel"},
            [
                "https://www.chavesnamao.com.br/apartamentos-para-alugar/rs-porto-alegre/santa-cecilia/",
                "https://www.chavesnamao.com.br/apartamentos-para-alugar/rs-porto-alegre/bom-fim/",
            ],
            id="rent-one-url-per-neighborhood",
        ),
        pytest.param(
            {"transaction": "venda", "max_price": 500000, "max_total": 600000, "min_area": 40},
            [
                "https://www.chavesnamao.com.br/apartamentos-a-venda/rs-porto-alegre/santa-cecilia/?filtro=pmax%3A500000%2Camin%3A40",
                "https://www.chavesnamao.com.br/apartamentos-a-venda/rs-porto-alegre/bom-fim/?filtro=pmax%3A500000%2Camin%3A40",
            ],
            id="sale-with-filters",
        ),
        pytest.param(
            {"transaction": "aluguel", "min_area": 40, "neighborhoods": ["Bom Fim"]},
            ["https://www.chavesnamao.com.br/apartamentos-para-alugar/rs-porto-alegre/bom-fim/?filtro=amin%3A40"],
            id="area-only",
        ),
    ],
)
def test_chaves_urls(values, urls):
    assert built("chaves", **{**PORTO_ALEGRE, **values}) == urls


@pytest.mark.parametrize(
    ("values", "url"),
    [
        pytest.param(
            {"transaction": "aluguel"},
            "https://www.imovelweb.com.br/apartamentos-aluguel-santa-cecilia-porto-alegre-bom-fim-porto-alegre.html",
            id="all-neighborhoods-in-one-url",
        ),
        pytest.param(
            {"transaction": "venda", "bedrooms": [2], "min_area": 40, "max_total": 1800},
            "https://www.imovelweb.com.br/apartamentos-venda-santa-cecilia-porto-alegre-bom-fim-porto-alegre"
            "-2-quartos-mais-40-m2-util-menos-1800-reales.html",
            id="filters",
        ),
        pytest.param(
            {"transaction": "aluguel", "bedrooms": [1, 2]},
            "https://www.imovelweb.com.br/apartamentos-aluguel-santa-cecilia-porto-alegre-bom-fim-porto-alegre.html",
            id="several-bedroom-counts-not-sent",
        ),
    ],
)
def test_imovelweb_url(values, url):
    assert built("imovelweb", **{**PORTO_ALEGRE, **values}) == [url]


@pytest.mark.parametrize("site", ["chaves", "imovelweb", "leindecker", "certa"])
def test_neighborhood_sites_need_neighborhoods(site):
    assert built(site, transaction="aluguel", state="RS", city="Porto Alegre", places=[FAMED]) == []


LEINDECKER_RENT = (
    "https://www.leindecker.com.br/busca/alugar/cidade/porto-alegre/bairros/santa-cecilia_bom-fim"
    "/categorias/apartamentos_jk-lofts_studios/"
)
CERTA_RENT = (
    "https://www.certa.com.br/busca/alugar/categorias/apartamentos_kitnet-jk_studios/bairros/"
    "santa-cecilia-porto-alegre_bom-fim-porto-alegre/"
)


@pytest.mark.parametrize(
    ("site", "values", "url"),
    [
        pytest.param("leindecker", {}, LEINDECKER_RENT + "1/", id="leindecker"),
        pytest.param(
            "leindecker",
            {"max_price": 2000, "max_total": 1800, "min_area": 40, "bedrooms": [3, 2]},
            LEINDECKER_RENT + "valor_ate/1800/area/40/dormitorios/2/1/",
            id="leindecker-filters",
        ),
        pytest.param("leindecker", {"bedrooms": [2]}, LEINDECKER_RENT + "dormitorios/2/1/", id="leindecker-bedrooms"),
        pytest.param(
            "leindecker",
            {"transaction": "venda"},
            "https://www.leindecker.com.br/busca/comprar/cidade/porto-alegre/bairros/santa-cecilia_bom-fim"
            "/categorias/apartamentos_jk-loft-kitnet/1/",
            id="leindecker-sale",
        ),
        pytest.param(
            "leindecker",
            {"city": "porto alegre", "state": "rs"},
            LEINDECKER_RENT + "1/",
            id="leindecker-lowercase-city-and-state",
        ),
        pytest.param("certa", {}, CERTA_RENT + "1/", id="certa"),
        pytest.param(
            "certa",
            {"max_price": 1800, "min_area": 40, "bedrooms": [2, 3]},
            CERTA_RENT + "valor_ate/1800/area/40/quartos/2/1/",
            id="certa-filters",
        ),
    ],
)
def test_agency_urls(site, values, url):
    assert built(site, **{**PORTO_ALEGRE, "transaction": "aluguel", **values}) == [url]


@pytest.mark.parametrize(
    ("site", "values"),
    [
        pytest.param("leindecker", {"city": "Curitiba", "state": "PR"}, id="leindecker-other-city"),
        pytest.param("leindecker", {"state": "SC"}, id="leindecker-other-state"),
        pytest.param("certa", {"city": "Curitiba", "state": "PR"}, id="certa-other-city"),
        pytest.param("certa", {"state": "SC"}, id="certa-other-state"),
        pytest.param("certa", {"transaction": "venda"}, id="certa-sale"),
    ],
)
def test_agencies_search_only_porto_alegre_and_certa_only_rentals(site, values):
    assert built(site, **{**PORTO_ALEGRE, "transaction": "aluguel", **values}) == []


# --- annotate ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fees", "total"),
    [
        pytest.param({"price": 2000.0, "condo_fee": 450.0}, 2450.0, id="rent-plus-condo"),
        pytest.param({"price": 2000.0, "condo_fee": None}, 2000.0, id="unknown-condo-counts-as-zero"),
        pytest.param({"price": 2000.0}, 2000.0, id="missing-condo-counts-as-zero"),
        pytest.param({"price": None, "condo_fee": 450.0}, None, id="unknown-rent"),
    ],
)
def test_total_price_is_rent_plus_condo(fees, total):
    apt = dict(fees)
    annotate([apt], settings())
    assert apt["total_price"] == total


def test_distances_to_every_place_and_to_the_nearest_are_added_in_km():
    near = Place(name="Near", lat=-30.0, lon=-51.0)
    far = Place(name="Far Place", lat=-30.02, lon=-51.0)
    apt = {"price": None, "lat": -30.005, "lon": -51.0}  # 0.005 and 0.015 degrees of latitude away

    annotate([apt], settings(places=[far, near]))

    assert apt["distance_km_near"] == 0.56
    assert apt["distance_km_far_place"] == 1.67
    assert apt["distance_km"] == 0.56


@pytest.mark.parametrize(
    "coordinates",
    [{"lat": -30.0, "lon": None}, {"lat": None, "lon": -51.0}, {}],
    ids=["no-lon", "no-lat", "none"],
)
def test_a_listing_without_coordinates_has_unknown_distances(coordinates):
    apt = {"price": 1000.0, **coordinates}

    annotate([apt], settings(places=[FAMED]))

    assert apt["distance_km_famed"] is None
    assert apt["distance_km"] is None


def test_without_places_there_is_no_distance():
    apt = {"price": 1000.0, "lat": -30.0, "lon": -51.0}

    annotate([apt], settings())

    assert apt["distance_km"] is None
    assert not [k for k in apt if k.startswith("distance_km_")]


# --- apply_criteria ----------------------------------------------------------------------

LISTING = {
    "neighborhood": "Bom Fim",
    "price": 2000.0,
    "total_price": 2400.0,
    "area": 45,
    "bedrooms": 2,
    "distance_km": 1.0,
}


@pytest.mark.parametrize(
    ("filters", "changes", "kept"),
    [
        pytest.param({}, {}, True, id="no-filters"),
        pytest.param({}, dict.fromkeys(LISTING), True, id="no-filters-nothing-known"),
        pytest.param({"exclude_neighborhoods": ["centro historico"]}, {"neighborhood": "Centro Histórico"}, False, id="excluded-despite-accent"),
        pytest.param({"exclude_neighborhoods": ["Centro Histórico"]}, {"neighborhood": "CENTRO HISTORICO"}, False, id="excluded-despite-case"),
        pytest.param({"exclude_neighborhoods": ["centro historico"]}, {}, True, id="other-neighborhood"),
        pytest.param({"exclude_neighborhoods": ["centro historico"]}, {"neighborhood": None}, True, id="unknown-neighborhood"),
        pytest.param({"places": [FAMED], "radius_km": 1.0}, {}, True, id="distance-equal-to-radius"),
        pytest.param({"places": [FAMED], "radius_km": 1.0}, {"distance_km": 1.01}, False, id="distance-over-radius"),
        pytest.param({"places": [FAMED]}, {"distance_km": None}, False, id="unknown-distance-with-places"),
        pytest.param({}, {"distance_km": 50.0}, True, id="distance-ignored-without-places"),
        pytest.param({"max_price": 2000}, {}, True, id="price-equal-to-max"),
        pytest.param({"max_price": 1999}, {}, False, id="price-over-max"),
        pytest.param({"max_price": 1000}, {"price": None}, True, id="unknown-price"),
        pytest.param({"max_total": 2400}, {}, True, id="total-equal-to-max"),
        pytest.param({"max_total": 2399}, {}, False, id="total-over-max-though-rent-under"),
        pytest.param({"max_total": 1000}, {"total_price": None}, True, id="unknown-total"),
        pytest.param({"min_area": 45}, {}, True, id="area-equal-to-min"),
        pytest.param({"min_area": 46}, {}, False, id="area-under-min"),
        pytest.param({"min_area": 100}, {"area": None}, True, id="unknown-area"),
        pytest.param({"bedrooms": [1, 2]}, {}, True, id="bedrooms-listed"),
        pytest.param({"bedrooms": [1, 3]}, {}, False, id="bedrooms-not-listed"),
        pytest.param({"bedrooms": [1]}, {"bedrooms": None}, True, id="unknown-bedrooms"),
    ],
)
def test_apply_criteria(filters, changes, kept):
    apt = {**LISTING, **changes}
    assert apply_criteria([apt], settings(**filters)) == ([apt] if kept else [])


def test_apply_criteria_keeps_the_order_of_the_survivors():
    cheap, pricey, also_cheap = (dict(LISTING, price=p) for p in (1000.0, 5000.0, 1500.0))
    assert apply_criteria([cheap, pricey, also_cheap], settings(max_price=2000)) == [cheap, also_cheap]
