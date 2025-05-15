from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtGui import QDesktopServices
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsMapLayer,
    QgsProject,
)
from qgis.gui import QgisInterface
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QToolBar,
    QWidget,
)
from qgis.utils import iface

from .adapter import Adapter
from .auth import JakartoAuthentication
from .constants import jakartowns_url
from .converters import convert_geometry_type
from .layer import Layer
from .logs import notify
from .ui import utils
from .ui.browser_tree import BrowserTree
from .ui.create_sub_layer import CreateSubLayerDialog

iface: QgisInterface

HERE = Path(__file__).parent


class Plugin(QObject):
    menu: QMenu = None
    toolbar: QToolBar = None
    browser: BrowserTree = None

    start_realtime_signal = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._actions: list[QAction] = []
        self._signals: list = []

        self._adapter = None

        self._auth = JakartoAuthentication()
        self._realtime_thread = QThread()

    def initGui(self) -> None:  # noqa N802
        self.toolbar = iface.addToolBar("Jakarto Real-Time Layers")
        self.toolbar.setObjectName("Jakarto Real-Time Layers")
        self.menu = QMenu("Jakarto Real-Time Layers")
        self.menu.setIcon(utils.icon("jakartowns-sync-36.png"))

        self.browser = BrowserTree(self.get_all_layers)
        QgsApplication.instance().dataItemProviderRegistry().addProvider(
            self.browser.dip
        )

        self.connect_signal(self.browser.add_layer_signal, self.add_layer)
        self.connect_signal(self.browser.merge_sub_layer_signal, self.merge_sub_layer)
        self.connect_signal(self.browser.rename_layer_signal, self.rename_layer)
        self.connect_signal(self.browser.drop_layer_signal, self.drop_layer)

        # workaround for WebMenu
        temp_action = QAction()
        iface.addPluginToWebMenu("Jakarto Layers", temp_action)
        iface.webMenu().addMenu(self.menu)
        iface.removePluginWebMenu("Jakarto Layers", temp_action)

        self.connect_signal(QgsProject.instance().layersRemoved, self.on_layers_removed)
        self.connect_signal(iface.currentLayerChanged, self.on_current_layer_changed)

        self.add_action(
            utils.icon("jakartowns-sync-36.png"),
            text="Edit active layer in Jakartowns",
            callback=self.sync_layer_with_jakartowns,
            parent=iface.mainWindow(),
            object_name="sync_layer_with_jakartowns",
        )
        self.add_action(
            utils.icon("truck.png"),
            text="Pan Map View to follow Jakartowns positions",
            callback=self.set_jakartowns_follow,
            parent=iface.mainWindow(),
            checkable=True,
            enabled=False,
            object_name="jakartowns_follow",
        )
        self.add_action(
            utils.icon("layers-plus-alt.png"),
            text="Clone active layer as new Real-Time Layer",
            callback=self.import_layer,
            parent=iface.mainWindow(),
            object_name="import_layer",
        )
        self.add_action(
            utils.icon("shape-subtract.png"),
            text="Create new Real-Time Sub-Layer from selection",
            callback=self.create_sub_layer,
            parent=iface.mainWindow(),
            object_name="create_sub_layer",
        )
        self.on_current_layer_changed()

        self.remove_all_presence_layers()

        self.connect_signal(self.start_realtime_signal, self.adapter.start_realtime)

        if hasattr(iface, "projectRead"):
            # this is not available in tests
            self.connect_signal(iface.projectRead, self.remove_all_presence_layers)

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""

        if self.browser is not None and not sip.isdeleted(self.browser.dip):
            QgsApplication.instance().dataItemProviderRegistry().removeProvider(
                self.browser.dip
            )
            self.browser = None

        self.disconnect_signals()

        if self._adapter is not None:
            self.adapter.close()
            self._adapter = None
        for action in self._actions:
            if not sip.isdeleted(action):
                action.deleteLater()
        self._actions.clear()
        if self.menu is not None and not sip.isdeleted(self.menu):
            self.menu.deleteLater()
            self.menu = None
        if self.toolbar is not None and not sip.isdeleted(self.toolbar):
            iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar = None

    def connect_signal(self, signal, callback: Callable) -> None:
        signal.connect(callback)
        self._signals.append((signal, callback))

    def disconnect_signals(self) -> None:
        for signal, callback in self._signals:
            signal.disconnect(callback)
        self._signals.clear()

    @property
    def adapter(self) -> Adapter:
        if self._adapter is None:
            adapter = Adapter(auth=self._auth, realtime_thread=self._realtime_thread)
            self.get_action("jakartowns_follow").toggled.connect(
                adapter.set_jakartowns_follow
            )
            self.connect_signal(
                adapter.has_presence_point_signal, self.on_has_presence_point
            )
            self.on_current_layer_changed()
            self._adapter = adapter
        return self._adapter

    def connect_auth(self) -> bool:
        if not self._auth.setup_auth():
            return False

        # Don't call `self.adapter.start_realtime()` directly here because
        # when `connect_auth` is called from `QgsDataCollectionItem.createChildren`,
        # events silently fail. Probably because `createChildren` is not called
        # from the main thread...
        self.start_realtime_signal.emit()
        return True

    def on_has_presence_point(self, value: bool) -> None:
        self.get_action("jakartowns_follow").setEnabled(value)

    def set_jakartowns_follow(self) -> None:
        if self._adapter is None or not self.connect_auth():
            return
        self.adapter.set_jakartowns_follow(
            self.get_action("jakartowns_follow").isChecked()
        )

    def add_action(
        self,
        icon: QIcon,
        text: str,
        callback: Callable,
        *,
        add_to_menu: bool = True,
        add_to_toolbar: bool = True,
        status_tip: Optional[str] = None,
        whats_this: Optional[str] = None,
        parent: Optional[QWidget] = None,
        enabled: bool = True,
        checkable: bool = False,
        object_name: Optional[str] = None,
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

        action = QAction(icon, text, parent)
        action.triggered.connect(lambda _: callback())
        action.setEnabled(enabled)
        if checkable:
            action.setCheckable(True)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_menu and self.menu is not None:
            self.menu.addAction(action)

        if add_to_toolbar and self.toolbar is not None:
            self.toolbar.addAction(action)

        if object_name is not None:
            action.setObjectName(object_name)

        self._actions.append(action)

        return action

    def get_action(self, object_name: str) -> QAction:
        for action in self._actions:
            if action.objectName() == object_name:
                return action
        raise ValueError(f"Action with object name {object_name} not found")

    def is_layer_syncable(self, qgis_layer: QgsMapLayer) -> bool:
        return (
            qgis_layer is not None
            and hasattr(qgis_layer, "geometryType")
            and convert_geometry_type(qgis_layer.geometryType()) == "point"
        )

    def is_real_time_layer(self, qgis_layer: QgsMapLayer) -> bool:
        return self._layer_has_property(qgis_layer, "supabase_layer_id")

    def is_presence_layer(self, qgis_layer: QgsMapLayer) -> bool:
        return self._layer_has_property(qgis_layer, "jakarto_positions_presence_layer")

    def _layer_has_property(self, layer: QgsMapLayer, property_name: str) -> bool:
        return (
            layer is not None and layer.customProperty(property_name, None) is not None
        )

    def on_current_layer_changed(self, layer: Optional[QgsMapLayer] = None) -> None:
        if layer is None:
            layer = iface.activeLayer()

        is_syncable = self.is_layer_syncable(layer)
        is_real_time_layer = self.is_real_time_layer(layer)
        is_presence_layer = self.is_presence_layer(layer)

        sync_layer_action = self.get_action("sync_layer_with_jakartowns")
        sync_layer_action.setEnabled(is_syncable and not is_presence_layer)

        import_layer_action = self.get_action("import_layer")
        import_layer_action.setEnabled(
            is_syncable and not is_real_time_layer and not is_presence_layer
        )

        create_sub_layer_action = self.get_action("create_sub_layer")
        create_sub_layer_action.setEnabled(is_real_time_layer and not is_presence_layer)

        jakartowns_follow_action = self.get_action("jakartowns_follow")
        if not self._actions or not self._adapter:
            jakartowns_follow_action.setEnabled(False)
            return
        jakartowns_follow_action.setEnabled(self.adapter.any_presence_point())

    def sync_layer_with_jakartowns(self) -> None:
        if not self.connect_auth():
            return
        qgis_layer = iface.activeLayer()
        if not self.is_layer_syncable(qgis_layer) or self.is_presence_layer(qgis_layer):
            return

        if self.adapter.unsync_layer_with_jakartowns(qgis_layer):
            notify(f"Jakartowns sync deactivated for layer '{qgis_layer.name()}'")
            return  # layer was already synced with jakartowns, we just unsynced it

        if self.is_real_time_layer(qgis_layer):
            layer = self.adapter.get_layer(
                qgis_layer.customProperty("supabase_layer_id")
            )
            if layer is None:
                return
        else:
            layer = self.adapter.sync_layer_with_jakartowns(qgis_layer)

        def _get_center_4326() -> tuple[float, float]:
            center: QgsGeometry = QgsGeometry.fromPointXY(
                iface.mapCanvas().extent().center()
            )
            canvas_crs = iface.mapCanvas().mapSettings().destinationCrs()
            center.transform(
                QgsCoordinateTransform(
                    canvas_crs,
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance().transformContext(),
                )
            )
            pt = center.asPoint()
            return pt.x(), pt.y()

        lng, lat = _get_center_4326()
        url = f"{jakartowns_url}/?real_time_layer={layer.supabase_layer_id}&lat={lat}&lng={lng}"
        QDesktopServices.openUrl(QUrl(url))

        layer.set_layer_tree_icon(True)

    def remove_all_presence_layers(self) -> None:
        to_remove = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.customProperty("jakarto_positions_presence_layer", None) == "1":
                to_remove.append(layer.id())
        if to_remove:
            QgsProject.instance().removeMapLayers(to_remove)
            iface.mapCanvas().refresh()

    def get_all_layers(self, fetch_layers: bool = False) -> list[Layer]:
        if not self.connect_auth():
            return []
        if self._adapter is None or fetch_layers:
            # first time loading layers or force fetching layers
            self.adapter.fetch_layers()

        return self.adapter.get_all_layers()

    def reload_layers(self, fetch_layers: bool = True) -> None:
        if not self.connect_auth():
            return
        if fetch_layers:
            self.adapter.fetch_layers()

        self.browser.refresh_layers_signal.emit()

    def on_layers_removed(self, removed_ids: list[str]) -> None:
        if self._adapter and self.adapter.on_layers_removed(removed_ids):
            try:
                iface.mapCanvas().refresh()
            except RuntimeError:
                pass  # object could be deleted here in tests

    def add_layer(self, supabase_id: str) -> None:
        if not self.connect_auth():
            return

        def _sub_callback(success: bool) -> None:
            if not success:
                return
            iface.mapCanvas().refresh()
            layer = self.adapter.get_layer(supabase_id)
            if layer is None:
                return
            iface.setActiveLayer(layer.qgis_layer)
            layer.set_layer_tree_icon(True)

        self.adapter.add_layer(supabase_id, _sub_callback)

    def create_sub_layer(self) -> None:
        if not self.connect_auth():
            return
        qgis_layer = iface.activeLayer()
        if qgis_layer is None:
            return
        if not self.is_real_time_layer(qgis_layer):
            return

        layer = self.adapter.get_layer(qgis_layer.customProperty("supabase_layer_id"))
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
            iface.mapCanvas().refresh()

    def merge_sub_layer(self, supabase_id: str) -> None:
        if not self.connect_auth():
            return
        self.adapter.merge_sub_layer(supabase_id)
        self.adapter.remove_layer(supabase_id)
        self.reload_layers(fetch_layers=False)
        iface.mapCanvas().refresh()

    def drop_layer(self, supabase_id: str) -> None:
        if not self.connect_auth():
            return
        self.adapter.remove_layer(supabase_id)
        self.adapter.drop_layer(supabase_id)
        self.reload_layers(fetch_layers=False)
        iface.mapCanvas().refresh()

    def import_layer(self) -> None:
        if not self.connect_auth():
            return
        qgis_layer = iface.activeLayer()
        if not self.is_layer_syncable(qgis_layer):
            return

        try:
            layer, _ = self.adapter.import_layer(qgis_layer)
        except ValueError as e:
            notify(str(e), level="critical")
            return

        self.reload_layers(fetch_layers=False)
        self.browser.select_layer(layer.supabase_layer_id)

    def rename_layer(self, supabase_id: str) -> None:
        if not self.connect_auth():
            return
        layer = self.adapter.get_layer(supabase_id)
        if layer is None:
            return

        new_name, ok = QInputDialog.getText(
            iface.mainWindow(),
            "Rename Layer",
            f"Enter new layer name for layer '{layer.name}'",
            text=layer.name,
        )
        if ok and new_name and new_name != layer.name:
            self.adapter.rename_layer(supabase_id, new_name)
            self.reload_layers(fetch_layers=False)
            iface.mapCanvas().refresh()
