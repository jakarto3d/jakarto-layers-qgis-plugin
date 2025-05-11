from typing import Optional

import sip
from qgis.core import (
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsDataProvider,
)

from .utils import icon


class DataItemProvider(QgsDataItemProvider):
    def __init__(self):
        super().__init__()

    def name(self):
        return "JakartoProvider"

    def capabilities(self):
        return QgsDataProvider.Net

    def createDataItem(
        self, path: Optional[str] = None, parentItem: Optional[QgsDataItem] = None
    ):
        root = RootCollection()
        sip.transferto(root, None)
        return root


class LayerItem(QgsDataCollectionItem):
    def __init__(self, parent):
        QgsDataCollectionItem.__init__(
            self, parent, "Jakarto Layers", "/Jakarto/layers"
        )
        self.setIcon(icon("jakartowns.png"))

    def createChildren(self):
        return []


class RootCollection(QgsDataCollectionItem):
    def __init__(self):
        super().__init__(None, "Jakarto", "/Jakarto/root")
        self.setIcon(icon("jakartowns.png"))

    def createChildren(self):
        return [LayerItem(self)]

    def actions(self, parent):
        return []
