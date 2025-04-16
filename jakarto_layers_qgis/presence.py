from time import time
from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsProperty,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.utils import iface

from .constants import RESOURCES_DIR, python_to_qmetatype
from .vendor.realtime import AsyncRealtimeChannel

iface: QgisInterface

PRESENCE_LAYER_SRID = 4326


class PresenceManager(QObject):
    """Manages presence states and their visualization in QGIS."""

    presence_update = pyqtSignal()  # Signal for presence updates
    has_presence_point = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._presence_layer: QgsVectorLayer | None = None
        self._presence_states: dict[str, dict[str, Any]] = {}
        self._last_presence_point: dict[str, tuple[QgsGeometry, float]] = {}
        self.center_view_on_position_update = False

        self.presence_update.connect(self._update_presence_layer)

    async def subscribe_channel(self, channel: AsyncRealtimeChannel) -> None:
        def on_presence_join(key, curr_presences, joined_presences):
            for joined in joined_presences:
                presence_client_id = joined["presence_client_id"]
                self._presence_states.setdefault(presence_client_id, {})

        def on_presence_leave(key, curr_presences, left_presences):
            for left in left_presences:
                presence_client_id = left["presence_client_id"]
                self._presence_states.pop(presence_client_id, None)
                self._last_presence_point.pop(presence_client_id, None)
                self.presence_update.emit()

        def on_position_update(payload):
            if payload.get("event") != "jakartowns_position":
                return
            payload = payload["payload"]
            presence_client_id = payload["presence_client_id"]
            if not all(k in payload for k in ["x", "y", "srid"]):
                return
            self._presence_states[presence_client_id] = {
                "x": payload["x"],
                "y": payload["y"],
                "srid": payload["srid"],
                "rotation": payload.get("rotation", 0),
            }
            self.presence_update.emit()

        await (
            channel.on_presence_join(callback=on_presence_join)
            .on_presence_leave(callback=on_presence_leave)
            .on_broadcast("jakartowns_position", callback=on_position_update)
            .subscribe()
        )

    @property
    def presence_layer(self):
        if self._presence_layer is None:
            self._presence_layer = QgsVectorLayer(
                f"Point?crs=EPSG:{PRESENCE_LAYER_SRID}&index=yes",
                "Jakartowns positions",
                "memory",
            )
            self._presence_layer.setCustomProperty(
                "jakarto_positions_presence_layer", "1"
            )
            # Add fields for presence info
            self._presence_layer.dataProvider().addAttributes(
                [QgsField("rotation", python_to_qmetatype["float"])]
            )
            self._presence_layer.updateFields()

            # Style the layer with a custom SVG marker
            symbol = QgsMarkerSymbol()
            svg_path = str(RESOURCES_DIR / "presence_marker.svg")
            svg_layer = QgsSvgMarkerSymbolLayer(svg_path)
            svg_layer.setSize(10)
            symbol.changeSymbolLayer(0, svg_layer)

            # Set up data-defined rotation
            symbol.setDataDefinedAngle(QgsProperty.fromField("rotation"))
            renderer = QgsSingleSymbolRenderer(symbol)
            self._presence_layer.setRenderer(renderer)

            # Add to project if not already added
            if self._presence_layer.id() not in QgsProject.instance().mapLayers():
                QgsProject.instance().addMapLayer(self._presence_layer, False)
                root = QgsProject.instance().layerTreeRoot()
                root.insertLayer(0, self._presence_layer)

        return self._presence_layer

    def _update_presence_layer(self) -> None:
        """Update the presence layer with current presence states."""
        provider = self.presence_layer.dataProvider()
        provider.truncate()

        features = []
        for client_id, state in self._presence_states.items():
            if not all(k in state for k in ["x", "y", "srid", "rotation"]):
                continue
            feature = QgsFeature()
            point = QgsPointXY(state["x"], state["y"])
            geom = QgsGeometry.fromPointXY(point)
            if state["srid"] != PRESENCE_LAYER_SRID:
                geom.transform(
                    QgsCoordinateTransform(
                        QgsCoordinateReferenceSystem(state["srid"]),
                        QgsCoordinateReferenceSystem(PRESENCE_LAYER_SRID),
                        QgsProject.instance().transformContext(),
                    )
                )
            self._last_presence_point[client_id] = (geom, time())
            feature.setGeometry(geom)
            rotation_deg = -1 * state["rotation"] * 180 / 3.141592
            feature.setAttributes([rotation_deg])
            features.append(feature)

        provider.addFeatures(features)
        self.presence_layer.updateExtents()
        self.presence_layer.triggerRepaint()

        self.has_presence_point.emit(bool(self._last_presence_point))
        self.center_view_if_active()

    def center_view_if_active(self) -> None:
        if not self.center_view_on_position_update:
            return
        if not bool(self._last_presence_point):
            return
        point_geom, _ = max(
            self._last_presence_point.values(), key=lambda x: x[1]
        )  # max by time

        # Transform point to map canvas CRS
        canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
        transform_context = QgsProject.instance().transformContext()
        point_geom.transform(
            QgsCoordinateTransform(
                QgsCoordinateReferenceSystem(PRESENCE_LAYER_SRID),
                canvas_crs,
                transform_context,
            )
        )

        iface.mapCanvas().setCenter(point_geom.asPoint())
        iface.mapCanvas().refresh()

    def close(self) -> None:
        if self._presence_layer is not None:
            try:
                QgsProject.instance().removeMapLayer(self._presence_layer)
                iface.mapCanvas().refresh()
            except RuntimeError:
                pass
            self._presence_layer = None

    def __del__(self) -> None:
        self.close()
