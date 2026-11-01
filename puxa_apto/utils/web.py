from typing import Dict
from urllib.parse import urlsplit

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from ..config import DEFAULT_HEADERS

__all__ = ["RequestException", "fetch_page"]

PROFILES = ("chrome", "safari")
_profile_by_host: Dict[str, str] = {}


def fetch_page(url: str) -> bytes:  # pyright: ignore[reportReturnType] -- baseline: predates type checking
    """Fetch with a browser TLS fingerprint; Cloudflare blocks some fingerprints per site."""
    host = urlsplit(url).hostname or ""
    remembered = _profile_by_host.get(host)
    order = sorted(PROFILES, key=lambda p: p != remembered)  # remembered profile first
    for profile in order:
        response = requests.get(url, headers=DEFAULT_HEADERS, impersonate=profile, timeout=30)
        if response.status_code == 403 and profile != order[-1]:
            continue
        response.raise_for_status()
        _profile_by_host[host] = profile
        return response.content
