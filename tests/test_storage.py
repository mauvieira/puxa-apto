import csv
import json
import re

from puxa_apto.utils.fingerprint import create_apartment_fingerprint, filter_new_apartments
from puxa_apto.utils.storage import (
    load_existing_apartments,
    save_new_apartments_csv,
    save_to_csv,
    save_to_json,
)

VIVAREAL_LINK = "https://www.vivareal.com.br/imovel/apartamento-1-quarto-bom-fim-porto-alegre-45m2-aluguel-id-1/"
ZAP_LINK = "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-1-quarto-bom-fim-porto-alegre-45m2-id-2/"
LEINDECKER_LINK = "https://www.leindecker.com.br/imovel/apartamento-santana-porto-alegre/1234/"
CHAVES_LINK = "https://www.chavesnamao.com.br/imovel/apartamento-a-venda-1-quarto-rs-porto-alegre-santa-cecilia-3/"

STANDARD_COLUMNS = [
    "link",
    "agency_ref",
    "title",
    "street",
    "neighborhood",
    "city",
    "area",
    "bedrooms",
    "bathrooms",
    "parking",
    "price",
    "condo_fee",
    "iptu",
    "total_price",
    "distance_km",
]
TRAILING_COLUMNS = ["approximate_location", "lat", "lon", "amenity_codes", "description", "images"]


def history():
    """Listings as earlier runs saved them: complete, with an agency ref, with cents, incomplete."""
    return [
        {
            "link": VIVAREAL_LINK,
            "agency_ref": None,
            "street": "Rua Ramiro Barcelos, 1954",
            "neighborhood": "Bom Fim",
            "area": 45,
            "bedrooms": 1,
            "price": 2400.0,
        },
        {
            "link": LEINDECKER_LINK,
            "agency_ref": "leindecker:1234",
            "street": "Rua Santana, 300",
            "neighborhood": "Santana",
            "area": 60,
            "bedrooms": 2,
            "price": 3150,
        },
        {
            "link": CHAVES_LINK,
            "agency_ref": None,
            "street": "Rua São Manoel, 12",
            "neighborhood": "Santa Cecília",
            "area": 38,
            "bedrooms": 1,
            "price": 1890.5,
        },
        {
            "link": "",
            "agency_ref": None,
            "street": "Avenida Protásio Alves, 10",
            "neighborhood": "Petrópolis",
            "area": None,
            "bedrooms": None,
            "price": None,
        },
    ]


def expected_keys(apartments):
    links = {a["link"] for a in apartments if a["link"]}
    fingerprints = {create_apartment_fingerprint(a) for a in apartments} - {None}
    refs = {a["agency_ref"] for a in apartments if a["agency_ref"]}
    return links, fingerprints, refs


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- load_existing_apartments ------------------------------------------------------------


def test_nothing_is_known_before_the_first_run(tmp_path):
    assert load_existing_apartments(str(tmp_path / "a.json"), str(tmp_path / "a.csv")) == (set(), set(), set())


def test_the_json_history_yields_links_fingerprints_and_agency_refs(tmp_path):
    json_file = tmp_path / "a.json"
    json_file.write_text(json.dumps(history()), encoding="utf-8")

    assert load_existing_apartments(str(json_file), str(tmp_path / "a.csv")) == expected_keys(history())


def test_the_csv_written_by_save_to_csv_yields_the_same_keys_as_the_json(tmp_path):
    csv_file = tmp_path / "a.csv"
    save_to_csv(history(), str(csv_file))

    assert load_existing_apartments(str(tmp_path / "a.json"), str(csv_file)) == expected_keys(history())


def test_a_legacy_csv_without_agency_refs_still_yields_links_and_fingerprints(tmp_path):
    csv_file = tmp_path / "a.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["link", "street", "neighborhood", "area", "bedrooms", "price"], extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(history())

    links, fingerprints, refs = load_existing_apartments(str(tmp_path / "a.json"), str(csv_file))

    expected_links, expected_fingerprints, _ = expected_keys(history())
    assert (links, fingerprints, refs) == (expected_links, expected_fingerprints, set())


def test_unparseable_csv_numbers_count_as_unknown(tmp_path):
    csv_file = tmp_path / "a.csv"
    apt = {"link": ZAP_LINK, "street": "Rua X", "neighborhood": "Bom Fim", "area": "45m2", "bedrooms": "um", "price": "R$ 2.400"}
    save_to_csv([apt], str(csv_file))

    _, fingerprints, _ = load_existing_apartments(str(tmp_path / "a.json"), str(csv_file))

    unknown = {"street": "Rua X", "neighborhood": "Bom Fim", "area": None, "bedrooms": None, "price": None}
    assert fingerprints == {create_apartment_fingerprint(unknown)}


