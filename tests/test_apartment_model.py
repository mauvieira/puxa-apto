from puxa_apto.models.apartment import Apartment

LISTING = {
    "link": "https://www.vivareal.com.br/imovel/apartamento-1-quarto-bom-fim-porto-alegre-45m2-aluguel-id-1/",
    "street": "Rua Ramiro Barcelos, 1954",
    "neighborhood": "Bom Fim",
    "city": "Porto Alegre",
    "area": 45,
    "bedrooms": 1,
    "bathrooms": 1,
    "parking": 0,
    "price": 2400.0,
    "condo_fee": 450.0,
    "iptu": 60.0,
    "title": "Apartamento perto do HCPA",
    "images": ["https://img/1.jpg"],
}


def test_a_listing_round_trips_through_the_model_dropping_fields_it_does_not_hold():
    scraped = {**LISTING, "agency_ref": None, "lat": -30.03, "description": "Perto do HCPA"}

    assert Apartment.from_dict(scraped).to_dict() == LISTING


def test_fields_missing_from_a_listing_take_the_model_defaults():
    assert Apartment.from_dict({}) == Apartment(link="")
    assert Apartment.from_dict({}).to_dict() == {
        "link": "",
        "street": "",
        "neighborhood": "",
        "city": "",
        "area": None,
        "bedrooms": None,
        "bathrooms": None,
        "parking": None,
        "price": None,
        "condo_fee": None,
        "iptu": None,
        "title": "",
        "images": [],
    }

