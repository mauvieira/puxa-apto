"""Every scraped site, in run order. Adding a site = a scraper, a URL builder and one entry here;
CLI flags (--<key>-url, --skip-<key>), config keys (sites, urls.<key>) and PUXA_URLS__<KEY>
follow from SITES."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Protocol

from .scrapers import (
    CertaScraper,
    ChavesScraper,
    ImovelWebScraper,
    LeindeckerScraper,
    VivaRealScraper,
    ZapScraper,
)
from .search import certa_urls, chaves_urls, imovelweb_urls, leindecker_urls, vivareal_urls, zap_urls

if TYPE_CHECKING:
    from .settings import SearchSettings


class Scraper(Protocol):
    """What the CLI needs from a scraper: BaseScraper and AgencyScraper subclasses both fit."""

    def __init__(self, url: str) -> None: ...

    def scrape(self, max_pages: Optional[int] = None) -> List[Dict]: ...


@dataclass(frozen=True)
class Site:
    """One scraped site; its key in SITES names its flags, config keys and fixtures."""

    label: str  # console heading, e.g. "ZAP IMÓVEIS"
    name: str  # in help texts and `info`, e.g. "Zap Imóveis"
    host: str  # e.g. "zapimoveis.com.br"; `info` and the test fixtures use it
    scraper: type[Scraper]  # built with one search URL
    build_urls: Callable[["SearchSettings"], List[str]]  # [] when the search lacks what `needs` names
    needs: str  # shown when the site is skipped for having nothing to search
    url_help: str  # help of --<key>-url
    short_flag: Optional[str] = None  # alias of --<key>-url, e.g. "-z"


# Keys become Python identifiers (<key>_url), so they must be lowercase identifiers.
SITES: Dict[str, Site] = {
    "vivareal": Site(
        label="VIVAREAL",
        name="VivaReal",
        host="vivareal.com.br",
        scraper=VivaRealScraper,
        build_urls=vivareal_urls,
        needs="places",
        url_help="VivaReal search URL (repeatable; replaces the built one)",
        short_flag="-v",
    ),
    "chaves": Site(
        label="CHAVES NA MÃO",
        name="Chaves na Mão",
        host="chavesnamao.com.br",
        scraper=ChavesScraper,
        build_urls=chaves_urls,
        needs="neighborhoods",
        url_help="Chaves na Mão search URL (repeatable; replaces the built ones)",
        short_flag="-c",
    ),
    "imovelweb": Site(
        label="IMOVELWEB",
        name="ImovelWeb",
        host="imovelweb.com.br",
        scraper=ImovelWebScraper,
        build_urls=imovelweb_urls,
        needs="neighborhoods",
        url_help="ImovelWeb search URL (repeatable; replaces the built one)",
        short_flag="-i",
    ),
    "zap": Site(
        label="ZAP IMÓVEIS",
        name="Zap Imóveis",
        host="zapimoveis.com.br",
        scraper=ZapScraper,
        build_urls=zap_urls,
        needs="places",
        url_help="Zap Imóveis search URL (repeatable; replaces the built one)",
        short_flag="-z",
    ),
    "leindecker": Site(
        label="LEINDECKER",
        name="Leindecker",
        host="leindecker.com.br",
        scraper=LeindeckerScraper,
        build_urls=leindecker_urls,
        needs="Porto Alegre neighborhoods",
        url_help="Leindecker search URL ending with its page number, e.g. …/1/ (repeatable; replaces the built one)",
    ),
    "certa": Site(
        label="CERTA",
        name="Certa",
        host="certa.com.br",
        scraper=CertaScraper,
        build_urls=certa_urls,
        needs="Porto Alegre neighborhoods and aluguel",
        url_help="Certa search URL ending with its page number, e.g. …/1/ (repeatable; replaces the built one)",
    ),
}


def resolve_urls(key: str, settings: "SearchSettings", cli_urls: List[str]) -> List[str]:
    """CLI URLs win over configured URLs, which win over URLs built from the search area."""
    return cli_urls or getattr(settings.urls, key) or SITES[key].build_urls(settings)
