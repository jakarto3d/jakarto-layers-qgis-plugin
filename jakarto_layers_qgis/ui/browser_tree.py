from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

import sip
from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import (
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsDataProvider,
)

from .utils import icon

if TYPE_CHECKING:
    from ..layer import Layer


class BrowserTree(QObject):
    refresh_layers_signal = pyqtSignal()

    def __init__(self, get_layers_func: Callable[[], list[Layer]]):
        super().__init__()
        self.get_layers_func = get_layers_func

        self.dip = _DataItemProvider(self)
        self.root = _RootCollection(self)
        self.real_time_layers_collection = _RealTimeLayersCollection(self)

        self.refresh_layers_signal.connect(self.refresh_layers)

    def refresh_layers(self):
        self.real_time_layers_collection.depopulate()
        self.real_time_layers_collection.refresh()


class _DataItemProvider(QgsDataItemProvider):
    def __init__(self, browser: BrowserTree):
        super().__init__()
        self.browser = browser

    def name(self):
        return "JakartoProvider"

    def capabilities(self):
        return QgsDataProvider.Net

    def createDataItem(
        self, path: Optional[str] = None, parentItem: Optional[QgsDataItem] = None
    ):
        sip.transferto(self.browser.root, None)
        return self.browser.root


class _RootCollection(QgsDataCollectionItem):
    def __init__(self, browser: BrowserTree):
        super().__init__(None, "Jakarto", "/Jakarto/root")
        self.setIcon(icon("jakartowns.png"))
        self.browser = browser

    def createChildren(self):
        return [self.browser.real_time_layers_collection]

    def actions(self, parent):
        return []


class _RealTimeLayersCollection(QgsDataCollectionItem):
    def __init__(self, browser: BrowserTree):
        QgsDataCollectionItem.__init__(
            self, browser.root, "Real-Time Layers", "/Jakarto/real-time-layers"
        )
        self.setIcon(icon("jakartowns-sync-36.png"))
        self.browser = browser

    def createChildren(self):
        layers = self.browser.get_layers_func()

        return [_RealTimeLayerItem(self, layer.name) for layer in layers]


class _RealTimeLayerItem(QgsDataItem):
    def __init__(self, parent, name: str):
        QgsDataItem.__init__(
            self,
            QgsDataItem.Custom,
            parent,
            name,
            "/Jakarto/real-time-layer/" + name,
        )
        self.setIcon(icon("layer-points.svg"))
        self.populate()