def test_an_unreadable_json_still_lets_the_csv_load_and_vice_versa(tmp_path):
    json_file, csv_file = tmp_path / "a.json", tmp_path / "a.csv"
    json_file.write_text("[{not json", encoding="utf-8")
    save_to_csv(history()[:1], str(csv_file))

    assert load_existing_apartments(str(json_file), str(csv_file)) == expected_keys(history()[:1])

    json_file.write_text(json.dumps(history()[1:2]), encoding="utf-8")
    csv_file.write_bytes(b"link\n\xff\xfe\n")

    assert load_existing_apartments(str(json_file), str(csv_file)) == expected_keys(history()[1:2])


def test_saved_listings_reposted_with_a_new_link_are_not_new(tmp_path):
    json_file = tmp_path / "a.json"
    save_to_json(history(), str(json_file))
    links, fingerprints, refs = load_existing_apartments(str(json_file), str(tmp_path / "a.csv"))

    same_link = dict(history()[0], price=9999.0)
    same_ref = dict(history()[1], link="https://www.zapimoveis.com.br/imovel/x-id-9/", area=61)
    same_apartment = dict(history()[2], link="https://www.vivareal.com.br/imovel/x-id-8/", street="RUA SÃO MANOEL 12")
    fresh = dict(history()[0], link="https://www.vivareal.com.br/imovel/x-id-7/", bedrooms=3)

    new = filter_new_apartments([same_link, same_ref, same_apartment, fresh], links, fingerprints, refs)

    assert new == [fresh]


# --- save_to_json ------------------------------------------------------------------------


def test_save_to_json_appends_to_the_history_and_returns_all_of_it(tmp_path):
    json_file = str(tmp_path / "a.json")
    first, second = history()[:2], history()[2:]

    assert save_to_json(first, json_file) == first
    assert save_to_json(second, json_file) == first + second
    with open(json_file, encoding="utf-8") as f:
        assert json.load(f) == first + second


def test_save_to_json_with_nothing_new_returns_the_history_untouched(tmp_path):
    json_file = tmp_path / "a.json"

    assert save_to_json([], str(json_file)) == []
    assert not json_file.exists()

    save_to_json(history(), str(json_file))
    before = json_file.read_bytes()
    assert save_to_json([], str(json_file)) == history()
    assert json_file.read_bytes() == before


# --- save_to_csv -------------------------------------------------------------------------


def test_csv_columns_put_standard_fields_first_then_one_column_per_place_then_the_rest(tmp_path):
    csv_file = tmp_path / "a.csv"
    apartments = [
        {"link": VIVAREAL_LINK, "distance_km_famed": 0.5, "source_page": 1},
        {"link": ZAP_LINK, "distance_km_hcpa": 0.7, "distance_km_famed": 0.4, "source_page": 2, "floor": 3},
    ]

    save_to_csv(apartments, str(csv_file))

    with open(csv_file, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == [
        *STANDARD_COLUMNS,
        "distance_km_famed",
        "distance_km_hcpa",
        *TRAILING_COLUMNS,
        "source_page",
        "floor",
    ]


def test_csv_rows_hold_every_value_with_lists_joined_and_gaps_blank(tmp_path):
    csv_file = tmp_path / "a.csv"
    apt = {
        "link": CHAVES_LINK,
        "neighborhood": "Santa Cecília",
        "price": 1890.5,
        "condo_fee": None,
        "images": ["https://img/1.jpg", "https://img/2.jpg"],
        "amenity_codes": ["POOL", "GYM"],
    }

    save_to_csv([apt], str(csv_file))

    (row,) = read_csv(csv_file)
    assert row["link"] == CHAVES_LINK
    assert row["neighborhood"] == "Santa Cecília"
    assert row["price"] == "1890.5"
    assert row["condo_fee"] == ""
    assert row["street"] == ""
    assert row["images"] == "https://img/1.jpg;https://img/2.jpg"
    assert row["amenity_codes"] == "POOL;GYM"


def test_save_to_csv_replaces_the_previous_file(tmp_path):
    csv_file = tmp_path / "a.csv"
    save_to_csv(history(), str(csv_file))

    save_to_csv(history()[:1], str(csv_file))

    assert [row["link"] for row in read_csv(csv_file)] == [VIVAREAL_LINK]


def test_save_to_csv_with_nothing_writes_no_file(tmp_path):
    csv_file = tmp_path / "a.csv"
    save_to_csv([], str(csv_file))
    assert not csv_file.exists()


# --- save_new_apartments_csv -------------------------------------------------------------


def test_new_listings_go_to_a_timestamped_csv_in_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert save_new_apartments_csv([]) == ""
    assert list(tmp_path.iterdir()) == []

    filename = save_new_apartments_csv(history())

    assert re.fullmatch(r"apartamentos_novos_\d{8}_\d{6}\.csv", filename)
    assert [row["link"] for row in read_csv(tmp_path / filename)] == [a["link"] for a in history()]
