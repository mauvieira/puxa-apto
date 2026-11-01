import pytest
from curl_cffi.requests.exceptions import HTTPError

from puxa_apto.utils import web


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(f"HTTP Error {self.status_code}", 0, self)


def fake_network(monkeypatch, status_by_profile):
    monkeypatch.setattr(web, "_profile_by_host", {})

    def get(url, impersonate=None, **kwargs):
        return FakeResponse(status_by_profile.get(impersonate, 403), b"ok")

    monkeypatch.setattr(web.requests, "get", get)


def test_a_site_that_blocks_chromes_fingerprint_is_still_fetched(monkeypatch):
    fake_network(monkeypatch, {"chrome": 403, "safari": 200})

    assert web.fetch_page("https://www.vivareal.com.br/x") == b"ok"


def test_a_site_that_blocks_every_fingerprint_raises_a_request_error(monkeypatch):
    fake_network(monkeypatch, {})

    with pytest.raises(web.RequestException):
        web.fetch_page("https://www.vivareal.com.br/x")
