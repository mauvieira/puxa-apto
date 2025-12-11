"""Default filters:
- Bedrooms: 3 or 4
- Max price: R$ 750.000
- Min area: 85 m²
- Amenities: Portaria 24h
- Location: Curitiba/PR (specific neighborhoods: Água Verde, Batel, Bigorrilho, Portão)
"""

import logging
import sys
from typing import Optional

DEFAULT_VIVAREAL_URL = (
    "https://www.vivareal.com.br/venda/brasil/apartamento_residencial/"
    "?transacao=venda&stamps=Datazap&tipos=apartamento_residencial"
    "&amenities=Portaria+24h&quartos=3%2C4&precoMaximo=750000"
    "&areaMinima=85&viewport=-49.266843766513205%2C-25.411754369023587"
    "%7C-49.31962963992629%2C-25.47151235294528"
)

DEFAULT_CHAVES_URL = (
    "https://www.chavesnamao.com.br/apartamentos-a-venda/pr-curitiba/agua-verde/3-quartos/"
    "?filtro=bai%3A[8629+8669+8628+8637+8646+8662]%2Cpmax%3A750000%2Camin%3A85%2Care%3A[31]"
)

DEFAULT_IMOVELWEB_URL = (
    "https://www.imovelweb.com.br/apartamentos-venda-agua-verde-curitiba-batel-curitiba"
    "-bigorrilho-portao-curitiba-areac-portaria-24-horas-3-quartos-mais-85-m2-util"
    "-menos-750000-reales-ordem-publicado-maior.html"
)

DEFAULT_ZAP_URL = (
    "https://www.zapimoveis.com.br/venda/"
    "?transacao=venda&stamps=Datazap&amenities=Portaria+24h&quartos=3%2C4"
    "&precoMaximo=750000&areaMinima=85"
    "&viewport=-49.26565732569504%2C-25.408943548379348"
    "%7C-49.318443199108124%2C-25.46870292652639"
)

DEFAULT_JSON_FILE = "apartamentos.json"
DEFAULT_CSV_FILE = "apartamentos.csv"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )