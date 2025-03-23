from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsPoint, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from .constants import qmetatype_to_python
from .supabase_models import LayerAttribute, SupabaseFeature, SupabaseLayer

if TYPE_CHECKING:
    # to avoid circular imports
    from .layer import Layer


def qgis_to_supabase_feature(
    feature: QgsFeature, supabase_layer_id: str, supabase_feature_id: str | None = None
) -> SupabaseFeature:
    attributes = {}
    for key, value in feature.attributeMap().items():
        if QVariant() == value:
            value = None
        elif isinstance(value, (int, str, float, bool)):
            pass
        elif to_py := [f for f in dir(value) if f.startswith("toPy")]:
            value = getattr(value, to_py[0])()
        else:
            raise ValueError(f"Unknown value type: {type(value)}")
        attributes[key] = value

    return SupabaseFeature(
        id=supabase_feature_id or str(uuid.uuid4()),
        layer=supabase_layer_id,
        attributes=attributes,
        geom=geom_force3d(json.loads(feature.geometry().asJson())),
    )


def supabase_to_qgis_feature(feature: SupabaseFeature, layer: Layer) -> QgsFeature:
    attrs_names = [a.name for a in layer.attributes]
    if layer.geometry_type == "point":
        x, y, z = feature.geom["coordinates"]
        qgis_feature = QgsFeature()
        qgis_feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(x, y, z)))
        qgis_feature.setAttributes(
            [feature.attributes.get(name) for name in attrs_names]
        )
    else:
        raise NotImplementedError(
            f"Geometry type {layer.geometry_type} not implemented"
        )
    return qgis_feature


def geom_force3d(geom: dict[str, Any]) -> dict[str, Any]:
    def _recurse(coords: list[Any]) -> None:
        if not isinstance(coords, list) or not coords:
            return
        if isinstance(coords[0], list):
            for coord in coords:
                _recurse(coord)
        elif len(coords) == 2:
            coords.append(0)
        elif len(coords) == 3:
            return
        else:
            raise ValueError(f"Invalid geometry type: {type(coords)}")

    _recurse(geom["coordinates"])
    return geom


def qgis_layer_to_postgrest_layer(
    layer: QgsVectorLayer,
    supabase_layer_id: str | None = None,
) -> SupabaseLayer:
    if layer.geometryType() != Qgis.GeometryType.Point:
        raise ValueError("Only point layers are supported")

    if supabase_layer_id is None:
        supabase_layer_id = str(uuid.uuid4())

    return SupabaseLayer(
        id=supabase_layer_id,
        name=layer.name(),
        geometry_type="point",
        attributes=[
            LayerAttribute(name=a.name(), type=qmetatype_to_python[a.type()])
            for a in layer.fields()
        ],
    )
