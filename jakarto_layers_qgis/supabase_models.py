from __future__ import annotations

from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Any
import uuid

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
            "attributes": {
                k: self._jsonize_value(v) for k, v in self.attributes.items()
            },
            "geom": self.geom,
        }
        return data

    def _jsonize_value(self, value: Any) -> Any:
        if isinstance(value, (int, str, float, bool)):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._jsonize_value(v) for v in value]
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        else:
            return str(value)

    @property
    def geometry_type(self) -> str:
        return geometry_postgis_to_alias[self.geom["type"]]


@dataclass
class LayerAttribute:
    name: str
    type: str

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> LayerAttribute:
        return cls(
            name=json_data["name"],
            type=json_data["type"],
        )


@dataclass
class SupabaseLayer:
    name: str
    geometry_type: str
    attributes: list[LayerAttribute]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
