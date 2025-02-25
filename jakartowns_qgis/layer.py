from typing import Any, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant


class Layer:
    def __init__(self, name: str) -> None:
        self.name = name
        self._layer = QgsVectorLayer("Point", name, "memory")
        self._added = []
        self._changed = []
        self._removed = []
        self._layer.committedFeaturesAdded.connect(self.on_added)
        self._layer.committedFeaturesRemoved.connect(self.on_removed)
        self._layer.committedGeometriesChanges.connect(self.on_geometry_changed)
        self._layer.committedAttributeValuesChanges.connect(
            self.on_attribute_values_changed
        )
        self._layer.committedAttributesAdded.connect(self.on_attributes_added)
        self._layer.committedAttributesDeleted.connect(self.on_attributes_deleted)

        self._layer.afterCommitChanges.connect(self.after_commit)

        self.id = self._layer.id()

    def dirty(self) -> bool:
        return bool(self._added or self._changed or self._removed)

    def after_commit(self) -> None:
        if self.dirty():
            print(self._added, self._changed, self._removed, "dirty")
        self._added = []
        self._changed = []
        self._removed = []

    @property
    def layer(self) -> QgsVectorLayer:
        return self._layer

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
