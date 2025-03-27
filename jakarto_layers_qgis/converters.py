from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QVariant

from .constants import geometry_types, qmetatype_to_python
from .supabase_models import LayerAttribute, SupabaseFeature, SupabaseLayer

if TYPE_CHECKING:
    # to avoid circular imports
    from .layer import Layer


def qgis_to_supabase_feature(
    feature: QgsFeature,
    supabase_layer_id: str,
    supabase_feature_id: str | None = None,
    *,
    feature_type: str | None = None,
    attribute_names: list[str] | None = None,
) -> SupabaseFeature:
    if attribute_names is None:
        attribute_names = list(feature.attributeMap().keys())

    attributes = {}
    null = QVariant()
    for name, value in zip(attribute_names, feature.attributes()):
        if isinstance(value, (int, str, float, bool)):
            pass
        elif null == value:
            value = None
        elif isinstance(value, QDate):
            value = value.toPyDate()
        elif isinstance(value, QDateTime):
            value = value.toPyDateTime()
        else:
            raise ValueError(f"Unknown value type: '{value!r}'")
        attributes[name] = value

    geometry = feature.geometry()
    if feature_type is None:
        feature_type = geometry.type().name.lower()  # type: ignore
    else:
        feature_type = feature_type.lower()
    if feature_type != "point":
        raise NotImplementedError(f"Geometry type {feature_type} not implemented")

    point = geometry.vertexAt(0)
    geom = {
        "type": geometry_types[feature_type],
        "coordinates": [point.x(), point.y(), point.z() if point.is3D() else None],
    }
    geom = geom_force3d(geom)

    return SupabaseFeature(
        id=supabase_feature_id or str(uuid.uuid4()),
        layer_id=supabase_layer_id,
        attributes=attributes,
        geom=geom,
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
