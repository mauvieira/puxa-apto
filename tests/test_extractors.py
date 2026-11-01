import pytest

from puxa_apto.utils.extractors import extract_number, extract_price


@pytest.mark.parametrize(
    ("text", "number"),
    [
        pytest.param("45 m²", 45, id="area"),
        pytest.param("2 quartos", 2, id="bedrooms"),
        pytest.param("1.200 m²", 1200, id="thousands-dot"),
        pytest.param("3 a 4 quartos", 3, id="first-number-wins"),
        pytest.param("Quartos: 2", 2, id="number-after-label"),
        pytest.param("sem vaga", None, id="no-digits"),
        pytest.param("", None, id="empty"),
    ],
)
def test_extract_number(text, number):
    assert extract_number(text) == number


@pytest.mark.parametrize(
    ("text", "price"),
    [
        pytest.param("R$ 850", 850.0, id="plain"),
        pytest.param("R$ 2.500", 2500.0, id="thousands-dot"),
        pytest.param("R$ 2.500,50", 2500.5, id="decimal-comma"),
        pytest.param("R$ 1.234.567,89", 1234567.89, id="millions"),
        pytest.param("R$ 3.000 /mês", 3000.0, id="per-month-suffix"),
        pytest.param("Condomínio R$ 450", 450.0, id="condo-label"),
        pytest.param("R$ 120 IPTU", 120.0, id="iptu-label"),
        pytest.param("Sob consulta", None, id="no-digits"),
        pytest.param("", None, id="empty"),
    ],
)
def test_extract_price(text, price):
    assert extract_price(text) == price
