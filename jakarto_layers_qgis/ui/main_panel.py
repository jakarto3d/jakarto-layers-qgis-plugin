from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDockWidget, QListWidget, QPushButton

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
        self.layerList: QListWidget
        self.layerAdd: QPushButton
        self.layerRemove: QPushButton
        self.layerImport: QPushButton
