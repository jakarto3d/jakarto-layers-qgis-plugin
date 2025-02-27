from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Generator, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface

from .constants import geometry_types, python_to_qmetatype, qmetatype_to_python
from .postgrest import PostgrestFeature

iface: QgisInterface


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

        self._ignore_signals = False

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
                QgsField(attr.name, python_to_qmetatype[attr.type])
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

    @contextmanager
    def ignore_signals(self) -> Generator[None, None, None]:
        self._ignore_signals = True
        yield
        self._ignore_signals = False

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

    def pg_feature_by_qgis_id(self, qgis_id: int) -> PostgrestFeature | None:
        return next((f for f in self._postgrest_features if f.qgis_id == qgis_id), None)

    def pg_feature_by_source_id(self, source_id: str) -> PostgrestFeature | None:
        return next(
            (f for f in self._postgrest_features if f.source_id == source_id), None
        )

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
        if self._ignore_signals:
            return
        for feature in features:
            postgrest_feature = PostgrestFeature.from_qgis_feature(
                feature, self.source_id
            )
            self._postgrest_features.append(postgrest_feature)
            self._added.append(postgrest_feature)

    def on_removed(self, layer_id: str, fids: list[int]) -> None:
        if self._ignore_signals:
            return
        for fid in fids:
            if not (feature := self.pg_feature_by_qgis_id(fid)):
                continue
            self._removed.append(feature)
            self._postgrest_features.remove(feature)

    def on_attribute_values_changed(
        self, layer_id: str, values: dict[int, dict[int, Any]]
    ) -> None:
        if self._ignore_signals:
            return
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

                if not (feature := self.pg_feature_by_qgis_id(fid)):
                    continue

                feature.attributes[self.attributes[attr_idx].name] = value
                self._attributes_changed.append(feature)

    def on_attributes_added(self, layer_id: str, attributes: list[QgsField]) -> None:
        if self._ignore_signals:
            return
        for field in attributes:
            name = field.name()
            type_ = field.type()
            if type_ not in qmetatype_to_python:
                print("Warning: unknown attribute type", type_)
                continue
            self.attributes.append(LayerAttribute(name, qmetatype_to_python[type_]))
            self._layer_attributes_modified = True

    def on_attributes_deleted(self, layer_id: str, attribute_ids: list[int]) -> None:
        if self._ignore_signals:
            return
        self.attributes = [
            a for i, a in enumerate(self.attributes) if i not in attribute_ids
        ]
        self._layer_attributes_modified = True

    def on_geometry_changed(
        self, layer_id: int, geometries: dict[int, QgsGeometry]
    ) -> None:
        if self._ignore_signals:
            return
        for fid, geom in geometries.items():
            if not (feature := self.pg_feature_by_qgis_id(fid)):
                continue
            feature.geom = json.loads(geom.asJson())
            self._geometry_changed.append(feature)

    def update_feature(self, feature: PostgrestFeature) -> None:
        """Called when an update message is received from the realtime server.

        This function updates the feature in the QGIS layer.
        Also, it avoids triggering a database update again in an infinite loop
        using the `ignore_signals` context manager.
        """
        current_feature = self.pg_feature_by_source_id(feature.source_id)
        if current_feature is None or current_feature.qgis_id is None:
            return

        self.qgis_layer.startEditing()

        try:
            current_feature.attributes = feature.attributes
            current_feature.geom = feature.geom

            qgis_feature = self.qgis_layer.getFeature(current_feature.qgis_id)
            # update the feature's attributes
            for attr_name, value in feature.attributes.items():
                field_idx = self.qgis_layer.fields().indexOf(attr_name)
                if field_idx >= 0:
                    qgis_feature.setAttribute(field_idx, value)
            if feature.geom:
                x, y = feature.geom["coordinates"]
                qgis_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))

            self.qgis_layer.updateFeature(qgis_feature)
            # avoid infinite loop
            # (realtime -> QGIS -> database -> realtime -> QGIS -> database -> ...)
            with self.ignore_signals():
                self.qgis_layer.commitChanges()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)

    def add_feature(self, feature: PostgrestFeature) -> None:
        """Called when an insert message is received from the realtime server.

        Similar as `.update_feature`.
        """
        self.qgis_layer.startEditing()
        try:
            feature.add_to_qgis_layer(self)
            self._postgrest_features.append(feature)
            self.qgis_layer.updateExtents()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)

    def delete_feature(self, feature: PostgrestFeature) -> None:
        """Called when a delete message is received from the realtime server.

        Similar as `.update_feature`.
        """
        current_feature = self.pg_feature_by_source_id(feature.source_id)
        if current_feature is None or current_feature.qgis_id is None:
            return

        self.qgis_layer.startEditing()

        try:
            self.qgis_layer.deleteFeature(current_feature.qgis_id)
            with self.ignore_signals():
                self.qgis_layer.commitChanges()
            self._postgrest_features.remove(current_feature)
            self.qgis_layer.updateExtents()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)


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
