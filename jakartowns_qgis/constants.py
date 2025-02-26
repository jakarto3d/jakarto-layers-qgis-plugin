from qgis.PyQt.QtCore import QMetaType, QVariant

geometry_types = {
    "point": "Point",
    "line": "LineString",
    "polygon": "Polygon",
}
geometry_postgis_to_alias = {v: k for k, v in geometry_types.items()}

# https://doc.qt.io/qt-5/qmetatype.html
qmetatype_to_python: dict[QMetaType, str] = {
    QMetaType.Bool: "bool",
    QMetaType.Int: "int",
    QMetaType.UInt: "int",
    QMetaType.Double: "float",
    QMetaType.QString: "str",
    QMetaType.Long: "int",
    QMetaType.LongLong: "int",
    QMetaType.Short: "int",
    QMetaType.ULong: "int",
    QMetaType.ULongLong: "int",
    QMetaType.UShort: "int",
    QMetaType.Float: "float",
    QMetaType.QDate: "date",
    QMetaType.QTime: "time",
    QMetaType.QDateTime: "datetime",
}
python_to_qvariant: dict[str, QVariant.Type] = {
    "bool": QVariant.Bool,
    "int": QVariant.Int,
    "float": QVariant.Double,
    "str": QVariant.String,
    "date": QVariant.Date,
    "time": QVariant.Time,
    "datetime": QVariant.DateTime,
}
