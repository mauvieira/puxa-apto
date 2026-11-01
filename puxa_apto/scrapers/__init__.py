"""Scrapers for various real estate websites."""

from .base import BaseScraper
from .vivareal import VivaRealScraper
from .zap import ZapScraper
from .chaves import ChavesScraper
from .imovelweb import ImovelWebScraper
from .leindecker import LeindeckerScraper
from .certa import CertaScraper

__all__ = [
    "BaseScraper",
    "CertaScraper",
    "ChavesScraper",
    "ImovelWebScraper",
    "LeindeckerScraper",
    "VivaRealScraper",
    "ZapScraper",
]
