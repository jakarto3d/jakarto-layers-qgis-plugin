from __future__ import annotations

from typing import Any, Callable, Iterable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPoint, QgsVectorLayer
from qgis.gui import QgisInterface
from qgis.utils import iface

from .constants import geometry_types, python_to_qmetatype, qmetatype_to_python
from .converters import supabase_to_qgis_feature
from .logs import log
from .qgis_events import QGISDeleteEvent, QGISInsertEvent, QGISUpdateEvent
from .supabase_models import LayerAttribute, SupabaseFeature

iface: QgisInterface


class Layer:
    def __init__(
        self,
        name: str,
        supabase_layer_id: str,
        geometry_type: str,
        attributes: list[LayerAttribute] | None,
        commit_callback: Callable,
    ) -> None:
        self.name = name
        self.supabase_layer_id = supabase_layer_id
        self.geometry_type = geometry_type
        self.attributes: list[LayerAttribute] = attributes or []
        self.commit_callback = commit_callback

        self._qgis_id_to_supabase_id: dict[int, str] = {}
        self._supabase_id_to_qgis_id: dict[str, int] = {}

        self.manually_updated_supabase_ids: set[str] = set()

        self._qgis_events: list[
            QGISInsertEvent | QGISUpdateEvent | QGISDeleteEvent
        ] = []

        self._layer_attributes_modified: bool = False

        self._qgis_layer = None

    @property
    def qgis_layer(self) -> QgsVectorLayer:
        if self._qgis_layer is None:
            # create the layer
            self._qgis_layer = QgsVectorLayer(
                f"{geometry_types[self.geometry_type]}?crs=EPSG:4326&index=yes",
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

            # connect signals
            self._qgis_layer.committedFeaturesAdded.connect(self.on_event_added)
            self._qgis_layer.committedFeaturesRemoved.connect(self.on_event_removed)
            self._qgis_layer.committedAttributeValuesChanges.connect(
                self.on_event_attributes_changed
            )
            self._qgis_layer.committedGeometriesChanges.connect(
                self.on_event_attributes_changed
            )
            self._qgis_layer.committedAttributesAdded.connect(
                self.on_event_attributes_added
            )
            self._qgis_layer.committedAttributesDeleted.connect(
                self.on_event_attributes_deleted
            )
            self._qgis_layer.afterCommitChanges.connect(self.after_commit)

            # ignore warning about memory layers on quit
            self._qgis_layer.setCustomProperty("skipMemoryLayersCheck", 1)

        return self._qgis_layer

    def add_feature_id(self, qgis_id: int, supabase_id: str) -> None:
        self._qgis_id_to_supabase_id[qgis_id] = supabase_id
        self._supabase_id_to_qgis_id[supabase_id] = qgis_id

    def get_supabase_feature_id(self, qgis_id: int) -> str | None:
        return self._qgis_id_to_supabase_id.get(qgis_id)

    def get_qgis_feature_id(self, supabase_id: str) -> int | None:
        return self._supabase_id_to_qgis_id.get(supabase_id)

    def remove_supabase_feature_id(self, supabase_id: str) -> None:
        qgis_id = self._supabase_id_to_qgis_id.pop(supabase_id, None)
        if qgis_id is not None:
            self._qgis_id_to_supabase_id.pop(qgis_id, None)

    def _reset_edits(self) -> None:
        self._qgis_events = []
        self._layer_attributes_modified = False

    def reset(self) -> None:
        self._reset_edits()
        self._qgis_layer = None

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

    def get_qgis_feature(self, qgis_id: int) -> QgsFeature | None:
        feature = self.qgis_layer.getFeature(qgis_id)
        if not feature.isValid():
            return None
        return feature

    def on_event_added(self, layer_id: str, features: Iterable[QgsFeature]) -> None:
        """Called when features are added to the layer."""
        # remove echo of supabase_insert event
        features = [f for f in features if f.id() not in self._qgis_id_to_supabase_id]
        if not features:
            return
        self._qgis_events.append(QGISInsertEvent(list(features)))

    def on_event_removed(self, layer_id: str, fids: list[int]) -> None:
        """Called when features are removed from the layer."""
        # remove echo of supabase_delete event
        fids = [id_ for id_ in fids if id_ in self._qgis_id_to_supabase_id]
        if not fids:
            return
        self._qgis_events.append(QGISDeleteEvent(list(fids)))

    def on_event_attributes_changed(
        self, layer_id: str, values: dict[int, dict[int, Any]]
    ) -> None:
        """Called when the attributes of a feature are changed."""
        fids = []
        for id_ in values.keys():
            supabase_id = self._qgis_id_to_supabase_id.get(id_)
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

    def on_realtime_insert(self, feature: SupabaseFeature) -> None:
        """Called when an insert message is received from the realtime server."""

        if feature.id in self._supabase_id_to_qgis_id:
            return  # echo of a qgis_insert event

        log(f"Supabase InsertMessage: {feature.id}")

        self.qgis_layer.startEditing()
        try:
            qgis_feature = supabase_to_qgis_feature(feature, self)
            self.qgis_layer.dataProvider().addFeature(qgis_feature)
            self.add_feature_id(qgis_feature.id(), feature.id)
            self.qgis_layer.updateExtents()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)

    def on_realtime_update(self, feature: SupabaseFeature) -> None:
        """Called when an update message is received from the realtime server."""

        if feature.id in self.manually_updated_supabase_ids:
            self.manually_updated_supabase_ids.remove(feature.id)
            return  # echo of a qgis_update event

        log(f"Supabase UpdateMessage: {feature.id}")

        qgis_id = self._supabase_id_to_qgis_id.get(feature.id)
        if qgis_id is None:
            return
        qgis_feature = self.get_qgis_feature(qgis_id)
        if qgis_feature is None:
            return

        self.qgis_layer.startEditing()

        try:
            for attr_name, value in feature.attributes.items():
                field_idx = self.qgis_layer.fields().indexOf(attr_name)
                if field_idx >= 0:
                    qgis_feature.setAttribute(field_idx, value)
            if feature.geom:
                if feature.geom["type"] != "Point":
                    raise ValueError(
                        f"Geometry type {feature.geom['type']} not implemented"
                    )
                x, y, z = feature.geom["coordinates"]
                qgis_feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(x, y, z)))

            self.qgis_layer.updateFeature(qgis_feature)
            self.qgis_layer.commitChanges()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)

    def on_realtime_delete(self, supabase_feature_id: str) -> bool:
        """Called when a delete message is received from the realtime server."""
        qgis_id = self._supabase_id_to_qgis_id.get(supabase_feature_id)
        if qgis_id is None:
            return False  # echo of a qgis_delete event

        log(f"Supabase DeleteMessage: {supabase_feature_id}")

        self.qgis_layer.startEditing()

        try:
            self.qgis_layer.deleteFeature(qgis_id)
            self.qgis_layer.commitChanges()
            self._supabase_id_to_qgis_id.pop(supabase_feature_id)
            self._qgis_id_to_supabase_id.pop(qgis_id)
            self.qgis_layer.updateExtents()
        except:
            self.qgis_layer.rollBack()
            raise
        finally:
            iface.vectorLayerTools().stopEditing(self.qgis_layer)

        return True
