from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from .constants import geometry_postgis_to_alias


@dataclass
class SupabaseFeature:
    id: str
    layer_id: str
    attributes: dict[str, Any]
    geom: dict[str, Any]
    parent_id: str | None = None

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> SupabaseFeature:
        return cls(
            id=json_data["id"],
            layer_id=json_data["layer_id"],
            attributes=json_data.get("attributes", {}),
            geom=json_data["geom"],
            parent_id=json_data.get("parent_id"),
        )

    def to_json(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "layer_id": self.layer_id,
            "attributes": {
                k: self._jsonize_value(v) for k, v in self.attributes.items()
            },
            "geom": self.geom,
        }
        if self.parent_id is not None:
            data["parent_id"] = self.parent_id
        return data

    def _jsonize_value(self, value: Any) -> Any:
        if isinstance(value, (int, str, float, bool)):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._jsonize_value(v) for v in value]
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif value is None:
            return None
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
    id: str
    name: str
    geometry_type: str
    attributes: list[LayerAttribute]
    srid: int
    parent_id: str | None = None
    temporary: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
