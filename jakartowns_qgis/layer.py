from typing import Any, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from .constants import geometry_types


class Layer:
    def __init__(self, name: str, id_: str, geometry_type: str) -> None:
        self.name = name
        self.source_id = id_
        self.geometry_type = geometry_type
        self._added = []
        self._changed = []
        self._removed = []
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
            self._qgis_layer.committedGeometriesChanges.connect(
                self.on_geometry_changed
            )
            self._qgis_layer.committedAttributeValuesChanges.connect(
                self.on_attribute_values_changed
            )
            self._qgis_layer.committedAttributesAdded.connect(self.on_attributes_added)
            self._qgis_layer.committedAttributesDeleted.connect(
                self.on_attributes_deleted
            )

            self._qgis_layer.afterCommitChanges.connect(self.after_commit)

        return self._qgis_layer

    def reset(self) -> None:
        self._added = []
        self._changed = []
        self._removed = []
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
            x, y = geom["coordinates"]
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            provider.addFeature(f)
        self.qgis_layer.updateExtents()

    def dirty(self) -> bool:
        return bool(self._added or self._changed or self._removed)

    def after_commit(self) -> None:
        if self.dirty():
            print(self._added, self._changed, self._removed, "dirty")
        self._added = []
        self._changed = []
        self._removed = []

    def on_added(self, layer_id: str, features: Iterable[QgsFeature]) -> None:
        fids = [feature.id() for feature in features]
        print(fids, "added")
        self._added.extend(fids)

    def on_removed(self, layer_id: str, fids: list[int]) -> None:
        print(fids, "removed")
        self._removed.extend(fids)

    def on_geometry_changed(
        self, layer_id: int, geometries: dict[int, QgsGeometry]
    ) -> None:
        print(geometries, "geometry changed")

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

                print(fid, attr_idx, type(value), value, "attributes changed")

    def on_attributes_added(self, layer_id: str, attributes: list[QgsField]) -> None:
        print(attributes, "attributes added")

    def on_attributes_deleted(self, layer_id: str, attributes: list[int]) -> None:
        print(attributes, "attributes deleted")
