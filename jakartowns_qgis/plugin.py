from __future__ import annotations

from pathlib import Path
from typing import Callable

from qgis.core import QgsDataSourceUri, QgsProject, QgsVectorLayer
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QListWidgetItem, QWidget
from qgis.utils import iface

from .layers import LayerContainer
from .ui.main_panel import MainPanel

iface: QgisInterface

HERE = Path(__file__).parent


class Plugin:
    """QGIS Plugin Implementation."""

    name = "jakartowns_qgis"

    def __init__(self) -> None:
        self.actions: list[QAction] = []
        self.menu = Plugin.name
        self.toolbar = None
        self._panel = None
        self._layer_container = LayerContainer()

    @property
    def panel(self) -> MainPanel:
        if self._panel is None:
            raise RuntimeError("Panel is not loaded")
        return self._panel

    def add_action(
        self,
        icon_path: str | Path,
        text: str,
        callback: Callable,
        *,
        enabled_flag: bool = True,
        add_to_menu: bool = True,
        status_tip: str | None = None,
        whats_this: str | None = None,
        parent: QWidget | None = None,
    ) -> QAction:
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.

        :param text: Text that should be shown in menu items for this action.

        :param callback: Function to be called when the action is triggered.

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.

        :param parent: Parent widget for the new action. Defaults None.

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(str(icon_path))
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_menu:
            iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self) -> None:  # noqa N802
        self._panel = MainPanel()
        self.toolbar = iface.addToolBar("Jakarto Layers")
        self.toolbar.setObjectName("JakartoLayers")

        self.panel.layerList.itemSelectionChanged.connect(
            self.on_item_selection_changed
        )
        self.panel.layerList.itemDoubleClicked.connect(self.add_layer)
        self.panel.layerAdd.clicked.connect(self.add_layer)
        self.panel.layerRemove.clicked.connect(self.remove_layer)
        action = self.add_action(
            ":/resources/icons/layer-solid-36.png",
            text=Plugin.name,
            callback=self.run,
            parent=iface.mainWindow(),
        )
        self.toolbar.addAction(action)

    def onClosePlugin(self) -> None:  # noqa N802
        """Cleanup necessary items here when plugin dockwidget is closed"""

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""
        if self._panel:
            self._panel.close()
            self._panel = None

        if self.toolbar:
            iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar = None

        for action in self.actions:
            iface.removePluginMenu(Plugin.name, action)

        self._layer_container.remove_all_layers()

    def run(self) -> None:
        iface.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.panel)

        layers = self._layer_container.load_layers()

        self.panel.layerList.clear()
        self.panel.layerList.addItems(layers)

    def get_selected_layer(self, value=None) -> str | None:
        if value is not None and hasattr(value, "text"):
            return value.text()
        current = self.panel.layerList.currentItem()
        return current.text() if current else None

    def on_item_selection_changed(self) -> None:
        add_enabled, remove_enabled = True, True
        if layer_name := self.get_selected_layer():
            add_enabled = layer_name not in self._layer_container.layers
            remove_enabled = layer_name in self._layer_container.layers

        self.panel.layerAdd.setEnabled(add_enabled)
        self.panel.layerRemove.setEnabled(remove_enabled)

    def add_layer(self, value) -> None:
        self._layer_container.add_layer(self.get_selected_layer(value))
        self.on_item_selection_changed()

    def remove_layer(self) -> None:
        self._layer_container.remove_layer(self.get_selected_layer())
        self.on_item_selection_changed()
