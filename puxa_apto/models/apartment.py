from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Apartment:

    link: str
    street: str = ""
    neighborhood: str = ""
    city: str = ""
    area: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    price: Optional[float] = None
    condo_fee: Optional[float] = None
    iptu: Optional[float] = None
    title: str = ""
    images: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "link": self.link,
            "street": self.street,
            "neighborhood": self.neighborhood,
            "city": self.city,
            "area": self.area,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "parking": self.parking,
            "price": self.price,
            "condo_fee": self.condo_fee,
            "iptu": self.iptu,
            "title": self.title,
            "images": self.images,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Apartment":
        return cls(
            link=data.get("link", ""),
            street=data.get("street", ""),
            neighborhood=data.get("neighborhood", ""),
            city=data.get("city", ""),
            area=data.get("area"),
            bedrooms=data.get("bedrooms"),
            bathrooms=data.get("bathrooms"),
            parking=data.get("parking"),
            price=data.get("price"),
            condo_fee=data.get("condo_fee"),
            iptu=data.get("iptu"),
            title=data.get("title", ""),
            images=data.get("images", []),
        )
