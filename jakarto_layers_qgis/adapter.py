from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from itertools import chain
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtBoundSignal, pyqtSignal
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.utils import iface

from .constants import anon_key, realtime_url
from .converters import qgis_layer_to_supabase_layer, qgis_to_supabase_feature
from .layer import Layer
from .logs import log
from .presence import PresenceManager
from .qgis_events import QGISDeleteEvent, QGISInsertEvent, QGISUpdateEvent
from .supabase_events import (
    SupabaseDeleteMessage,
    SupabaseInsertMessage,
    SupabaseUpdateMessage,
    parse_message,
)
from .supabase_models import SupabaseFeature, SupabaseLayer
from .supabase_postgrest import Postgrest
from .supabase_session import SupabaseSession
from .vendor.realtime import AsyncRealtimeClient

iface: QgisInterface


class Adapter(QObject):
    realtime_event_received = pyqtSignal(dict)  # Signal for realtime events

    def __init__(self) -> None:
        super().__init__()
        self._loaded_layers: dict[str, Layer] = {}
        self._qgis_layer_id_to_supabase_id: dict[str, str] = {}
        self._all_layers: dict[str, Layer] = {}
        self._session = SupabaseSession()
        self._postgrest_client = Postgrest(self._session)
        self._realtime: AsyncRealtimeClient | None = None
        self._realtime_thread_event = threading.Event()
        self._presence_manager = PresenceManager()

        # Connect the signal to the handler
        self.realtime_event_received.connect(self.on_supabase_realtime_event)

    def fetch_layers(self) -> None:
        all_layers = {
            supabase_layer.id: Layer.from_supabase_layer(
                supabase_layer,
                self._commit_callback,
            )
            for supabase_layer in self._postgrest_client.get_layers()
        }

        # remove layers that are not in the loaded layers
        for layer_id in list(self._all_layers.keys()):
            if layer_id not in all_layers:
                self._all_layers.pop(layer_id, None)

        # add new layers
        for layer_id, layer in all_layers.items():
            if layer_id in self._all_layers:
                continue
            self._all_layers[layer_id] = layer

    def _commit_callback(
        self,
        layer: Layer,
        events: list[QGISInsertEvent | QGISUpdateEvent | QGISDeleteEvent],
        layer_attributes_modified: bool,
    ) -> None:
        """Update the database tables after a qgis manual edit.

        We should batch these for performance (maybe upserts with Postgrest),
        but for this prototype we'll just do one request per modification.
        """
        layer_id = layer.supabase_layer_id

        for event in events:
            if isinstance(event, QGISInsertEvent):
                log(f"QGISInsertEvent: {len(event.features)} features")
                for feature in event.features:
                    supabase_feature = qgis_to_supabase_feature(
                        feature,
                        supabase_layer_id=layer_id,
                        attribute_names=[a.name() for a in layer.qgis_layer.fields()],
                    )
                    self._postgrest_client.add_feature(supabase_feature)
                    layer.add_feature_id(feature.id(), supabase_feature.id)
            elif isinstance(event, QGISUpdateEvent):
                log(f"QGISUpdateEvent: {len(event.ids)} features")
                for id_ in event.ids:
                    if not (feature := layer.get_qgis_feature(id_)):
                        continue
                    supabase_id = layer.get_supabase_feature_id(feature.id())
                    supabase_feature = qgis_to_supabase_feature(
                        feature,
                        supabase_layer_id=layer_id,
                        supabase_feature_id=supabase_id,
                        attribute_names=[a.name() for a in layer.qgis_layer.fields()],
                    )
                    self._postgrest_client.update_feature(supabase_feature)
                    layer.manually_updated_supabase_ids.add(supabase_feature.id)
            elif isinstance(event, QGISDeleteEvent):
                log(f"QGISDeleteEvent: {len(event.ids)} features")
                for id_ in event.ids:
                    supabase_id = layer.get_supabase_feature_id(id_)
                    if supabase_id is None:
                        continue
                    self._postgrest_client.remove_feature(supabase_id)
                    layer.remove_supabase_feature_id(supabase_id)

        if layer_attributes_modified:
            self._postgrest_client.update_attributes(
                layer_id,
                [{"name": a.name, "type": a.type} for a in layer.attributes],
            )

    def is_loaded(self, supabase_id: str) -> bool:
        layer = self.get_layer(supabase_id)
        if layer is None:
            return False
        return layer.supabase_layer_id in self._loaded_layers

    @property
    def has_presence_point(self) -> pyqtBoundSignal:
        return self._presence_manager.has_presence_point

    def set_jakartowns_follow(self, value: bool) -> None:
        self._presence_manager.center_view_on_position_update = value
        self._presence_manager.center_view_if_active()

    def all_layer_properties(self, with_temporary: bool = False) -> list[tuple]:
        """For display in the layer tree."""
        all_layers = self._all_layers.copy()
        if not with_temporary:
            all_layers = {k: v for k, v in all_layers.items() if not v.temporary}

        layers_data = {}
        # first pass to get all layers
        for layer_id, layer in all_layers.items():
            layers_data[layer_id] = (
                layer.name,
                layer.geometry_type,
                layer.supabase_srid,
                layer_id,
                [],
            )
        # second pass to get parent-child relationships
        for layer_id, layer in all_layers.items():
            parent_id = layer.supabase_parent_layer_id
            if parent_id is None:
                continue
            if parent_id not in layers_data:
                # we don't have permissions to see the parent layer
                layer.supabase_parent_layer_id = None
                continue
            layers_data[parent_id][4].append(layers_data[layer_id])
        # third pass to get top-level layers
        top_layers = [
            layer_data
            for layer_id, layer_data in layers_data.items()
            if all_layers[layer_id].supabase_parent_layer_id is None
        ]
        return top_layers

    def get_layer(self, supabase_id: str | None) -> Layer | None:
        if supabase_id is None:
            return None
        if supabase_id in self._all_layers:
            return self._all_layers[supabase_id]
        return None

    def _supabase_layer_from_qgis_features(
        self,
        qgis_layer: QgsVectorLayer,
        qgis_features: list[QgsFeature],
        *,
        layer_name: str | None = None,
        parent_layer: Layer | None = None,
        temporary_layer: bool = False,
    ) -> tuple[SupabaseLayer, list[SupabaseFeature]]:
        """Create a new supabase layer from a list of qgis features.

        Args:
            layer: The qgis layer to create the supabase layer from
            features: The features to create the supabase layer from
            layer_name: The name of the supabase layer
            parent_layer: The parent layer of the supabase layer (to create a sub-layer)

        Returns:
            A tuple containing the supabase layer and the list of supabase features
        """
        # get the srid from the layer
        # must correspond with supported crs in jakproj
        srid = qgis_layer.crs().authid()
        try:
            srid = int(srid.split(":")[-1])
        except Exception:
            raise ValueError(f"Unsupported CRS: {srid}")

        allowed_srids = list(
            chain(
                range(2945, 2953),  # NAD83(CSRS) / MTM
                [26891],  # NAD83 / MTM
                range(32183, 32192),  # NAD83 / MTM
                [4326],  # WGS84
                range(6346, 6348),  # NAD83(2011) / UTM
                range(26910, 26920),  # NAD83 / UTM
                range(32610, 32620),  # WGS 84 / UTM
                [2154],  # RGF93 v1 / Lambert-93 -- France
            )
        )
        if srid not in allowed_srids:
            raise ValueError(f"Unsupported CRS: {srid}")
        # reproject to a known CRS ?
        # target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        # context = QgsProject.instance().transformContext()
        # request = QgsFeatureRequest().setDestinationCrs(target_crs, context)
        # features = list(layer.getFeatures(request))
        supabase_layer_id = str(uuid.uuid4())
        supabase_layer: SupabaseLayer = qgis_layer_to_supabase_layer(
            qgis_layer,
            supabase_layer_id,
            srid=srid,
            layer_name=layer_name,
            temporary_layer=temporary_layer,
        )

        supabase_features = []
        feature_type = qgis_layer.geometryType().name  # type: ignore
        attribute_names = [a.name() for a in qgis_layer.fields()]
        for qgis_feature in qgis_features:
            supabase_feature = qgis_to_supabase_feature(
                qgis_feature,
                supabase_layer_id=supabase_layer_id,
                feature_type=feature_type,
                attribute_names=attribute_names,
            )
            if parent_layer is not None:
                # set the parent id for the supabase feature (for sub-layers)
                supabase_feature.parent_id = parent_layer.get_supabase_feature_id(
                    qgis_feature.id()
                )
            supabase_features.append(supabase_feature)

        if parent_layer is not None:
            # set the parent id for the supabase layer (for sub-layers)
            supabase_layer.parent_id = parent_layer.supabase_layer_id

        return supabase_layer, supabase_features

    def import_layer(
        self, qgis_layer: QgsVectorLayer, temporary_layer: bool = False
    ) -> tuple[Layer, list[tuple[int, str]]]:
        qgis_features = [
            f for f in qgis_layer.getFeatures() if not f.geometry().isNull()
        ]

        supabase_layer, supabase_features = self._supabase_layer_from_qgis_features(
            qgis_layer,
            qgis_features,
            temporary_layer=temporary_layer,
        )
        qgis_feature_id_to_supabase_feature_id = [
            (qgis_feature.id(), supabase_feature.id)
            for qgis_feature, supabase_feature in zip(qgis_features, supabase_features)
        ]

        self._postgrest_client.create_layer(supabase_layer)
        if supabase_features:
            self._postgrest_client.add_features(supabase_features)

        layer = Layer.from_supabase_layer(
            supabase_layer,
            self._commit_callback,
            qgis_layer=qgis_layer if temporary_layer else None,
        )

        self._all_layers[supabase_layer.id] = layer

        if not temporary_layer:
            iface.messageBar().pushMessage(
                "Jakarto layers",
                f"Imported {len(supabase_features)} features "
                f"to '{supabase_layer.name}' layer",
                level=Qgis.MessageLevel.Success,
                duration=5,
            )

        return layer, qgis_feature_id_to_supabase_feature_id

    def sync_layer_with_jakartowns(self, qgis_layer: QgsVectorLayer) -> Layer:
        self.unsync_layer_with_jakartowns(qgis_layer)

        layer: Layer
        qgis_feature_id_to_supabase_feature_id: list[tuple[int, str]]
        layer, qgis_feature_id_to_supabase_feature_id = self.import_layer(
            qgis_layer, temporary_layer=True
        )

        qgis_layer.setCustomProperty(
            "jakarto_sync_with_jakartowns", layer.supabase_layer_id
        )

        self._all_layers[layer.supabase_layer_id] = layer
        self._loaded_layers[layer.supabase_layer_id] = layer
        self._qgis_layer_id_to_supabase_id[layer.qgis_layer.id()] = (
            layer.supabase_layer_id
        )

        for qgis_id, supabase_id in qgis_feature_id_to_supabase_feature_id:
            layer.add_feature_id(qgis_id, supabase_id)

        self.start_realtime()

        return layer

    def unsync_layer_with_jakartowns(self, qgis_layer: QgsVectorLayer) -> bool:
        supabase_id = qgis_layer.customProperty("jakarto_sync_with_jakartowns", None)
        if supabase_id is None:
            return False
        layer = self._all_layers.get(supabase_id)
        self._loaded_layers.pop(supabase_id, None)
        self._all_layers.pop(supabase_id, None)
        if layer is not None:
            layer.disconnect_all_signals()
            layer.set_layer_tree_icon(False)
        self._postgrest_client.drop_layer(supabase_id)
        qgis_layer.removeCustomProperty("jakarto_sync_with_jakartowns")
        return True

    def add_layer(
        self, supabase_id: str | None, callback: Callable[[bool], Any]
    ) -> None:
        if not (layer := self.get_layer(supabase_id)):
            callback(False)
            return
        if layer.supabase_layer_id in self._loaded_layers:
            callback(False)
            return

        def _sub_callback(features: list[SupabaseFeature]) -> None:
            layer.add_features_on_load(features)
            QgsProject.instance().addMapLayer(layer.qgis_layer, addToLegend=True)
            self._loaded_layers[layer.supabase_layer_id] = layer
            self._qgis_layer_id_to_supabase_id[layer.qgis_layer.id()] = (
                layer.supabase_layer_id
            )
            callback(True)

        self._postgrest_client.get_features(
            layer.geometry_type,
            layer.supabase_layer_id,
            callback=_sub_callback,
        )

    def setup_auth(self, email: str, password: str) -> bool:
        """This is meant to be called when the plugin is needed (on action click for example)."""
        return self._session.setup_auth(email, password)

    def remove_layer(self, supabase_id: str | None) -> bool:
        if not (layer := self.get_layer(supabase_id)):
            return False
        if layer.supabase_layer_id not in self._loaded_layers:
            return False
        if layer.temporary:
            layer.set_layer_tree_icon(False)
        else:
            # this will trigger the on_layers_removed signal
            QgsProject.instance().removeMapLayer(layer.qgis_layer)

        return True

    def drop_layer(self, supabase_id: str) -> bool:
        self.remove_layer(supabase_id)
        self._postgrest_client.drop_layer(supabase_id)
        self._all_layers.pop(supabase_id, None)
        return True

    def on_layers_removed(self, qgis_ids: list[str]) -> bool:
        """Called when layers are removed from the map (not by the plugin)."""
        removed = False
        for qgis_id in qgis_ids:
            if qgis_id not in self._qgis_layer_id_to_supabase_id:
                continue
            supabase_id = self._qgis_layer_id_to_supabase_id[qgis_id]
            if layer := self._loaded_layers.get(supabase_id):
                layer.reset()
            self._loaded_layers.pop(supabase_id, None)
            self._qgis_layer_id_to_supabase_id.pop(qgis_id, None)
            removed = True

        return removed

    def remove_all_layers(self) -> None:
        if self._loaded_layers:
            for supabase_id in list(self._loaded_layers.keys()):
                self.remove_layer(supabase_id)
            iface.mapCanvas().refresh()
            self._loaded_layers.clear()
            self._qgis_layer_id_to_supabase_id.clear()

    def start_realtime(self) -> None:
        def _thread_func() -> None:
            async def _run_realtime():
                self._realtime = AsyncRealtimeClient(realtime_url, token=anon_key)
                await self._realtime.connect()
                await self._realtime.set_auth(self._session.access_token)
                await (
                    self._realtime.channel("points")
                    .on_postgres_changes(
                        "*",
                        table="points",
                        callback=self.realtime_event_received.emit,
                    )
                    .subscribe()
                )

                channel = self._realtime.channel(
                    # this channel is private, only the user with the same id can subscribe to it
                    # this is configured in the realtime.messages table's RLS policies
                    f"jakartowns_positions_{self._session.user_id}",
                    params={
                        "config": {
                            "broadcast": {"ack": False, "self": False},
                            "presence": {"key": str(uuid.uuid4())},
                            "private": True,
                        }
                    },
                )
                await self._presence_manager.subscribe_channel(channel)

                while not self._realtime_thread_event.is_set():
                    await asyncio.sleep(0.1)

            try:
                asyncio.run(_run_realtime())
            except Exception:
                if not self._realtime_thread_event.is_set():
                    raise

        if self._realtime is None:
            self._realtime_thread_event = threading.Event()
            thread = threading.Thread(target=_thread_func, daemon=True)
            thread.start()

    def on_supabase_realtime_event(
        self, event_data: dict, only_print_errors: bool = True
    ) -> None:
        """Handle realtime events in the main thread."""
        try:
            message = parse_message(event_data)
            if message is None:
                return
            if isinstance(message, SupabaseInsertMessage):
                layer_id = message.record.layer_id
                if layer_id not in self._loaded_layers:
                    return
                self._loaded_layers[layer_id].on_realtime_insert(message.record)
            elif isinstance(message, SupabaseUpdateMessage):
                layer_id = message.record.layer_id
                if layer_id not in self._loaded_layers:
                    return
                self._loaded_layers[layer_id].on_realtime_update(message.record)
            elif isinstance(message, SupabaseDeleteMessage):
                for layer in self._loaded_layers.values():
                    if layer.on_realtime_delete(message.old_record_id):
                        break
        except Exception:
            if only_print_errors:
                traceback.print_exc()
            else:
                raise

    def stop_realtime(self) -> None:
        self._realtime_thread_event.set()
        self._realtime = None

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        self.remove_all_layers()
        self._presence_manager.close()
        self.stop_realtime()
        self._session.close()

    def merge_sub_layer(self, supabase_id: str | None) -> None:
        if not (layer := self.get_layer(supabase_id)):
            return
        if layer.supabase_parent_layer_id is None:
            return
        self._postgrest_client.merge_sub_layer(layer.supabase_layer_id)
        self.remove_layer(layer.supabase_layer_id)
        self._all_layers.pop(layer.supabase_layer_id, None)

    def create_sub_layer(self, parent_layer: Layer, new_layer_name: str) -> None:
        """Create a new sub-layer from selected features of the parent layer.

        Args:
            parent_layer: The parent layer
            new_layer_name: Name for the new sub-layer
        """
        selected_features = parent_layer.qgis_layer.selectedFeatures()
        if not selected_features:
            return

        postgrest_layer, supabase_features = self._supabase_layer_from_qgis_features(
            parent_layer.qgis_layer,
            selected_features,
            layer_name=new_layer_name,
            parent_layer=parent_layer,
            temporary_layer=False,
        )

        self._postgrest_client.create_layer(postgrest_layer)
        self._postgrest_client.add_features(supabase_features)

        new_layer = Layer.from_supabase_layer(
            postgrest_layer,
            self._commit_callback,
        )
        self._all_layers[postgrest_layer.id] = new_layer

        iface.messageBar().pushMessage(
            "Jakarto layers",
            f"Created sub-layer '{postgrest_layer.name}' "
            f"from {len(selected_features)} features",
            level=Qgis.MessageLevel.Success,
            duration=5,
        )

    def rename_layer(self, supabase_id: str | None, new_name: str) -> None:
        """Rename a layer.

        Args:
            supabase_id: The ID of the layer to rename
            new_name: The new name for the layer
        """
        if not (layer := self.get_layer(supabase_id)):
            return
        self._postgrest_client.rename_layer(layer.supabase_layer_id, new_name)
        layer.name = new_name
        if layer.qgis_layer is not None:
            layer.qgis_layer.setName(new_name)
