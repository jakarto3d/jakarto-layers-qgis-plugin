from __future__ import annotations

from dataclasses import dataclass
from typing import Any


from .constants import geometry_postgis_to_alias


@dataclass
class SupabaseFeature:
    id: str
    layer: str
    attributes: dict[str, Any]
    geom: dict[str, Any]

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> SupabaseFeature:
        return cls(
            id=json_data["id"],
            layer=json_data["layer"],
            attributes=json_data.get("attributes", {}),
            geom=json_data["geom"],
        )

    def to_json(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "layer": self.layer,
            "attributes": self.attributes,
            "geom": self.geom,
        }
        return data

    @property
    def geometry_type(self) -> str:
        return geometry_postgis_to_alias[self.geom["type"]]
