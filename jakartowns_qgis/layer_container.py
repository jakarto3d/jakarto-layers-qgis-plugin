from qgis.core import QgsProject
from qgis.gui import QgisInterface
from qgis.utils import iface

from .layer import Layer

iface: QgisInterface


class LayerContainer:
    def __init__(self) -> None:
        self.layers: dict[str, Layer] = {}

    def load_layers(self) -> list[Layer]:
        return [Layer("layer1"), Layer("layer2")]

    def add_layer(self, layer_name: str | None) -> None:
        if layer_name is None or layer_name in self.layers:
            return

        layer = Layer(layer_name)
        QgsProject.instance().addMapLayer(layer.layer, addToLegend=True)
        self.layers[layer_name] = layer

    def remove_layer(self, layer_name: str | None) -> None:
        if layer_name is None or layer_name not in self.layers:
            return

        layer = self.layers[layer_name]
        QgsProject.instance().removeMapLayer(layer.id)
        del self.layers[layer_name]

    def remove_all_layers(self) -> None:
        if self.layers:
            for layer_id in self.layers.values():
                QgsProject.instance().removeMapLayer(layer_id.id)

            iface.mapCanvas().refreshAllLayers()
            self.layers.clear()
