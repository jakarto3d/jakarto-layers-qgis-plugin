from pathlib import Path

from qgis.PyQt.QtGui import QIcon

HERE = Path(__file__).parent


def icon(name: str) -> QIcon:
    return QIcon(str(HERE / "icons" / name))
