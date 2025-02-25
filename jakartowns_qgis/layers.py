from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgisInterface
from qgis.utils import iface

iface: QgisInterface


class LayerContainer:
    def __init__(self) -> None:
        self.layers: dict[str, str] = {}

    def load_layers(self) -> list[str]:
        return ["layer1", "layer2"]

    def add_layer(self, layer_name: str | None) -> None:
        if layer_name is None:
            return
        if layer_name in self.layers:
            return

        layer = QgsVectorLayer("Point", layer_name, "memory")
        QgsProject.instance().addMapLayer(layer, addToLegend=True)
        self.layers[layer_name] = layer.id()

    def remove_layer(self, layer_name: str | None) -> None:
        if layer_name is None:
            return
        if layer_name not in self.layers:
            return
        layer_id = self.layers[layer_name]
        QgsProject.instance().removeMapLayer(layer_id)
        del self.layers[layer_name]

    def remove_all_layers(self) -> None:
        if self.layers:
            for layer_id in self.layers.values():
                QgsProject.instance().removeMapLayer(layer_id)

            iface.mapCanvas().refreshAllLayers()
            self.layers.clear()
