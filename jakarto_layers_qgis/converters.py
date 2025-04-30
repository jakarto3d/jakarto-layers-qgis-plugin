from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Optional

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
    *,
    supabase_layer_id: str,
    supabase_feature_id: Optional[str] = None,
    feature_type: Optional[str] = None,
    attribute_names: list[str],
) -> SupabaseFeature:
    attributes = {n: v for n, v in zip(attribute_names, feature.attributes())}

    null = QVariant()
    for name, value in attributes.items():
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


def str_convert(value: Optional[str], python_type: str) -> Any:
    if value in (None, "None"):
        return None
    try:
        if python_type == "bool":
            return value.lower() in ["true", "1", "yes", "y"]
        elif python_type == "int":
            return int(value)
        elif python_type == "float":
            return float(value)
        elif python_type == "str":
            return str(value)
        elif python_type == "date":
            date.fromisoformat(value)  # typecheck and return the string
        elif python_type == "time":
            time.fromisoformat(value)  # typecheck and return the string
        elif python_type == "datetime":
            datetime.fromisoformat(value)  # typecheck and return the string
        return value
    except (ValueError, TypeError):
        return None


def supabase_attribute_to_qgis_attribute(value, python_type: str):
    return str_convert(value, python_type)


def supabase_to_qgis_feature(feature: SupabaseFeature, layer: Layer) -> QgsFeature:
    name_to_type = {a.name: a.type for a in layer.attributes}

    def get_value(name: str) -> Any:
        value = feature.attributes.get(name)
        type_ = name_to_type[name]
        return supabase_attribute_to_qgis_attribute(value, type_)

    if layer.geometry_type == "point":
        x, y, z = feature.geom["coordinates"]
        qgis_feature = QgsFeature()
        qgis_feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(x, y, z)))
        attrs = [get_value(name) for name in name_to_type]
        qgis_feature.setAttributes(attrs)
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


def qgis_layer_to_supabase_layer(
    qgis_layer: QgsVectorLayer,
    supabase_layer_id: Optional[str] = None,
    *,
    layer_name: Optional[str] = None,
    srid: int,
    parent_id: Optional[str] = None,
    temporary_layer: bool = False,
) -> SupabaseLayer:
    if qgis_layer.geometryType() != Qgis.GeometryType.Point:
        raise ValueError("Only point layers are supported")

    if supabase_layer_id is None:
        supabase_layer_id = str(uuid.uuid4())

    if layer_name is None:
        layer_name = qgis_layer.name()

    return SupabaseLayer(
        id=supabase_layer_id,
        name=layer_name,
        geometry_type="point",
        attributes=[
            LayerAttribute(name=a.name(), type=qmetatype_to_python[a.type()])
            for a in qgis_layer.fields()
        ],
        srid=srid,
        parent_id=parent_id,
        temporary=temporary_layer,
    )
