from pathlib import Path

from qgis.PyQt.QtGui import QIcon

HERE = Path(__file__).parent


def icon_path(name: str) -> Path:
    return HERE / "icons" / name


def icon(name: str) -> QIcon:
    return QIcon(str(icon_path(name)))
