from __future__ import annotations

import asyncio
import threading
import traceback

from qgis.core import QgsProject
from qgis.gui import QgisInterface
from qgis.utils import iface

from .constants import anon_key, realtime_url
from .layer import Layer, LayerAttribute
from .postgrest import Postgrest, PostgrestFeature
from .realtime_websockets import UpdateMessage, parse_message
from .vendor.realtime import AsyncRealtimeClient

iface: QgisInterface


class LayerContainer:
    def __init__(self) -> None:
        self._loaded_layers: dict[str, Layer] = {}
        self._qgis_id_to_source_id: dict[str, str] = {}
        self._all_layers: dict[str, Layer] = {}
        self._layer_name_to_source_id: dict[str, str] = {}
        self._postgrest_client = Postgrest()
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
        self._layer_name_to_source_id = {
            layer.name: layer.source_id for layer in self._all_layers.values()
        }

    def _commit_callback(
        self,
        layer: Layer,
        added: list[PostgrestFeature],
        removed: list[PostgrestFeature],
        attributes_changed: list[PostgrestFeature],
        geometry_changed: list[PostgrestFeature],
        layer_attributes_modified: bool,
    ) -> None:
        """Update the database tables after a qgis manual edit.

        We should batch these for performance (not possible with Postgrest),
        but for this prototype we'll just do one request per modification.
        """
        for feature in added:
            self._postgrest_client.add_feature(feature)
        for feature in removed:
            self._postgrest_client.remove_feature(feature)
        for feature in attributes_changed + geometry_changed:
            self._postgrest_client.update_feature(feature)
        if layer_attributes_modified:
            # We should also remove any unused attributes
            # in the features, but this would make one request for every feature.
            # We'll do it when we have a better backend than Postgrest.
            self._postgrest_client.update_attributes(
                layer.source_id,
                [{"name": a.name, "type": a.type} for a in layer.attributes],
            )

    def is_loaded(self, id_or_name: str) -> bool:
        layer = self.get_layer(id_or_name)
        if layer is None:
            return False
        return layer.source_id in self._loaded_layers

    def all_layer_names(self) -> list[str]:
        return list(self._layer_name_to_source_id.keys())

    def get_layer(self, id_or_name_or_qgis_id: str | None) -> Layer | None:
        if id_or_name_or_qgis_id is None:
            return None
        if id_or_name_or_qgis_id in self._all_layers:
            return self._all_layers[id_or_name_or_qgis_id]
        if id_or_name_or_qgis_id in self._layer_name_to_source_id:
            return self._all_layers[
                self._layer_name_to_source_id[id_or_name_or_qgis_id]
            ]
        if id_or_name_or_qgis_id in self._qgis_id_to_source_id:
            return self._all_layers[self._qgis_id_to_source_id[id_or_name_or_qgis_id]]
        return None

    def add_layer(self, id_or_name: str | None) -> bool:
        if not (layer := self.get_layer(id_or_name)):
            return False
        if layer.source_id in self._loaded_layers:
            return False

        features = self._postgrest_client.get_features(
            layer.geometry_type, layer.source_id
        )
        layer.add_features(features)
        QgsProject.instance().addMapLayer(layer.qgis_layer, addToLegend=True)
        self._loaded_layers[layer.source_id] = layer
        self._qgis_id_to_source_id[layer.qgis_layer.id()] = layer.source_id
        return True

    def remove_layer(self, id_or_name: str | None) -> bool:
        if not (layer := self.get_layer(id_or_name)):
            return False
        if layer.source_id not in self._loaded_layers:
            return False
        # this will trigger the on_layers_removed signal
        QgsProject.instance().removeMapLayer(layer.qgis_layer)
        return True

    def on_layers_removed(self, qgis_ids: list[str]) -> bool:
        """Called when layers are removed from the map (not by the plugin)."""
        removed = False
        for qgis_id in qgis_ids:
            if qgis_id not in self._qgis_id_to_source_id:
                continue
            source_id = self._qgis_id_to_source_id[qgis_id]
            layer = self._loaded_layers[source_id]
            layer.reset()
            self._loaded_layers.pop(source_id, None)
            self._qgis_id_to_source_id.pop(qgis_id, None)
            removed = True

        return removed

    def remove_all_layers(self) -> None:
        if self._loaded_layers:
            for source_id in list(self._loaded_layers.keys()):
                self.remove_layer(source_id)
            iface.mapCanvas().refresh()
            self._loaded_layers.clear()
            self._qgis_id_to_source_id.clear()

    def start_realtime(self) -> None:
        def _thread_func() -> None:
            async def _run_realtime():
                self._realtime = AsyncRealtimeClient(realtime_url, token=anon_key)
                await self._realtime.connect()
                await self._realtime.set_auth(self._postgrest_client._access_token)
                await (
                    self._realtime.channel("points")
                    .on_postgres_changes("*", callback=self.on_postgres_changes)
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

    def on_postgres_changes(self, data: dict) -> None:
        try:
            message: UpdateMessage | None = parse_message(data)
            if message is None:
                return
            if isinstance(message, UpdateMessage):
                layer_id = message.record.layer
                if layer_id not in self._loaded_layers:
                    return
                layer = self._loaded_layers[layer_id]
                layer.update_feature(message.record)
        except Exception:
            traceback.print_exc()

    def stop_realtime(self) -> None:
        self._realtime_thread_event.set()
