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
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

from .utils import icon

if TYPE_CHECKING:
    from ..layer import Layer


class BrowserTree(QObject):
    refresh_layers_signal = pyqtSignal()
    add_layer_signal = pyqtSignal(str)
    merge_sub_layer_signal = pyqtSignal(str)
    rename_layer_signal = pyqtSignal(str)
    drop_layer_signal = pyqtSignal(str)

    def __init__(self, get_layers_func: Callable[[bool], list[Layer]]):
        super().__init__()
        self._get_layers_func = get_layers_func

        self.dip = _DataItemProvider(self)
        self.root = _RootCollection(self)
        self.real_time_layers_collection = _RealTimeLayersCollection(self)

        self.refresh_layers_signal.connect(self.refresh_layers)

        self._layers: list[Layer] = []

    def get_layers(self, fetch_layers: bool = False) -> list[Layer]:
        self._layers = self._get_layers_func(fetch_layers)
        return self._layers

    def add_layer(self, supabase_layer_id: str):
        self.add_layer_signal.emit(supabase_layer_id)

    def merge_sub_layer(self, supabase_layer_id: str):
        self.merge_sub_layer_signal.emit(supabase_layer_id)

    def rename_layer(self, supabase_layer_id: str):
        self.rename_layer_signal.emit(supabase_layer_id)

    def drop_layer(self, supabase_layer_id: str):
        self.drop_layer_signal.emit(supabase_layer_id)

    def refresh_layers(self):
        self.real_time_layers_collection.depopulate()
        self.real_time_layers_collection.refresh()

    def select_layer(self, supabase_layer_id: str):
        found_layer = None
        for layer in self.real_time_layers_collection.children():
            if layer.layer.supabase_layer_id == supabase_layer_id:
                found_layer = layer
                break
        if not found_layer:
            return

        self.real_time_layers_collection.setCurrentItem(found_layer)


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

        self._initial_fetch_done = False

    def createChildren(self):
        fetch_layers = not self._initial_fetch_done
        layers = self.browser.get_layers(fetch_layers)
        self._initial_fetch_done = True

        return [_RealTimeLayerItem(self, layer, self.browser) for layer in layers]


class _RealTimeLayerItem(QgsDataItem):
    def __init__(
        self,
        parent: _RealTimeLayersCollection,
        layer: Layer,
        browser: BrowserTree,
    ):
        QgsDataItem.__init__(
            self,
            QgsDataItem.Custom,
            parent,
            layer.name,
            "/Jakarto/real-time-layer/" + layer.supabase_layer_id,
        )
        self.layers_collection = parent
        self.layer = layer
        self.browser = browser

        self.setIcon(icon("layer-points.svg"))
        self.populate()

    def add_layer_action(self):
        self.browser.add_layer(self.layer.supabase_layer_id)

    def merge_sub_layer_action(self):
        self.browser.merge_sub_layer(self.layer.supabase_layer_id)

    def rename_layer_action(self):
        self.browser.rename_layer(self.layer.supabase_layer_id)

    def drop_layer_action(self):
        self.browser.drop_layer(self.layer.supabase_layer_id)

    def handleDoubleClick(self):
        self.browser.add_layer(self.layer.supabase_layer_id)
        return True

    def actions(self, parent):
        actions = []

        add_layer = QAction(QIcon(), "Add Layer", parent)
        add_layer.triggered.connect(self.add_layer_action)
        actions.append(add_layer)

        merge_sub_layer = QAction(QIcon(), "Merge Sub Layer", parent)
        merge_sub_layer.triggered.connect(self.merge_sub_layer_action)
        is_sub_layer = self.layer.supabase_parent_layer_id is not None
        merge_sub_layer.setVisible(is_sub_layer)

        drop_layer = QAction(QIcon(), "Drop Layer", parent)
        drop_layer.triggered.connect(self.drop_layer_action)

        rename_layer = QAction(QIcon(), "Rename Layer", parent)
        rename_layer.triggered.connect(self.rename_layer_action)

        manage_menu = QMenu("Manage Layer", parent)

        manage_menu.addAction(merge_sub_layer)
        manage_menu.addAction(rename_layer)

        separator = QAction(QIcon(), "", parent)
        separator.setSeparator(True)
        manage_menu.addAction(separator)

        manage_menu.addAction(drop_layer)

        manage_layer = QAction(QIcon(), "Manage Layer", parent)
        manage_layer.setMenu(manage_menu)

        actions.append(manage_layer)

        return actions
