from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from typing import Any, Callable

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeatureRequest,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.utils import iface

from .constants import anon_key, realtime_url
from .converters import qgis_layer_to_postgrest_layer, qgis_to_supabase_feature
from .layer import Layer
from .logs import log
from .qgis_events import QGISDeleteEvent, QGISInsertEvent, QGISUpdateEvent
from .supabase_events import (
    SupabaseDeleteMessage,
    SupabaseInsertMessage,
    SupabaseUpdateMessage,
    parse_message,
)
from .supabase_models import LayerAttribute, SupabaseFeature
from .supabase_postgrest import Postgrest
from .supabase_session import SupabaseSession
from .vendor.realtime import AsyncRealtimeClient

iface: QgisInterface


class Adapter:
    def __init__(self) -> None:
        self._loaded_layers: dict[str, Layer] = {}
        self._qgis_id_to_supabase_id: dict[str, str] = {}
        self._all_layers: dict[str, Layer] = {}
        self._session = SupabaseSession()
        self._postgrest_client = Postgrest(self._session)
        self._realtime: AsyncRealtimeClient | None = None
        self._realtime_thread_event = threading.Event()

    def fetch_layers(self) -> None:
        self._all_layers = {
            id_: Layer(
                name,
                id_,
                geometry_type,
                attributes=[LayerAttribute.from_json(a) for a in attributes],
                commit_callback=self._commit_callback,
            )
            for name, id_, geometry_type, attributes in self._postgrest_client.get_layers()
        }

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
                    supabase_feature = qgis_to_supabase_feature(feature, layer_id)
                    self._postgrest_client.add_feature(supabase_feature)
                    layer.add_feature_id(feature.id(), supabase_feature.id)
            elif isinstance(event, QGISUpdateEvent):
                log(f"QGISUpdateEvent: {len(event.ids)} features")
                for id_ in event.ids:
                    if not (feature := layer.get_qgis_feature(id_)):
                        continue
                    supabase_id = layer.get_supabase_feature_id(feature.id())
                    supabase_feature = qgis_to_supabase_feature(
                        feature, layer_id, supabase_id
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

    def is_loaded(self, id_or_name: str) -> bool:
        layer = self.get_layer(id_or_name)
        if layer is None:
            return False
        return layer.supabase_layer_id in self._loaded_layers

    def all_layer_names(self) -> list[str]:
        return [layer.name for layer in self._all_layers.values()]

    def get_layer(self, id_or_name_or_qgis_id: str | None) -> Layer | None:
        if id_or_name_or_qgis_id is None:
            return None
        if id_or_name_or_qgis_id in self._all_layers:
            return self._all_layers[id_or_name_or_qgis_id]
        if id_or_name_or_qgis_id in self.all_layer_names():
            return [
                layer
                for layer in self._all_layers.values()
                if layer.name == id_or_name_or_qgis_id
            ][0]
        if id_or_name_or_qgis_id in self._qgis_id_to_supabase_id:
            return self._all_layers[self._qgis_id_to_supabase_id[id_or_name_or_qgis_id]]
        return None

    def import_layer(self, layer: QgsVectorLayer) -> None:
        supabase_layer_id = str(uuid.uuid4())

        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        context = QgsProject.instance().transformContext()

        request = QgsFeatureRequest().setDestinationCrs(target_crs, context)
        features = list(layer.getFeatures(request))
        features = [f for f in features if not f.geometry().isNull()]

        postgrest_layer = qgis_layer_to_postgrest_layer(layer, supabase_layer_id)

        supabase_features = []
        feature_type = layer.geometryType().name  # type: ignore
        for feature in features:
            supabase_feature = qgis_to_supabase_feature(
                feature,
                supabase_layer_id,
                feature_type=feature_type,
                attribute_names=[a.name for a in postgrest_layer.attributes],
            )
            supabase_features.append(supabase_feature)

        self._postgrest_client.create_layer(postgrest_layer)
        self._postgrest_client.add_features(supabase_features)

        # Show a toast notification to the user
        iface.messageBar().pushMessage(
            "Jakarto layers",
            f"Imported {len(features)} features to '{postgrest_layer.name}' layer",
            level=Qgis.MessageLevel.Info,
            duration=5,  # Show for 5 seconds
        )

    def add_layer(
        self, id_or_name: str | None, callback: Callable[[bool], Any]
    ) -> None:
        if not (layer := self.get_layer(id_or_name)):
            callback(False)
            return
        if layer.supabase_layer_id in self._loaded_layers:
            callback(False)
            return

        def _sub_callback(features: list[SupabaseFeature]) -> None:
            layer.add_features_on_load(features)
            QgsProject.instance().addMapLayer(layer.qgis_layer, addToLegend=True)
            self._loaded_layers[layer.supabase_layer_id] = layer
            self._qgis_id_to_supabase_id[layer.qgis_layer.id()] = (
                layer.supabase_layer_id
            )
            callback(True)

        self._postgrest_client.get_features(
            layer.geometry_type,
            layer.supabase_layer_id,
            callback=_sub_callback,
        )

    def remove_layer(self, id_or_name: str | None) -> bool:
        if not (layer := self.get_layer(id_or_name)):
            return False
        if layer.supabase_layer_id not in self._loaded_layers:
            return False
        # this will trigger the on_layers_removed signal
        QgsProject.instance().removeMapLayer(layer.qgis_layer)
        return True

    def drop_layer(self, id_or_name: str | None) -> bool:
        if not (layer := self.get_layer(id_or_name)):
            return False
        if layer.supabase_layer_id not in self._all_layers:
            return False
        self._postgrest_client.drop_layer(layer.supabase_layer_id)
        self._all_layers.pop(layer.supabase_layer_id, None)
        return True

    def on_layers_removed(self, qgis_ids: list[str]) -> bool:
        """Called when layers are removed from the map (not by the plugin)."""
        removed = False
        for qgis_id in qgis_ids:
            if qgis_id not in self._qgis_id_to_supabase_id:
                continue
            supabase_id = self._qgis_id_to_supabase_id[qgis_id]
            layer = self._loaded_layers[supabase_id]
            layer.reset()
            self._loaded_layers.pop(supabase_id, None)
            self._qgis_id_to_supabase_id.pop(qgis_id, None)
            removed = True

        return removed

    def remove_all_layers(self) -> None:
        if self._loaded_layers:
            for supabase_id in list(self._loaded_layers.keys()):
                self.remove_layer(supabase_id)
            iface.mapCanvas().refresh()
            self._loaded_layers.clear()
            self._qgis_id_to_supabase_id.clear()

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
                        callback=self.on_supabase_realtime_event,
                    )
                    .subscribe()
                )
                while not self._realtime_thread_event.is_set():
                    await asyncio.sleep(0.1)

            try:
                asyncio.run(_run_realtime())
            except Exception:
                if not self._realtime_thread_event.is_set():
                    raise

        self._realtime_thread_event = threading.Event()
        thread = threading.Thread(target=_thread_func, daemon=True)
        thread.start()

    def on_supabase_realtime_event(self, event_data: dict) -> None:
        try:
            message = parse_message(event_data)
            if message is None:
                return
            if isinstance(message, SupabaseInsertMessage):
                layer_id = message.record.layer
                if layer_id not in self._loaded_layers:
                    return
                self._loaded_layers[layer_id].on_realtime_insert(message.record)
            elif isinstance(message, SupabaseUpdateMessage):
                layer_id = message.record.layer
                if layer_id not in self._loaded_layers:
                    return
                self._loaded_layers[layer_id].on_realtime_update(message.record)
            elif isinstance(message, SupabaseDeleteMessage):
                for layer in self._loaded_layers.values():
                    if layer.on_realtime_delete(message.old_record_id):
                        break
        except Exception:
            traceback.print_exc()

    def stop_realtime(self) -> None:
        self._realtime_thread_event.set()
        self._realtime = None

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        self.stop_realtime()
        self._session.close()
