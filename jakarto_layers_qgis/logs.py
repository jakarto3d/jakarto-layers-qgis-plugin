import os

from qgis.core import Qgis, QgsMessageLog


def debug(message: str) -> None:
    if not os.environ.get("JAKARTO_LAYERS_VERBOSE"):
        return
    print(message)


def log(message: str, level: str = "info") -> None:
    log_level = {
        "info": Qgis.MessageLevel.Info,
        "warning": Qgis.MessageLevel.Warning,
        "error": Qgis.MessageLevel.Critical,
    }[level]
    QgsMessageLog.logMessage(message, "Jakarto Real-Time Layers", log_level)
