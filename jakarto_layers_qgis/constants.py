from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable

from qgis.PyQt.QtCore import QMetaType

HERE = Path(__file__).parent

RESOURCES_DIR = HERE / "resources"

auth_url = "http://localhost:8000/auth/v1/token"
postgrest_url = "http://localhost:8000/rest/v1"
realtime_url = "ws://localhost:8000/realtime/v1"
anon_key = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyAgCiAgICAicm9sZSI6ICJhbm9uIiwKICAgI"
    "CJpc3MiOiAic3VwYWJhc2UtZGVtbyIsCiAgIC"
    "AiaWF0IjogMTY0MTc2OTIwMCwKICAgICJleHA"
    "iOiAxNzk5NTM1NjAwCn0.dc_X5iR_VP_qT0zs"
    "iyj_I_OZ2T9FtRU2BBNWN8Bu4GE"
)

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
python_to_qmetatype: dict[str, QMetaType] = {
    "bool": QMetaType.Bool,
    "int": QMetaType.Int,
    "float": QMetaType.Double,
    "str": QMetaType.QString,
    "date": QMetaType.QDate,
    "time": QMetaType.QTime,
    "datetime": QMetaType.QDateTime,
}

type_to_null_value: dict[str, Any] = {
    "bool": False,
    "int": 0,
    "float": 0.0,
    "str": "",
    "date": "1970-01-01",
    "time": "00:00:00",
    "datetime": "1970-01-01 00:00:00",
}


def _type_check_date_or_time(type_):
    def _check(x: Any) -> bool:
        if isinstance(x, type_):
            return True
        if isinstance(x, str):
            try:
                type_.fromisoformat(x)
                return True
            except ValueError:
                return False
        return False

    return _check


type_to_type_check: dict[str, Callable] = {
    "bool": lambda x: isinstance(x, bool),
    "int": lambda x: isinstance(x, int),
    "float": lambda x: isinstance(x, float),
    "str": lambda x: isinstance(x, str),
    "date": _type_check_date_or_time(date),
    "time": _type_check_date_or_time(time),
    "datetime": _type_check_date_or_time(datetime),
}
