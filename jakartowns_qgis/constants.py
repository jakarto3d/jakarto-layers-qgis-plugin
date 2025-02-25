from datetime import date, datetime, time

from qgis.PyQt.QtCore import QMetaType

geometry_types = {
    "point": "Point",
    "line": "LineString",
    "polygon": "Polygon",
}

# https://doc.qt.io/qt-5/qmetatype.html
qmetatype_to_python = {
    QMetaType.Bool: bool,
    QMetaType.Int: int,
    QMetaType.UInt: int,
    QMetaType.Double: float,
    QMetaType.QString: str,
    QMetaType.Long: int,
    QMetaType.LongLong: int,
    QMetaType.Short: int,
    QMetaType.ULong: int,
    QMetaType.ULongLong: int,
    QMetaType.UShort: int,
    QMetaType.Float: float,
    QMetaType.QDate: date,
    QMetaType.QTime: time,
    QMetaType.QDateTime: datetime,
}
