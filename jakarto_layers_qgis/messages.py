import os

from qgis import utils
from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgisInterface
from qgis.PyQt.QtWidgets import QMessageBox


def debug(message: str) -> None:
    if not os.environ.get("JAKARTO_LAYERS_VERBOSE"):
        return
    print(message)


def convert_log_level(level: str) -> Qgis.MessageLevel:
    return {
        "info": Qgis.MessageLevel.Info,
        "warning": Qgis.MessageLevel.Warning,
        "critical": Qgis.MessageLevel.Critical,
        "error": Qgis.MessageLevel.Critical,
        "success": Qgis.MessageLevel.Success,
    }.get(level, Qgis.MessageLevel.NoLevel)


def log(message: str, level: str = "info") -> None:
    log_level = convert_log_level(level)
    QgsMessageLog.logMessage(message, "Jakarto Real-Time Layers", log_level)


def notify(message: str, level: str = "info", duration: int = 5) -> None:
    iface: QgisInterface = utils.iface
    log_level = convert_log_level(level)
    iface.messageBar().pushMessage(
        "Jakarto Real-Time Layers",
        message,
        level=log_level,
        duration=duration,
    )


def ask(message: str) -> bool:
    iface: QgisInterface = utils.iface
    return (
        QMessageBox.question(
            iface.mainWindow(),
            "Jakarto Real-Time Layers",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,  # type: ignore
        )
        == QMessageBox.StandardButton.Yes
    )
