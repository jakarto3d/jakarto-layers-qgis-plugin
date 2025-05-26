import asyncio
import queue
import threading
from dataclasses import dataclass
from time import time
from typing import Optional

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

from .constants import python_to_qmetatype
from .ui import utils
from .vendor.realtime import AsyncRealtimeChannel

iface: QgisInterface

PRESENCE_LAYER_SRID = 4326


class PresenceManager(QObject):
    """Manages presence states and their visualization in QGIS."""

    presence_update = pyqtSignal()  # Signal for presence updates
    has_presence_point = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._presence_layer: Optional[QgsVectorLayer] = None
        self._presence_states: dict[str, Optional[PresencePoint]] = {}
        # _last_presence_point is to keep track of the last position that moved
        # so we can center the view on it
        self._last_presence_point: dict[str, PresencePoint] = {}

        self._channel: Optional[AsyncRealtimeChannel] = None
        self._send_broadcast_queue = queue.Queue()
        self._send_broadcast_thread: Optional[threading.Thread] = None
        self.center_view_on_position_update = False
        self.send_jakartowns_move_requests = True

        self.presence_update.connect(self._update_presence_layer)

    async def subscribe_channel(self, channel: AsyncRealtimeChannel) -> None:
        def on_presence_join(key, curr_presences, joined_presences):
            for joined in joined_presences:
                presence_client_id = joined["presence_client_id"]
                self._presence_states.setdefault(presence_client_id, None)

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
            self._presence_states[presence_client_id] = PresencePoint(
                x=payload["x"],
                y=payload["y"],
                srid=payload["srid"],
                rotation=payload.get("rotation", 0),
                time=time(),
            )
            self.presence_update.emit()

        await (
            channel.on_presence_join(callback=on_presence_join)
            .on_presence_leave(callback=on_presence_leave)
            .on_broadcast("jakartowns_position", callback=on_position_update)
            .subscribe()
        )
        self._channel = channel

        self._start_send_broadcast_thread()

    def _start_send_broadcast_thread(self):
        def thread_target():
            async def run():
                while True:
                    payload = self._send_broadcast_queue.get()
                    if self._channel is None:
                        continue
                    if payload is None:
                        break
                    event, data = payload
                    await self._channel.send_broadcast(event=event, data=data)

            asyncio.run(run())

        self._send_broadcast_thread = threading.Thread(
            target=thread_target, daemon=True
        )
        self._send_broadcast_thread.start()

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
            self._presence_layer.setCustomProperty("skipMemoryLayersCheck", 1)
            # Add fields for presence info
            self._presence_layer.dataProvider().addAttributes(
                [QgsField("rotation", python_to_qmetatype["float"])]
            )
            self._presence_layer.updateFields()

            # Style the layer with a custom SVG marker
            symbol = QgsMarkerSymbol()
            svg_path = str(utils.icon_path("presence-marker.svg"))
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
                tree_root = QgsProject.instance().layerTreeRoot()
                tree_root.insertLayer(0, self._presence_layer)
                layer_node = tree_root.findLayer(self._presence_layer.id())
                if layer_node is not None:
                    tree_view = iface.layerTreeView()
                    for indicator in tree_view.indicators(layer_node):
                        tree_view.removeIndicator(layer_node, indicator)

        return self._presence_layer

    def _update_presence_layer(self) -> None:
        """Update the presence layer with current presence states."""
        provider = self.presence_layer.dataProvider()
        provider.truncate()

        features = []
        for client_id, presence_point in self._presence_states.items():
            if presence_point is None:
                continue
            feature = QgsFeature()
            point = QgsPointXY(presence_point.x, presence_point.y)
            geom = QgsGeometry.fromPointXY(point)
            if presence_point.srid != PRESENCE_LAYER_SRID:
                geom.transform(
                    QgsCoordinateTransform(
                        QgsCoordinateReferenceSystem(presence_point.srid),
                        QgsCoordinateReferenceSystem(PRESENCE_LAYER_SRID),
                        QgsProject.instance().transformContext(),
                    )
                )
            self._last_presence_point[client_id] = PresencePoint(
                x=geom.asPoint().x(),
                y=geom.asPoint().y(),
                srid=PRESENCE_LAYER_SRID,
                rotation=presence_point.rotation,
                time=presence_point.time,
            )
            feature.setGeometry(geom)
            rotation_deg = -1 * presence_point.rotation * 180 / 3.141592
            feature.setAttributes([rotation_deg])
            features.append(feature)

        provider.addFeatures(features)
        self.presence_layer.updateExtents()
        self.presence_layer.triggerRepaint()

        self.has_presence_point.emit(self.any_presence_point())
        self.center_view_if_active()

    def any_presence_point(self) -> bool:
        return bool(self._last_presence_point)

    def center_view_if_active(self) -> None:
        if not self.center_view_on_position_update:
            return
        if not bool(self._last_presence_point):
            return
        # max by time
        presence_point: PresencePoint = max(
            self._last_presence_point.values(), key=lambda x: x.time
        )
        geom = QgsGeometry.fromPointXY(QgsPointXY(presence_point.x, presence_point.y))

        # Transform point to map canvas CRS
        canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
        presence_point_crs = QgsCoordinateReferenceSystem(presence_point.srid)
        if presence_point_crs != canvas_crs:
            transform_context = QgsProject.instance().transformContext()
            geom.transform(
                QgsCoordinateTransform(
                    presence_point_crs, canvas_crs, transform_context
                )
            )

        iface.mapCanvas().setCenter(geom.asPoint())
        iface.mapCanvas().refresh()

    def send_jakartowns_move_request(
        self,
        lon: float,
        lat: float,
    ) -> None:
        if self._channel is None or not self.send_jakartowns_move_requests:
            return
        self._send_broadcast_queue.put(
            (
                "jakartowns_move_request",
                {"lon": lon, "lat": lat},
            )
        )

    def close(self) -> None:
        self._send_broadcast_queue.put(None)

        if self._presence_layer is not None:
            try:
                QgsProject.instance().removeMapLayer(self._presence_layer)
                iface.mapCanvas().refresh()
            except RuntimeError:
                pass
            self._presence_layer = None

    def __del__(self) -> None:
        self.close()


@dataclass
class PresencePoint:
    x: float
    y: float
    srid: int
    rotation: float
    time: float
