import pytest

from puxa_apto.models.apartment import Apartment
from puxa_apto.utils.fingerprint import (
    create_apartment_fingerprint,
    drop_cross_posts,
    filter_new_apartments,
)

VIVAREAL_LINK = "https://www.vivareal.com.br/imovel/apartamento-1-quarto-bom-fim-porto-alegre-45m2-aluguel-id-1/"
ZAP_LINK = "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-1-quarto-bom-fim-porto-alegre-45m2-id-2/"
LEINDECKER_LINK = "https://www.leindecker.com.br/imovel/apartamento-bom-fim-porto-alegre/1234/"
CERTA_LINK = "https://www.certa.com.br/imovel/apartamento-bom-fim-porto-alegre/5678/"


def listing(**changes):
    apt = {
        "link": VIVAREAL_LINK,
        "agency_ref": None,
        "street": "Rua Ramiro Barcelos, 1954",
        "neighborhood": "Bom Fim",
        "city": "Porto Alegre",
        "area": 45,
        "bedrooms": 1,
        "price": 2400.0,
    }
    apt.update(changes)
    return apt


# --- create_apartment_fingerprint -------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"link": ZAP_LINK, "city": "POA"}, id="link-and-city-ignored"),
        pytest.param({"street": "  RUA RAMIRO BARCELOS, 1954 ", "neighborhood": " BOM FIM"}, id="case-and-padding"),
        pytest.param({"street": "Rua  Ramiro   Barcelos 1954"}, id="punctuation-and-spacing"),
        pytest.param({"street": "Rua Ramiro Barcelos, 2010 apto 301"}, id="only-first-three-street-words"),
        pytest.param({"area": 45.0}, id="float-area"),
        pytest.param({"price": 1600.0}, id="price-rounds-to-same-thousand"),
    ],
)
def test_the_same_apartment_listed_differently_shares_a_fingerprint(changes):
    for require_all_fields in (False, True):
        assert create_apartment_fingerprint(listing(**changes), require_all_fields) == create_apartment_fingerprint(
            listing(), require_all_fields
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param({}, {"street": "Rua Fernandes Vieira, 1954"}, id="street"),
        pytest.param({}, {"neighborhood": "Santana"}, id="neighborhood"),
        pytest.param({}, {"area": 46}, id="area"),
        pytest.param({}, {"bedrooms": 2}, id="bedrooms"),
        pytest.param({"price": 2499.0}, {"price": 2501.0}, id="price-across-thousand-boundary"),
        pytest.param({"area": None}, {}, id="area-unknown-vs-known"),
    ],
)
def test_different_apartments_get_different_fingerprints(first, second):
    assert create_apartment_fingerprint(listing(**first)) != create_apartment_fingerprint(listing(**second))


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"street": ""}, id="empty-street"),
        pytest.param({"street": "   "}, id="blank-street"),
        pytest.param({"street": "!!!"}, id="street-only-punctuation"),
        pytest.param({"neighborhood": ""}, id="empty-neighborhood"),
        pytest.param({"neighborhood": " -- "}, id="neighborhood-only-punctuation"),
    ],
)
def test_a_listing_without_street_and_neighborhood_has_no_fingerprint(changes):
    assert create_apartment_fingerprint(listing(**changes)) is None
    assert create_apartment_fingerprint(listing(**changes), require_all_fields=True) is None


@pytest.mark.parametrize("missing", ["street", "neighborhood"])
def test_a_listing_missing_the_address_key_has_no_fingerprint(missing):
    apt = listing()
    del apt[missing]
    assert create_apartment_fingerprint(apt) is None


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"area": None}, id="no-area"),
        pytest.param({"area": 0}, id="zero-area"),
        pytest.param({"bedrooms": None}, id="no-bedrooms"),
        pytest.param({"price": None}, id="no-price"),
        pytest.param({"price": 0.0}, id="zero-price"),
    ],
)
def test_requiring_all_fields_rejects_an_incomplete_listing_that_still_has_a_partial_fingerprint(changes):
    apt = listing(**changes)
    assert create_apartment_fingerprint(apt, require_all_fields=True) is None
    assert create_apartment_fingerprint(apt) is not None


def test_a_complete_listing_has_the_same_fingerprint_whether_or_not_all_fields_are_required():
    assert create_apartment_fingerprint(listing(), require_all_fields=True) == create_apartment_fingerprint(listing())


def test_an_apartment_model_fingerprints_like_the_equivalent_listing_dict():
    model = Apartment(
        link=ZAP_LINK,
        street=" RUA RAMIRO BARCELOS, 1954",
        neighborhood="BOM FIM ",
        area=45,
        bedrooms=1,
        price=2400.0,
    )

    for require_all_fields in (False, True):
        assert create_apartment_fingerprint(model, require_all_fields) == create_apartment_fingerprint(  # pyright: ignore[reportArgumentType] -- the function accepts Apartment at runtime though typed Dict
            listing(), require_all_fields
        )
    assert create_apartment_fingerprint(Apartment(link=ZAP_LINK, neighborhood="Bom Fim")) is None  # pyright: ignore[reportArgumentType] -- the function accepts Apartment at runtime though typed Dict
    assert create_apartment_fingerprint(Apartment(link=ZAP_LINK, street="Rua X")) is None  # pyright: ignore[reportArgumentType] -- the function accepts Apartment at runtime though typed Dict


