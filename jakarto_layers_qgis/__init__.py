import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/vendor")
from . import vendor  # noqa: F401

# This may cause issues if the vendorized packages don't make all their imports
# when the base module is imported.
# Still, we try to not affect the original sys.path.
sys.path.pop(0)


def classFactory(_):
    from jakarto_layers_qgis.plugin import Plugin

    return Plugin()
