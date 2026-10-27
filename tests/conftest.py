import gzip
import os
import re
import time
from pathlib import Path

import pytest

from puxa_apto.utils import web

FIXTURES = Path(__file__).resolve().parent / "fixtures"

_FIXTURE_BY_HOST = {
    "vivareal.com.br": "vivareal.html.gz",
    "zapimoveis.com.br": "zap.html.gz",
    "chavesnamao.com.br": "chaves.html.gz",
    "imovelweb.com.br": "imovelweb.html.gz",
    "leindecker.com.br": "leindecker.html.gz",
    "certa.com.br": "certa.html.gz",
}
_DETAIL_FIXTURE_BY_HOST = {
    "leindecker.com.br": "leindecker-detail.html.gz",
    "certa.com.br": "certa-detail.html.gz",
}
_LATER_PAGE = re.compile(r"pagina|[?&]pg=")


@pytest.fixture
def fake_sites(monkeypatch, tmp_path):
    """Serve captured search pages instead of the network; returns the URLs requested."""
    for name in list(os.environ):
        if name.startswith("PUXA_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)

    requested = []

    def fetch_page(url: str) -> bytes:
        requested.append(url)
        if _LATER_PAGE.search(url):
            return b"<html></html>"
        fixtures = _DETAIL_FIXTURE_BY_HOST if "/imovel/" in url else {}
        fixture = next(
            (f for host, f in fixtures.items() if host in url),
            None,
        ) or next(f for host, f in _FIXTURE_BY_HOST.items() if host in url)
        return gzip.decompress((FIXTURES / fixture).read_bytes())

    monkeypatch.setattr(web, "fetch_page", fetch_page)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return requested
