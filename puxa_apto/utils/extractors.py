
import re
from typing import Optional


def extract_number(text: str) -> Optional[int]:
    if not text:
        return None
    numbers = re.findall(r"\d+", text.replace(".", "").replace(",", ""))
    return int(numbers[0]) if numbers else None


def extract_price(text: str) -> Optional[float]:
    if not text:
        return None
    numbers = re.findall(r"\d+", text.replace(".", "").replace(",", "."))
    if numbers:
        return (
            float("".join(numbers[:-1]) + "." + numbers[-1])
            if len(numbers) > 1
            else float(numbers[0])
        )
    return None
