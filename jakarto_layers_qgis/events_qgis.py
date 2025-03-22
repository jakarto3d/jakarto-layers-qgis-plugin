from dataclasses import dataclass

from qgis.core import QgsFeature


@dataclass
class QGISInsertEvent:
    features: list[QgsFeature]


@dataclass
class QGISUpdateEvent:
    ids: list[int]


@dataclass
class QGISDeleteEvent:
    ids: list[int]
