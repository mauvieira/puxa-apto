from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, Field, create_model, model_validator
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .sites import SITES
from .utils.text import slugify

SiteName = Literal[tuple(SITES)]


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Place(Point):
    name: str = Field(min_length=1)


# one List[str] field per registered site (urls.zap, ...)
_SITE_URL_FIELDS: Dict[str, Any] = {key: (List[str], []) for key in SITES}
SiteUrls = create_model("SiteUrls", **_SITE_URL_FIELDS)


class SearchSettings(BaseSettings):
    """One search: reference places (VivaReal/Zap map), neighborhoods (Chaves/ImovelWeb) and filters.

    Precedence: init kwargs (CLI flags) > PUXA_* env vars > .env > JSON config file > defaults.
    """

    # extra="ignore": .env files commonly hold unrelated non-PUXA_ keys, which "forbid" rejects.
    model_config = SettingsConfigDict(
        env_prefix="PUXA_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    transaction: Literal["aluguel", "venda"] = "venda"
    state: Optional[str] = None  # UF, e.g. "RS"
    city: Optional[str] = None  # e.g. "Porto Alegre"
    places: List[Place] = []  # reference points; listings beyond radius_km of all of them are dropped
    radius_km: float = Field(1.2, gt=0)
    neighborhoods: List[str] = []
    exclude_neighborhoods: List[str] = []
    max_price: Optional[float] = None
    max_total: Optional[float] = Field(None, gt=0)  # rent + condo fee; a missing fee counts as 0
    min_area: Optional[int] = None
    bedrooms: List[int] = []
    # SiteUrls and SiteName are generated from SITES at runtime, so pyright can't read them as
    # types; pydantic validates against them (ADR 0001).
    urls: SiteUrls = SiteUrls()  # pyright: ignore[reportInvalidTypeForm] -- generated from SITES; see comment above
    # which sites run; default all
    sites: List[SiteName] = Field(default_factory=lambda: list(SITES), min_length=1)  # pyright: ignore[reportInvalidTypeForm] -- generated from SITES; see comment above
    max_pages: Optional[int] = None
    json_file: str = "apartamentos.json"
    csv_file: Optional[str] = None
    title: Optional[str] = None  # heading of each Excel sheet; default "<Aluguel|Venda> · <city>"
    xlsx_file: Optional[str] = None  # workbook each run adds a sheet to

    @model_validator(mode="after")
    def _consistent(self) -> "SearchSettings":
        if self.neighborhoods and not (self.state and self.city):
            raise ValueError("state and city are required when neighborhoods are set")
        slugs = set()
        for place in self.places:
            slug = slugify(place.name)
            if not slug:
                raise ValueError(f"place name needs letters or digits: {place.name!r}")
            if slug in slugs:
                raise ValueError(f"place names must be unique: {place.name!r}")
            slugs.add(slug)
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, JsonConfigSettingsSource(settings_cls))


def load_settings(config_file: Optional[Path], overrides: dict) -> SearchSettings:
    class _FileBacked(SearchSettings):
        model_config = SettingsConfigDict(json_file=config_file)

    return _FileBacked(**overrides)
