from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from .constants import geometry_types, python_to_qvariant, qmetatype_to_python
from .postgrest import PostgrestFeature


class Layer:
    def __init__(
        self,
        name: str,
        id_: str,
        geometry_type: str,
        attributes: list[LayerAttribute] | None,
        commit_callback: Callable,
    ) -> None:
        self.name = name
        self.source_id = id_
        self.geometry_type = geometry_type
        self.attributes: list[LayerAttribute] = attributes or []
        self.commit_callback = commit_callback

        self._postgrest_features: list[PostgrestFeature] = []

        self._added: list[PostgrestFeature] = []
        self._removed: list[PostgrestFeature] = []
        self._attributes_changed: list[PostgrestFeature] = []
        self._geometry_changed: list[PostgrestFeature] = []
        self._layer_attributes_modified: bool = False

        self._qgis_layer = None

    @property
    def qgis_layer(self) -> QgsVectorLayer:
        if self._qgis_layer is None:
            self._qgis_layer = QgsVectorLayer(
                f"{geometry_types[self.geometry_type]}?crs=EPSG:4326",
                self.name,
                "memory",
            )

            provider = self._qgis_layer.dataProvider()
            attrs = [
                QgsField(attr.name, python_to_qvariant[attr.type])
                for attr in self.attributes
            ]
            provider.addAttributes(attrs)

            self._qgis_layer.updateFields()

            self._qgis_layer.committedFeaturesAdded.connect(self.on_added)
            self._qgis_layer.committedFeaturesRemoved.connect(self.on_removed)
            self._qgis_layer.committedAttributeValuesChanges.connect(
                self.on_attribute_values_changed
            )
            self._qgis_layer.committedAttributesAdded.connect(self.on_attributes_added)
            self._qgis_layer.committedAttributesDeleted.connect(
                self.on_attributes_deleted
            )
            self._qgis_layer.committedGeometriesChanges.connect(
                self.on_geometry_changed
            )

            self._qgis_layer.afterCommitChanges.connect(self.after_commit)

        return self._qgis_layer

    def _reset_edits(self) -> None:
        self._added.clear()
        self._removed.clear()
        self._attributes_changed.clear()
        self._geometry_changed.clear()
        self._layer_attributes_modified = False

    def reset(self) -> None:
        self._reset_edits()
        self._postgrest_features.clear()
        self._qgis_layer = None

    @property
    def qgis_id(self) -> str | None:
        if self._qgis_layer is None:
            return None
        return self._qgis_layer.id()

    def add_features(self, features: list[PostgrestFeature]) -> None:
        geometry_types = set(feature.geometry_type for feature in features)
        if wrong := geometry_types - {self.geometry_type}:
            raise ValueError(
                f"Geometry type {wrong} does not match layer geometry type {self.geometry_type}"
            )
        for feature in features:
            feature.add_to_qgis_layer(self)
            self._postgrest_features.append(feature)

        self.qgis_layer.updateExtents()

    def dirty(self) -> bool:
        return bool(
            self._added
            or self._removed
            or self._attributes_changed
            or self._geometry_changed
            or self._layer_attributes_modified
        )

    def _pg_feature_by_qgis_id(self, qgis_id: int) -> PostgrestFeature | None:
        return next((f for f in self._postgrest_features if f.qgis_id == qgis_id), None)

    def after_commit(self) -> None:
        if not self.dirty():
            return

        self.commit_callback(
            self,
            self._added,
            self._removed,
            self._attributes_changed,
            self._geometry_changed,
            self._layer_attributes_modified,
        )
        self._reset_edits()

    def on_added(self, layer_id: str, features: Iterable[QgsFeature]) -> None:
        for feature in features:
            postgrest_feature = PostgrestFeature.from_qgis_feature(
                feature, self.source_id
            )
            self._postgrest_features.append(postgrest_feature)
            self._added.append(postgrest_feature)

    def on_removed(self, layer_id: str, fids: list[int]) -> None:
        for fid in fids:
            if not (feature := self._pg_feature_by_qgis_id(fid)):
                continue
            self._removed.append(feature)
            self._postgrest_features.remove(feature)

    def on_attribute_values_changed(
        self, layer_id: str, values: dict[int, dict[int, Any]]
    ) -> None:
        for fid, attrs in values.items():
            for attr_idx, value in attrs.items():
                if QVariant() == value:
                    value = None
                elif isinstance(value, (int, str, float, bool)):
                    pass
                elif hasattr(value, "value"):
                    value = value.value()
                elif to_py := [f for f in dir(value) if f.startswith("toPy")]:
                    value = getattr(value, to_py[0])()
                else:
                    raise ValueError(f"Unknown value type: {type(value)}")

                if not (feature := self._pg_feature_by_qgis_id(fid)):
                    continue

                feature.attributes[self.attributes[attr_idx].name] = value
                self._attributes_changed.append(feature)

    def on_attributes_added(self, layer_id: str, attributes: list[QgsField]) -> None:
        for field in attributes:
            name = field.name()
            type_ = field.type()
            if type_ not in qmetatype_to_python:
                print("Warning: unknown attribute type", type_)
                continue
            self.attributes.append(LayerAttribute(name, qmetatype_to_python[type_]))
            self._layer_attributes_modified = True

    def on_attributes_deleted(self, layer_id: str, attribute_ids: list[int]) -> None:
        self.attributes = [
            a for i, a in enumerate(self.attributes) if i not in attribute_ids
        ]
        self._layer_attributes_modified = True

    def on_geometry_changed(
        self, layer_id: int, geometries: dict[int, QgsGeometry]
    ) -> None:
        for fid, geom in geometries.items():
            if not (feature := self._pg_feature_by_qgis_id(fid)):
                continue
            feature.geom = json.loads(geom.asJson())
            self._geometry_changed.append(feature)


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
