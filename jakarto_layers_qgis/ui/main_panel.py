from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QPushButton,
    QStyledItemDelegate,
    QTreeWidget,
)

HERE = Path(__file__).parent
FORM_CLASS, _ = uic.loadUiType(
    str(HERE / "main_panel.ui"),
    from_imports=True,
    resource_suffix="_rc",
    import_from="jakarto_layers_qgis.ui",
)


class MainPanel(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.layerTree: QTreeWidget
        self.layerAdd: QPushButton
        self.layerRemove: QPushButton
        self.layerImport: QPushButton
        self.jakartownsFollow: QPushButton

        self.layerTree.setItemDelegate(MinHeightDelegate(24))


class MinHeightDelegate(QStyledItemDelegate):
    def __init__(self, min_height, parent=None):
        super().__init__(parent)
        self._min_height = min_height

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), self._min_height))
