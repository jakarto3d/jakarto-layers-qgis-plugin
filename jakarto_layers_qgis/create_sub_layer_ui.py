from dataclasses import dataclass
from typing import Optional

from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsVectorLayer
from qgis.PyQt.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .layer import Layer


@dataclass
class SubLayerProperties:
    """Properties for creating a new sub-layer."""

    name: str


class CreateSubLayerDialog(QDialog):
    """Dialog for creating a new sub-layer from selected features."""

    def __init__(
        self,
        layer: Layer,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.layer = layer
        self.properties: Optional[SubLayerProperties] = None
        self.setup_ui()

    def setup_ui(self) -> None:
        """Set up the UI components."""
        self.setWindowTitle("Create Sub Layer")
        layout = QVBoxLayout()

        # Show selected features count
        selected_count = self.layer.qgis_layer.selectedFeatureCount()
        total_count = self.layer.qgis_layer.featureCount()
        count_label = QLabel(f"Selected features: {selected_count} / {total_count}")
        layout.addWidget(count_label)

        # New layer name input
        name_label = QLabel("New Layer Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter new layer name")
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)

        # Buttons
        button_layout = QVBoxLayout()
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(create_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def accept(self) -> None:
        """Handle dialog acceptance."""
        new_name = self.name_input.text().strip()
        if not new_name:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Please enter a valid layer name.",
            )
            return

        self.properties = SubLayerProperties(name=new_name)
        super().accept()
