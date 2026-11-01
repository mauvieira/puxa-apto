"""Amenity codes and agency free-text tags, as the scrapers save them, in pt-BR for the sheet."""

import re
from typing import List

# Portal codes (VivaReal, Zap, ImovelWeb).
CODES = {
    "ALARM_SYSTEM": "Alarme",
    "BARBECUE_GRILL": "Churrasqueira",
    "BICYCLES_PLACE": "Bicicletário",
    "CARETAKER": "Zelador",
    "GARAGE": "Garagem",
    "HEATING": "Aquecimento",
    "INTERCOM": "Interfone",
    "KITCHEN": "Cozinha",
    "PARTY_HALL": "Salão de festas",
    "SERVICE_AREA": "Área de serviço",
    "WATCHMAN": "Vigia",
    "WOOD_FLOOR": "Piso de madeira",
    "AIR_CONDITIONING": "Ar-condicionado",
    "BATHROOM_CABINETS": "Armário no banheiro",
    "BLINDEX_BOX": "Box blindex",
    "ENTRANCE_HALL": "Hall de entrada",
    "FURNISHED": "Mobiliado",
    "GATED_COMMUNITY": "Condomínio fechado",
    "KITCHEN_CABINETS": "Armários na cozinha",
    "BUILTIN_WARDROBE": "Armário embutido",
    "GARDEN": "Jardim",
    "COOKER": "Fogão",
    "ELEVATOR": "Elevador",
    "CONCIERGE_24H": "Portaria 24h",
    "NATURAL_VENTILATION": "Ventilação natural",
    "GOURMET_SPACE": "Espaço gourmet",
    "PETS_ALLOWED": "Aceita pets",
    "SPORTS_COURT": "Quadra",
    "PLAYGROUND": "Playground",
    "GYM": "Academia",
    "LAMINATED_FLOOR": "Piso laminado",
    "LAUNDRY": "Lavanderia",
    "SAFETY_CIRCUIT": "Circuito de segurança",
    "DINNER_ROOM": "Sala de jantar",
    "GAMES_ROOM": "Salão de jogos",
    "COPA": "Copa",
    "MASSAGE_ROOM": "Sala de massagem",
    "BALCONY": "Sacada",
    "ECO_GARBAGE_COLLECTOR": "Coleta seletiva",
    "EXTERIOR_VIEW": "Vista externa",
    "INTERNET_ACCESS": "Internet",
    "LARGE_WINDOW": "Janela grande",
    "BATHTUB": "Banheira",
    "CABLE_TV": "TV a cabo",
    "DEPOSIT": "Depósito",
    "EMPLOYEE_DEPENDENCY": "Dependência de empregada",
    "COLD_FLOOR": "Piso frio",
    "POOL": "Piscina",
}

# Agency tags (Leindecker, Certa, Chaves), keyed lowercased; unknown ones are room noise and dropped.
FREE_TEXT = {
    "área de serviço": "Área de serviço",
    "bem arejado": "Ventilação natural",
    "cozinha": "Cozinha",
    "piso parquet": "Piso parquet",
    "armários embutidos": "Armário embutido",
    "churrasqueira no condomínio": "Churrasqueira",
    "ensolarado": "Ensolarado",
    "estacionamento (1 vaga)": "Garagem",
    "interfone": "Interfone",
    "portão garagem automático": "Portão eletrônico",
    "porteiro eletrônico": "Interfone",
    "salão de festas": "Salão de festas",
    "zelador": "Zelador",
    "aceita pet": "Aceita pets",
    "cozinha com balcão": "Cozinha",
    "portão automático de garagem": "Portão eletrônico",
    "vaga de garagem": "Garagem",
    "acesso com tag (sensor)": "Acesso por tag",
    "banheiro auxiliar": "Banheiro auxiliar",
    "gás central": "Gás canalizado",
    "gás canalizado": "Gás canalizado",
    "suíte": "Suíte",
    "cozinha com armário": "Armários na cozinha",
    "living com sacada": "Sacada",
    "piso laminado": "Piso laminado",
    "box de vidro": "Box blindex",
    "zeladoria": "Zelador",
    "ar condicionado": "Ar-condicionado",
    "bicicletário": "Bicicletário",
    "churrasqueira / quiosque": "Churrasqueira",
    "elevador": "Elevador",
    "lavanderia": "Lavanderia",
    "pátio": "Pátio",
    "apto térreo": "Térreo",
    "cozinha américana": "Cozinha americana",
    "jardim": "Jardim",
    "térreo": "Térreo",
    "sala de jantar": "Sala de jantar",
    "ventilador de teto": "Ventilador de teto",
    "semi-mobiliado": "Semimobiliado",
    "piso frio": "Piso frio",
    "mobiliado": "Mobiliado",
    "área serviço fechada": "Área de serviço",
    "garagem": "Garagem",
}

# Shown first, in this order: what decides a rental at a glance.
FIRST = [
    "Mobiliado",
    "Semimobiliado",
    "Aceita pets",
    "Ar-condicionado",
    "Elevador",
    "Lavanderia",
    "Portaria 24h",
    "Academia",
    "Garagem",
    "Sacada",
]

_CODE = re.compile(r"^[A-Z0-9_]+$")
_RANK = {name: i for i, name in enumerate(FIRST)}


def _name(code: str) -> str:
    if _CODE.match(code):
        return CODES.get(code) or code.replace("_", " ").capitalize()
    return FREE_TEXT.get(code.strip().lower(), "")


def amenity_names(codes: List[str]) -> str:
    """["KITCHEN", "PETS_ALLOWED", "Banheiro"] -> "Aceita pets, Cozinha"."""
    names = list(dict.fromkeys(name for name in map(_name, codes) if name))
    names.sort(key=lambda name: _RANK.get(name, len(FIRST)))
    return ", ".join(names)
