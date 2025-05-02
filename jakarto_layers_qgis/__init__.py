import importlib
import platform
import traceback
from pathlib import Path

from qgis.core import Qgis

__version__ = "0.1.0"


def _sentry_before_send(event, hint):
    try:
        # Check if this is an exception
        if "exc_info" in hint:
            _, exc_value, tb = hint["exc_info"]
            stack_summary = traceback.extract_tb(tb)

            # Check if any frame in the traceback is from your package
            for frame in stack_summary:
                if "jakarto_layers_qgis" in frame.filename:
                    return event  # Send to Sentry
            return None  # Ignore
    except Exception:
        pass  # Fail safe

    return None  # Default to ignore


def _sentry_init():
    # Detect if we are running in dev. If so, don't initialize sentry.
    if (Path(__file__).parent.parent / "pyproject.toml").exists():
        # Running in dev, skipping sentry init
        return

    from jakarto_layers_qgis.vendor import sentry_sdk
    from jakarto_layers_qgis.vendor.sentry_sdk.integrations.threading import (
        ThreadingIntegration,
    )

    # to ignore type errors in sentry_sdk.init()
    kwargs = {
        "dsn": "https://b1b033649743ccd6ccf02813ca17e33b@o396741.ingest.us.sentry.io/4509248216694784",
        "before_send": _sentry_before_send,
        "in_app_include": ["jakarto_layers_qgis"],
        "auto_enabling_integrations": False,
        # disable threading integration, it conflicts with something in QGIS
        "disabled_integrations": [ThreadingIntegration],
        "release": __version__,
    }

    # patch for when importing sentry_sdk integrations
    old_import_module = importlib.import_module

    def _import_module(module_name):
        if module_name.startswith("sentry_sdk"):
            return old_import_module(f"jakarto_layers_qgis.vendor.{module_name}")
        return old_import_module(module_name)

    importlib.import_module = _import_module

    sentry_sdk.init(**kwargs)

    # restore original import_module
    importlib.import_module = old_import_module

    sentry_sdk.set_tags(
        {
            "qgis": Qgis.QGIS_VERSION,
            "python": platform.python_version(),
            "system": platform.system(),
        }
    )


def classFactory(_):
    _sentry_init()

    from jakarto_layers_qgis.plugin import Plugin

    return Plugin()