# --- drop_cross_posts --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "agency_link"),
    [("leindecker:1234", LEINDECKER_LINK), ("certa:5678", CERTA_LINK)],
    ids=["leindecker", "certa"],
)
def test_the_agency_copy_of_a_cross_post_is_kept_in_its_own_position(ref, agency_link):
    portal = listing(link=ZAP_LINK, agency_ref=ref)
    unrelated = listing(link=VIVAREAL_LINK)
    agency = listing(link=agency_link, agency_ref=ref)

    assert drop_cross_posts([portal, unrelated, agency]) == [unrelated, agency]
    assert drop_cross_posts([portal, unrelated, agency])[1] is agency


def test_without_an_agency_copy_the_first_portal_copy_is_kept():
    first = listing(link=ZAP_LINK, agency_ref="leindecker:1234")
    second = listing(link=VIVAREAL_LINK, agency_ref="leindecker:1234")

    (kept,) = drop_cross_posts([first, second])

    assert kept is first


def test_the_kept_copy_takes_missing_fields_from_the_dropped_ones_but_keeps_its_own_values():
    agency = listing(
        link=LEINDECKER_LINK,
        agency_ref="leindecker:1234",
        street="",
        lat=None,
        images=[],
        price=2400.0,
        approximate_location=False,
    )
    portal = listing(
        link=ZAP_LINK,
        agency_ref="leindecker:1234",
        street="Rua Ramiro Barcelos, 1954",
        lat=-30.0330,
        images=["https://img/1.jpg"],
        price=2500.0,
        approximate_location=True,
        description="Perto do HCPA",
    )

    (kept,) = drop_cross_posts([portal, agency])

    assert kept["link"] == LEINDECKER_LINK
    assert kept["street"] == "Rua Ramiro Barcelos, 1954"
    assert kept["lat"] == -30.0330
    assert kept["images"] == ["https://img/1.jpg"]
    assert kept["description"] == "Perto do HCPA"
    assert kept["price"] == 2400.0
    assert kept["approximate_location"] is False


def test_listings_without_a_ref_or_with_different_refs_all_pass_through():
    apartments = [
        listing(link=VIVAREAL_LINK),
        listing(link=VIVAREAL_LINK, agency_ref=""),
        {k: v for k, v in listing(link=ZAP_LINK).items() if k != "agency_ref"},
        listing(link=LEINDECKER_LINK, agency_ref="leindecker:1"),
        listing(link=ZAP_LINK, agency_ref="leindecker:2"),
    ]

    assert drop_cross_posts(apartments) == apartments


# --- filter_new_apartments ---------------------------------------------------------------


def new_links(apartments, links=(), fingerprints=(), refs=()):
    kept = filter_new_apartments(apartments, set(links), set(fingerprints), set(refs))
    return [a["link"] for a in kept]


def fingerprint(apt) -> str:
    value = create_apartment_fingerprint(apt)
    assert value is not None
    return value


def test_an_unseen_listing_is_new():
    assert new_links([listing()], links=[ZAP_LINK], fingerprints=[fingerprint(listing(area=99))], refs=["certa:1"]) == [
        VIVAREAL_LINK
    ]


def test_a_listing_whose_link_was_saved_is_not_new():
    assert new_links([listing(area=99)], links=[VIVAREAL_LINK]) == []


def test_a_listing_whose_agency_ref_was_saved_is_not_new_even_from_another_site():
    assert new_links([listing(link=ZAP_LINK, agency_ref="leindecker:1234")], refs=["leindecker:1234"]) == []


def test_a_complete_listing_matching_a_saved_fingerprint_is_not_new():
    saved = listing(link=ZAP_LINK)
    assert new_links([listing(street="RUA RAMIRO BARCELOS 1954")], fingerprints=[fingerprint(saved)]) == []


@pytest.mark.parametrize("missing", ["area", "bedrooms", "price"])
def test_an_incomplete_listing_is_not_deduplicated_by_fingerprint(missing):
    saved = listing(link=ZAP_LINK, **{missing: None})
    assert new_links([listing(**{missing: None})], fingerprints=[fingerprint(saved)]) == [VIVAREAL_LINK]


def test_listings_without_a_link_are_always_kept():
    orphan = listing(link="")
    saved = filter_new_apartments([orphan, dict(orphan)], set(), {fingerprint(orphan)}, set())
    assert saved == [orphan, orphan]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param({}, {"area": 99}, id="same-link"),
        pytest.param(
            {"link": LEINDECKER_LINK, "agency_ref": "leindecker:1"},
            {"link": ZAP_LINK, "agency_ref": "leindecker:1", "area": 99},
            id="same-ref",
        ),
        pytest.param({}, {"link": ZAP_LINK}, id="same-complete-fingerprint"),
    ],
)
def test_a_repeat_within_the_same_batch_is_dropped(first, second):
    assert new_links([listing(**first), listing(**second)]) == [listing(**first)["link"]]


def test_incomplete_repeats_within_a_batch_are_kept():
    assert new_links([listing(price=None), listing(link=ZAP_LINK, price=None)]) == [VIVAREAL_LINK, ZAP_LINK]
