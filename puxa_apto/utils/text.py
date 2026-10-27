import re
import unicodedata


def slugify(text: str) -> str:
    """"Santa Cecília" -> "santa-cecilia"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
