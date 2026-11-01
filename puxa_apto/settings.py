from pathlib import Path
from typing import List, Literal, Optional, Tuple, Type, get_args

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .utils.text import slugify

SiteName = Literal["vivareal", "chaves", "imovelweb", "zap", "leindecker", "certa"]


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Place(Point):
    name: str = Field(min_length=1)


class SiteUrls(BaseModel):
    vivareal: List[str] = []
    zap: List[str] = []
    chaves: List[str] = []
    imovelweb: List[str] = []
    leindecker: List[str] = []
    certa: List[str] = []


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
    urls: SiteUrls = SiteUrls()  # explicit per-site URLs; replace the built ones
    # which sites run; default all
    sites: List[SiteName] = Field(default_factory=lambda: list(get_args(SiteName)), min_length=1)
    max_pages: Optional[int] = None
    json_file: str = "apartamentos.json"
    csv_file: Optional[str] = None

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
