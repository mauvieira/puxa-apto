from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from ..config import DEFAULT_HEADERS

__all__ = ["fetch_page", "RequestException"]


def fetch_page(url: str) -> bytes:
    """Fetch a page with a Chrome TLS fingerprint; the sites block plain-Python handshakes."""
    response = requests.get(url, headers=DEFAULT_HEADERS, impersonate="chrome", timeout=30)
    response.raise_for_status()
    return response.content
