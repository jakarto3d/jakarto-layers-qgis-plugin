from qgis.core import QgsProject
from qgis.gui import QgisInterface
from qgis.utils import iface

from .layer import Layer
from .postgrest import Postgrest

iface: QgisInterface


class LayerContainer:
    def __init__(self) -> None:
        self._loaded_layers: dict[str, Layer] = {}
        self._qgis_id_to_source_id: dict[str, str] = {}
        self._all_layers: dict[str, Layer] = {}
        self._layer_name_to_source_id: dict[str, str] = {}
        self._postgrest_client = Postgrest()

    def fetch_layers(self) -> None:
        self._all_layers = {
            id_: Layer(name, id_, geometry_type)
            for name, id_, geometry_type in self._postgrest_client.get_layers()
        }
        self._layer_name_to_source_id = {
            layer.name: layer.source_id for layer in self._all_layers.values()
        }

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
