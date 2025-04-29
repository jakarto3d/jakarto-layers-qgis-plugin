import os
from pathlib import Path

from qgis.PyQt.QtCore import QMetaType

HERE = Path(__file__).parent

RESOURCES_DIR = HERE / "resources"

# prod variables
supabase_url = "https://supabase.jakarto.com"
auth_url = f"{supabase_url}/auth/v1/token"
postgrest_url = f"{supabase_url}/rest/v1"
realtime_url = f"{supabase_url.replace('https', 'wss')}/realtime/v1"
anon_key = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiY"
    "XNlLWRlbW8iLCJpYXQiOjE2NDE3NjkyMDAsImV4cCI6MTc5OTUzNTYwMH0.AhccFnQokMqgFJr"
    "etk5dXp1oAtzTbD5ocvuP1Ap-rzM"
)
verify_ssl = os.getenv("JAKARTO_VERIFY_SSL", "true").lower() == "true"

jakartowns_url = os.getenv("JAKARTO_LAYERS_JAKARTOWNS_URL", "https://maps.jakarto.com")

if os.getenv("JAKARTO_LAYERS_SUPABASE_LOCAL"):
    supabase_url = "http://localhost:8000"
    auth_url = f"{supabase_url}/auth/v1/token"
    postgrest_url = f"{supabase_url}/rest/v1"
    realtime_url = f"{supabase_url.replace('http', 'ws')}/realtime/v1"
    anon_key = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyAgCiAgICAicm9sZSI6ICJhbm9uIiwKICAgI"
        "CJpc3MiOiAic3VwYWJhc2UtZGVtbyIsCiAgICAiaWF0IjogMTY0MTc2OTIwMCwKICAgICJleHA"
        "iOiAxNzk5NTM1NjAwCn0.dc_X5iR_VP_qT0zsiyj_I_OZ2T9FtRU2BBNWN8Bu4GE"
    )


if not verify_ssl:
    # disable ssl verification for the realtime client
    import ssl

    from .vendor.realtime._async import client

    def patched_connect(*args, **kwargs):
        return real_connect(*args, **kwargs, ssl=ssl._create_unverified_context())

    real_connect = client.connect
    client.connect = patched_connect


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
