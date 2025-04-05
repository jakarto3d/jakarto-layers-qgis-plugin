from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from qgis.core import Qgis, QgsProject
from qgis.gui import QgisInterface, QgsLayerTreeViewIndicator
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
    QWidget,
)
from qgis.utils import iface

from .adapter import Adapter
from .ui.create_sub_layer import CreateSubLayerDialog
from .ui.main_panel import MainPanel

iface: QgisInterface

HERE = Path(__file__).parent


class Plugin:
    """QGIS Plugin Implementation."""

    name = "jakarto_layers_qgis"

    def __init__(self) -> None:
        self.actions: list[QAction] = []
        self.menu = Plugin.name
        self.toolbar = None
        self._panel = None

        self._adapter = None

    @property
    def panel(self) -> MainPanel:
        if self._panel is None:
            raise RuntimeError("Panel is not loaded")
        return self._panel

    @property
    def adapter(self) -> Adapter:
        if self._adapter is None:
            self._adapter = Adapter()
        return self._adapter

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

        self.panel.layerTree.itemSelectionChanged.connect(
            self.on_item_selection_changed
        )
        self.panel.layerTree.itemDoubleClicked.connect(self.add_layer)
        self.panel.layerTree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.panel.layerTree.customContextMenuRequested.connect(
            self.show_layer_context_menu
        )
        self.panel.layerAdd.clicked.connect(self.add_layer)
        self.panel.layerRemove.clicked.connect(self.remove_layer)
        self.panel.layerImport.clicked.connect(self.import_layer)

        QgsProject.instance().layersRemoved.connect(self.on_layers_removed)

        action = self.add_action(
            ":/resources/icons/layer-solid-36.png",
            text="Jakarto Layers",
            callback=self.run,
            parent=iface.mainWindow(),
        )
        self.toolbar.addAction(action)

    def show_layer_context_menu(self, position):
        item = self.panel.layerTree.itemAt(position)
        if item is None:
            return

        layer = self.adapter.get_layer(self.get_selected_layer(item))
        if not layer:
            return
        is_sub_layer = layer.supabase_parent_layer_id is not None

        menu = QMenu()
        add_action = menu.addAction("Load Layer")
        add_action.setToolTip("Load layer on the current map")
        add_action.setEnabled(self.panel.layerAdd.isEnabled())
        remove_action = menu.addAction("Remove Layer")
        remove_action.setToolTip("Remove layer from the map")
        remove_action.setEnabled(self.panel.layerRemove.isEnabled())
        menu.addSeparator()
        merge_sub_layer_action = menu.addAction("Merge Sub Layer")
        merge_sub_layer_action.setToolTip(
            "Merge the selected sub layer into its parent layer"
        )
        merge_sub_layer_action.setVisible(is_sub_layer)
        sub_layer_action = menu.addAction("New Sub Layer from selection")
        sub_layer_action.setToolTip("Create a new sub layer from the selection")
        sub_layer_action.setEnabled(self.panel.layerRemove.isEnabled())
        sub_layer_action.setVisible(not is_sub_layer)
        menu.addSeparator()
        rename_action = menu.addAction("Rename Layer")
        rename_action.setToolTip("Rename the selected layer")
        menu.addSeparator()
        drop_action = menu.addAction("Drop Layer")
        drop_action.setToolTip("Drop layer from the database (cannot be undone)")

        action = menu.exec_(self.panel.layerTree.mapToGlobal(position))

        if action == add_action:
            self.add_layer(item)
        elif action == remove_action:
            self.remove_layer()
        elif action == merge_sub_layer_action:
            self.merge_sub_layer(item)
        elif action == sub_layer_action:
            self.create_sub_layer(item)
        elif action == rename_action:
            self.rename_layer(item)
        elif action == drop_action:
            self.drop_layer(item)

    def onClosePlugin(self) -> None:  # noqa N802
        """Cleanup necessary items here when plugin dockwidget is closed"""

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""
        if self._adapter is not None:
            self.adapter.close()
        if self._panel is not None:
            self._panel.close()
            self._panel = None

        if self.toolbar:
            iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar = None

        for action in self.actions:
            iface.removePluginMenu(Plugin.name, action)

    def run(self) -> None:
        iface.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.panel)

        self.reload_layers()
        self.adapter.start_realtime()

    def reload_layers(self, fetch_layers: bool = True) -> None:
        if fetch_layers:
            self.adapter.fetch_layers()

        self.panel.layerTree.clear()
        for (
            name,
            type_,
            srid,
            supabase_layer_id,
            children,
        ) in self.adapter.all_layer_properties():
            item = QTreeWidgetItem()
            item.setText(0, name)
            if children:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            item.setText(1, type_)
            item.setText(2, str(srid))
            # Store the layer ID in the item's data
            item.setData(0, Qt.ItemDataRole.UserRole, supabase_layer_id)
            for child_name, child_type, child_srid, child_id, _ in children:
                child_item = QTreeWidgetItem()
                child_item.setText(0, child_name)
                child_item.setText(1, child_type)
                child_item.setText(2, str(child_srid))
                # Store the child layer ID in the item's data
                child_item.setData(0, Qt.ItemDataRole.UserRole, child_id)
                item.addChild(child_item)

            self.panel.layerTree.addTopLevelItem(item)
        self.panel.layerTree.resizeColumnToContents(0)
        self.panel.layerTree.resizeColumnToContents(1)
        self.panel.layerTree.resizeColumnToContents(2)

        self.panel.layerTree.expandAll()

    def get_selected_layer(self, value: Any = None) -> str | None:
        if value is not None and hasattr(value, "data"):
            try:
                return value.data(0, Qt.ItemDataRole.UserRole)
            except TypeError:
                return value.data(0, Qt.ItemDataRole.UserRole)
        elif value in self.adapter._all_layers:
            return value
        current = self.panel.layerTree.currentItem()
        return current.data(0, Qt.ItemDataRole.UserRole) if current else None

    def on_item_selection_changed(self) -> None:
        add_enabled, remove_enabled = True, True
        if supabase_id := self.get_selected_layer():
            loaded = self.adapter.is_loaded(supabase_id)
            add_enabled = not loaded
            remove_enabled = loaded

        self.panel.layerAdd.setEnabled(add_enabled)
        self.panel.layerRemove.setEnabled(remove_enabled)

    def on_layers_removed(self, removed_ids: list[str]) -> None:
        if self.adapter.on_layers_removed(removed_ids):
            self.on_item_selection_changed()
            try:
                iface.mapCanvas().refresh()
            except RuntimeError:
                pass  # object could be deleted here in tests

    def add_layer(self, value) -> None:
        supabase_id = self.get_selected_layer(value)
        if supabase_id is None:
            return

        def _sub_callback(success: bool) -> None:
            if not success:
                return
            self.on_item_selection_changed()
            iface.mapCanvas().refresh()
            layer = self.adapter.get_layer(supabase_id)
            if layer is None:
                return
            iface.setActiveLayer(layer.qgis_layer)
            tree_root = QgsProject.instance().layerTreeRoot()
            layer_node = tree_root.findLayer(layer.qgis_layer.id())
            if layer_node is not None:
                icons_folder = HERE / "ui" / "icons"
                icon = QIcon(str(icons_folder / "cloud-lightning-regular-36.png"))
                ind = QgsLayerTreeViewIndicator(layer_node)
                ind.setIcon(icon)
                is_sub = layer.supabase_parent_layer_id is not None
                name = "Layer" if not is_sub else "Sub-Layer"
                ind.setToolTip(f"Jakarto Real-time {name}")

                # remove all indicators, add the new one
                if hasattr(iface, "layerTreeView"):  # no iface.layerTreeView in tests
                    tree_view = iface.layerTreeView()
                    for indicator in tree_view.indicators(layer_node):
                        tree_view.removeIndicator(layer_node, indicator)
                    tree_view.addIndicator(layer_node, ind)

        self.adapter.add_layer(supabase_id, _sub_callback)

    def remove_layer(self) -> None:
        if self.adapter.remove_layer(self.get_selected_layer()):
            self.on_item_selection_changed()
            iface.mapCanvas().refresh()

    def create_sub_layer(self, value) -> None:
        supabase_id = self.get_selected_layer(value)
        if supabase_id is None:
            return
        layer = self.adapter.get_layer(supabase_id)
        if layer is None or layer.qgis_layer is None:
            return

        if layer.supabase_parent_layer_id is not None:
            QMessageBox.warning(
                iface.mainWindow(),
                "Already a sub-layer",
                "This layer is already a sub-layer, "
                "you cannot create a sub-layer from it.",
            )
            return

        # Check for selected features before showing dialog
        selected_count = layer.qgis_layer.selectedFeatureCount()
        if selected_count == 0:
            QMessageBox.warning(
                iface.mainWindow(),
                "No Features Selected",
                "Please select features from the loaded layer to create a sub-layer.",
            )
            return

        dialog = CreateSubLayerDialog(parent=iface.mainWindow(), layer=layer)

        accepted = QDialog.DialogCode.Accepted
        if dialog.exec_() == accepted and dialog.properties:
            self.adapter.create_sub_layer(layer, dialog.properties.name)
            self.reload_layers(fetch_layers=False)
            self.on_item_selection_changed()
            iface.mapCanvas().refresh()

    def merge_sub_layer(self, value) -> None:
        supabase_id = self.get_selected_layer(value)
        if supabase_id is None:
            return
        self.adapter.merge_sub_layer(supabase_id)
        self.adapter.remove_layer(supabase_id)
        self.reload_layers(fetch_layers=False)
        self.on_item_selection_changed()
        iface.mapCanvas().refresh()

    def drop_layer(self, value) -> None:
        supabase_id = self.get_selected_layer(value)
        if supabase_id is None:
            return
        self.adapter.remove_layer(supabase_id)
        self.adapter.drop_layer(supabase_id)
        self.reload_layers(fetch_layers=False)
        self.on_item_selection_changed()
        iface.mapCanvas().refresh()

    def import_layer(self) -> None:
        layer = iface.activeLayer()
        if layer is None:
            return
        if not hasattr(layer, "geometryType"):
            return
        if layer.geometryType() != Qgis.GeometryType.Point:
            return

        try:
            self.adapter.import_layer(layer)
        except ValueError as e:
            iface.messageBar().pushMessage(
                "Jakarto layers",
                str(e),
                level=Qgis.MessageLevel.Critical,
                duration=5,
            )
            return

        self.reload_layers(fetch_layers=False)

    def rename_layer(self, value) -> None:
        supabase_id = self.get_selected_layer(value)
        if supabase_id is None:
            return
        layer = self.adapter.get_layer(supabase_id)
        if layer is None:
            return

        new_name, ok = QInputDialog.getText(
            iface.mainWindow(),
            f"Rename Layer '{layer.name}'",
            "Enter new layer name:",
            text=layer.name,
        )
        if ok and new_name and new_name != layer.name:
            self.adapter.rename_layer(supabase_id, new_name)
            self.reload_layers(fetch_layers=False)
            self.on_item_selection_changed()
            iface.mapCanvas().refresh()
