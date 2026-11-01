import pytest

from puxa_apto.utils.text import slugify


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        pytest.param("Santa Cecília", "santa-cecilia", id="accent-dropped-letter-kept"),
        pytest.param("CENTRO HISTÓRICO", "centro-historico", id="upper-case-and-accent"),
        pytest.param("Graça", "graca", id="cedilla"),
        pytest.param("Moinhos de Vento", "moinhos-de-vento", id="spaces"),
        pytest.param("São João / Navegantes", "sao-joao-navegantes", id="punctuation-run-is-one-dash"),
        pytest.param("  Bom Fim!  ", "bom-fim", id="no-leading-or-trailing-dash"),
        pytest.param("Vila 24 de Outubro", "vila-24-de-outubro", id="digits-kept"),
        pytest.param("¿?", "", id="only-symbols"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug


def test_spellings_of_the_same_neighborhood_share_a_slug():
    assert slugify("Centro Histórico") == slugify("centro historico") == slugify("CENTRO-HISTORICO")
