from typing import Any, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from .constants import geometry_types, qmetatype_to_python


class Layer:
    def __init__(
        self,
        name: str,
        id_: str,
        geometry_type: str,
        attributes: dict | None = None,
    ) -> None:
        self.name = name
        self.source_id = id_
        self.geometry_type = geometry_type
        self.attributes: dict[str, dict[str, str]] = attributes or {}

        self._added: list[QgsFeature] = []
        self._removed: list[int] = []
        self._attributes_changed: list[int] = []
        self._attributes_added: dict[str, dict[str, str]] = {}
        self._attributes_deleted: list[int] = []
        self._geometry_changed: dict[int, QgsGeometry] = {}

        self._qgis_layer = None

    @property
    def qgis_layer(self) -> QgsVectorLayer:
        if self._qgis_layer is None:
            self._qgis_layer = QgsVectorLayer(
                f"{geometry_types[self.geometry_type]}?crs=EPSG:4326",
                self.name,
                "memory",
            )

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
        self._attributes_added.clear()
        self._attributes_deleted.clear()
        self._geometry_changed.clear()

    def reset(self) -> None:
        self._reset_edits()

        self._qgis_layer = None

    @property
    def qgis_id(self) -> str | None:
        if self._qgis_layer is None:
            return None
        return self._qgis_layer.id()

    def add_features(self, features: Iterable[dict[str, Any]]) -> None:
        provider = self.qgis_layer.dataProvider()
        for feature in features:
            geom = feature["geom"]
            if self.geometry_type == "point":
                x, y = geom["coordinates"]
                f = QgsFeature()
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                provider.addFeature(f)
            else:
                raise NotImplementedError(
                    f"Geometry type {self.geometry_type} not implemented"
                )
        self.qgis_layer.updateExtents()

    def dirty(self) -> bool:
        return bool(
            self._added
            or self._removed
            or self._attributes_changed
            or self._attributes_added
            or self._attributes_deleted
            or self._geometry_changed
        )

    def after_commit(self) -> None:
        if self.dirty():
            print("added", self._added)
            print("removed", self._removed)
            print("attributes changed", self._attributes_changed)
            print("attributes added", self._attributes_added)
            print("attributes deleted", self._attributes_deleted)
            print("geometry changed", self._geometry_changed)
        self._reset_edits()

    def on_added(self, layer_id: str, features: Iterable[QgsFeature]) -> None:
        self._added.extend(features)

    def on_removed(self, layer_id: str, fids: list[int]) -> None:
        self._removed.extend(fids)

    def on_geometry_changed(
        self, layer_id: int, geometries: dict[int, QgsGeometry]
    ) -> None:
        self._geometry_changed.update(geometries)

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

                self._attributes_changed.append(fid)

    def on_attributes_added(self, layer_id: str, attributes: list[QgsField]) -> None:
        for field in attributes:
            name = field.name()
            type_ = field.type()
            if type_ not in qmetatype_to_python:
                print("Warning: unknown attribute type", type_)
                continue
            self._attributes_added[name] = {"type": qmetatype_to_python[type_].__name__}

    def on_attributes_deleted(self, layer_id: str, attributes: list[int]) -> None:
        self._attributes_deleted.extend(attributes)
