from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable, Optional, Union

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPoint,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface, QgsLayerTreeViewIndicator
from qgis.PyQt.QtGui import QIcon
from qgis.utils import iface

from .constants import geometry_types, python_to_qmetatype, qmetatype_to_python
from .converters import supabase_attribute_to_qgis_attribute, supabase_to_qgis_feature
from .logs import debug
from .qgis_events import QGISDeleteEvent, QGISInsertEvent, QGISUpdateEvent
from .supabase_models import LayerAttribute, SupabaseFeature, SupabaseLayer

iface: QgisInterface


HERE = Path(__file__).parent


class Layer:
    def __init__(
        self,
        name: str,
        supabase_layer_id: str,
        geometry_type: str,
        supabase_srid: int,
        attributes: Optional[list[LayerAttribute]],
        supabase_parent_layer_id: Optional[str],
        temporary: bool,
        commit_callback: Callable,
        qgis_layer: Optional[QgsVectorLayer] = None,
    ) -> None:
        self.name = name
        self.supabase_layer_id = supabase_layer_id
        self.supabase_parent_layer_id = supabase_parent_layer_id
        self.geometry_type = geometry_type
        self.supabase_srid = supabase_srid
        self.attributes: list[LayerAttribute] = attributes or []
        self.temporary = temporary
        self.commit_callback = commit_callback

        self._qgis_feature_id_to_supabase_id: dict[int, str] = {}
        self._supabase_feature_id_to_qgis_id: dict[str, int] = {}

        self.manually_updated_supabase_ids: set[str] = set()

        self._qgis_events: list[
            Union[QGISInsertEvent, QGISUpdateEvent, QGISDeleteEvent]
        ] = []

        self._layer_attributes_modified: bool = False

        self._qgis_layer = qgis_layer

        self._qgis_layer_signals_initialized: bool = False

        self._signals: dict[Any, Callable] = {}

    @classmethod
    def from_supabase_layer(
        cls,
        supabase_layer: SupabaseLayer,
        commit_callback: Callable,
        qgis_layer: Optional[QgsVectorLayer] = None,
    ) -> Layer:
        layer = cls(
            name=supabase_layer.name,
            supabase_layer_id=supabase_layer.id,
            geometry_type=supabase_layer.geometry_type,
            supabase_srid=supabase_layer.srid,
            attributes=supabase_layer.attributes,
            supabase_parent_layer_id=supabase_layer.parent_id,
            temporary=supabase_layer.temporary,
            commit_callback=commit_callback,
            qgis_layer=qgis_layer,
        )
        return layer

    @property
    def qgis_layer(self) -> QgsVectorLayer:
        if self._qgis_layer is None:
            self._qgis_layer_signals_initialized = False
            # create the layer
            self._qgis_layer = QgsVectorLayer(
                f"{geometry_types[self.geometry_type]}?crs=EPSG:{self.supabase_srid}&index=yes",
                self.name,
                "memory",
            )
            # add attributes
            provider = self._qgis_layer.dataProvider()
            attrs = [
                QgsField(attr.name, python_to_qmetatype[attr.type])
                for attr in self.attributes
            ]
            provider.addAttributes(attrs)
            self._qgis_layer.updateFields()

            # ignore warning about memory layers on quit
            self._qgis_layer.setCustomProperty("skipMemoryLayersCheck", 1)

        if not self._qgis_layer_signals_initialized:
            # connect signals
            signals = [
                (self._qgis_layer.committedFeaturesAdded, self.on_event_added),
                (self._qgis_layer.committedFeaturesRemoved, self.on_event_removed),
                (
                    self._qgis_layer.committedAttributeValuesChanges,
                    self.on_event_attributes_changed,
                ),
                (
                    self._qgis_layer.committedGeometriesChanges,
                    self.on_event_attributes_changed,
                ),
                (
                    self._qgis_layer.committedAttributesAdded,
                    self.on_event_attributes_added,
                ),
                (
                    self._qgis_layer.committedAttributesDeleted,
                    self.on_event_attributes_deleted,
                ),
                (self._qgis_layer.afterCommitChanges, self.after_commit),
            ]
            for event, callback in signals:
                self._connect_signal(event, callback)

            self._qgis_layer_signals_initialized = True

        return self._qgis_layer

    def _connect_signal(self, event, callback):
        self._signals[event] = callback
        event.connect(callback)

    def disconnect_all_signals(self) -> None:
        for event, callback in self._signals.items():
            event.disconnect(callback)
        self._signals.clear()
        self._qgis_layer_signals_initialized = False

    def add_feature_id(self, qgis_feature_id: int, supabase_feature_id: str) -> None:
        self._qgis_feature_id_to_supabase_id[qgis_feature_id] = supabase_feature_id
        self._supabase_feature_id_to_qgis_id[supabase_feature_id] = qgis_feature_id

    def get_supabase_feature_id(self, qgis_id: int) -> Optional[str]:
        return self._qgis_feature_id_to_supabase_id.get(qgis_id)

    def get_qgis_feature_id(self, supabase_id: str) -> Optional[int]:
        return self._supabase_feature_id_to_qgis_id.get(supabase_id)

    def remove_supabase_feature_id(self, supabase_id: str) -> None:
        qgis_id = self._supabase_feature_id_to_qgis_id.pop(supabase_id, None)
        if qgis_id is not None:
            self._qgis_feature_id_to_supabase_id.pop(qgis_id, None)

    def _reset_edits(self) -> None:
        self._qgis_events = []
        self._layer_attributes_modified = False

    def reset(self) -> None:
        self._reset_edits()
        self._qgis_layer = None
        self._qgis_layer_signals_initialized = False

    def add_features_on_load(self, features: list[SupabaseFeature]) -> None:
        """Called on the first load of the layer."""
        geometry_types = set(feature.geometry_type for feature in features)
        if wrong := geometry_types - {self.geometry_type}:
            raise ValueError(
                f"Geometry type {wrong} does not match layer geometry type {self.geometry_type}"
            )
        for feature in features:
            qgis_feature = supabase_to_qgis_feature(feature, self)
            self.qgis_layer.dataProvider().addFeature(qgis_feature)
            self.add_feature_id(qgis_feature.id(), feature.id)

        self.qgis_layer.updateExtents()

    def dirty(self) -> bool:
        """True if the layer has edits that need to be pushed to supabase."""
        return bool(self._qgis_events or self._layer_attributes_modified)

    def after_commit(self) -> None:
        """Called when the layer edits are committed."""
        if not self.dirty():
            return

        self.commit_callback(
            self,
            self._qgis_events,
            self._layer_attributes_modified,
        )
        self._reset_edits()

    def get_qgis_feature(self, qgis_id: int) -> Optional[QgsFeature]:
        feature = self.qgis_layer.getFeature(qgis_id)
        if not feature.isValid():
            return None
        return feature

    def get_qgis_features(self, qgis_ids: list[int]) -> list[Union[QgsFeature, None]]:
        by_id = {}
        for feature in self.qgis_layer.getFeatures(qgis_ids):
            if not feature.isValid():
                continue
            by_id[feature.id()] = feature
        return [by_id.get(id_) for id_ in qgis_ids]

    def on_event_added(self, layer_id: str, features: Iterable[QgsFeature]) -> None:
        """Called when features are added to the layer."""
        # remove echo of supabase_insert event
        features = [
            f for f in features if f.id() not in self._qgis_feature_id_to_supabase_id
        ]
        if not features:
            return
        self._qgis_events.append(QGISInsertEvent(list(features)))

    def on_event_removed(self, layer_id: str, fids: list[int]) -> None:
        """Called when features are removed from the layer."""
        # remove echo of supabase_delete event
        fids = [id_ for id_ in fids if id_ in self._qgis_feature_id_to_supabase_id]
        if not fids:
            return
        self._qgis_events.append(QGISDeleteEvent(list(fids)))

    def on_event_attributes_changed(
        self, layer_id: str, values: dict[int, dict[int, Any]]
    ) -> None:
        """Called when the attributes of a feature are changed."""
        fids = []
        for id_ in values.keys():
            supabase_id = self._qgis_feature_id_to_supabase_id.get(id_)
            if supabase_id is None:
                continue
            fids.append(id_)
        if not fids:
            return

        self._qgis_events.append(QGISUpdateEvent(fids))

    def on_event_attributes_added(
        self, layer_id: str, attributes: list[QgsField]
    ) -> None:
        """Called when new attributes are added to the layer."""
        for field in attributes:
            name = field.name()
            type_ = field.type()
            if type_ not in qmetatype_to_python:
                print("Warning: unknown attribute type", type_)
                continue
            self.attributes.append(LayerAttribute(name, qmetatype_to_python[type_]))
            self._layer_attributes_modified = True

    def on_event_attributes_deleted(
        self, layer_id: str, attribute_ids: list[int]
    ) -> None:
        """Called when attributes are deleted from the layer."""
        self.attributes = [
            a for i, a in enumerate(self.attributes) if i not in attribute_ids
        ]
        self._layer_attributes_modified = True

    def on_realtime_insert(self, features: list[SupabaseFeature]) -> None:
        """Called when an insert message is received from the realtime server."""
        if not self._qgis_layer_signals_initialized:
            return

        # remove echo of a qgis_insert event
        features = [
            f for f in features if f.id not in self._supabase_feature_id_to_qgis_id
        ]
        if not features:
            return

        debug(f"Supabase InsertMessage: {', '.join(f.id for f in features)}")

        qgis_features = [
            supabase_to_qgis_feature(feature, self) for feature in features
        ]
        self.qgis_layer.dataProvider().addFeatures(qgis_features)
        for qgis_feature, feature in zip(qgis_features, features):
            self.add_feature_id(qgis_feature.id(), feature.id)

        self.qgis_layer.triggerRepaint()
        # needed to refresh attribute table
        self.qgis_layer.reload()

    def on_realtime_update(self, features: list[SupabaseFeature]) -> None:
        """Called when an update message is received from the realtime server."""
        if not self._qgis_layer_signals_initialized:
            return

        # remove echo of a qgis_update event
        to_update = []
        for feature in features:
            if feature.id in self.manually_updated_supabase_ids:
                self.manually_updated_supabase_ids.remove(feature.id)
                continue
            if feature.id not in self._supabase_feature_id_to_qgis_id:
                continue
            to_update.append(feature)
        if not to_update:
            return
        features = to_update

        debug(f"Supabase UpdateMessage: {', '.join(f.id for f in features)}")

        qgis_ids = [self._supabase_feature_id_to_qgis_id[f.id] for f in features]
        qgis_features = self.get_qgis_features(qgis_ids)

        attr_name_to_type = {a.name: a.type for a in self.attributes}

        change_attributes_by_qgis_id: dict[int, dict[int, Any]] = {}
        change_geometry_by_qgis_id: dict[int, QgsGeometry] = {}

        for qgis_feature, feature in zip(qgis_features, features):
            if qgis_feature is None:
                continue
            change_attributes = {}
            change_geometry = None

            qgis_attributes = qgis_feature.attributes()

            for attr_name, value in feature.attributes.items():
                field_idx = self.qgis_layer.fields().indexOf(attr_name)
                if field_idx >= 0:
                    value = supabase_attribute_to_qgis_attribute(
                        value, attr_name_to_type[attr_name]
                    )
                    if qgis_attributes[field_idx] != value:
                        change_attributes[field_idx] = value

            if change_attributes:
                change_attributes_by_qgis_id[qgis_feature.id()] = change_attributes

            if feature.geom:
                if feature.geom["type"] != "Point":
                    raise ValueError(
                        f"Geometry type {feature.geom['type']} not implemented"
                    )
                x, y, z = feature.geom["coordinates"]
                qgis_pt = qgis_feature.geometry().vertexAt(0)
                qx, qy, qz = qgis_pt.x(), qgis_pt.y(), qgis_pt.z()

                # Compare coordinates with 8 decimal places precision
                if (
                    round(x, 8) != round(qx, 8)
                    or round(y, 8) != round(qy, 8)
                    or round(z, 8) != round(qz, 8)
                ):
                    change_geometry = QgsGeometry(QgsPoint(x, y, z))

            if change_geometry:
                change_geometry_by_qgis_id[qgis_feature.id()] = change_geometry

        if change_attributes_by_qgis_id:
            self.qgis_layer.dataProvider().changeAttributeValues(
                change_attributes_by_qgis_id
            )
        if change_geometry_by_qgis_id:
            self.qgis_layer.dataProvider().changeGeometryValues(
                change_geometry_by_qgis_id
            )
        # only update view if there are changes
        if change_attributes_by_qgis_id or change_geometry_by_qgis_id:
            self.qgis_layer.triggerRepaint()
            self.qgis_layer.reload()

    def on_realtime_delete(self, supabase_feature_ids: list[str]) -> bool:
        """Called when a delete message is received from the realtime server."""
        if not self._qgis_layer_signals_initialized:
            return False
        id_pairs_with_none = [
            (id_, self._supabase_feature_id_to_qgis_id.get(id_))
            for id_ in supabase_feature_ids
        ]
        id_pairs: list[tuple[str, int]] = [
            p for p in id_pairs_with_none if p[1] is not None
        ]
        if not id_pairs:
            return False  # echo of a qgis_delete event

        debug(f"Supabase DeleteMessage: {', '.join(supabase_feature_ids)}")

        try:
            # remove from those dicts before deleting the feature
            # to avoid infinite loop when on_event_removed is called
            for supabase_feature_id, qgis_id in id_pairs:
                self._supabase_feature_id_to_qgis_id.pop(supabase_feature_id, None)
                self._qgis_feature_id_to_supabase_id.pop(qgis_id, None)
            qgis_ids_to_delete = [p[1] for p in id_pairs]
            self.qgis_layer.dataProvider().deleteFeatures(qgis_ids_to_delete)
            self.qgis_layer.triggerRepaint()
            self.qgis_layer.reload()
        except Exception:
            # restore the dicts
            for supabase_feature_id, qgis_id in id_pairs:
                self._supabase_feature_id_to_qgis_id[supabase_feature_id] = qgis_id
                self._qgis_feature_id_to_supabase_id[qgis_id] = supabase_feature_id
            raise

        return True

    def set_layer_tree_icon(self, visible: bool) -> None:
        tree_root = QgsProject.instance().layerTreeRoot()
        layer_node = tree_root.findLayer(self.qgis_layer.id())
        if layer_node is not None:
            icons_folder = HERE / "ui" / "icons"
            icon = QIcon(str(icons_folder / "jakartowns-black.png"))
            ind = QgsLayerTreeViewIndicator(layer_node)
            ind.setIcon(icon)
            is_sub = self.supabase_parent_layer_id is not None
            name = "Layer" if not is_sub else "Sub-Layer"
            ind.setToolTip(f"Jakarto Real-time {name}")

            # remove all indicators, add the new one
            if hasattr(iface, "layerTreeView"):  # no iface.layerTreeView in tests
                tree_view = iface.layerTreeView()
                for indicator in tree_view.indicators(layer_node):
                    tree_view.removeIndicator(layer_node, indicator)
                if visible:
                    tree_view.addIndicator(layer_node, ind)

    def __repr__(self) -> str:
        return (
            f"Layer(name={self.name}, "
            f"supabase_layer_id={self.supabase_layer_id}, "
            f"temporary={self.temporary})"
        )
