import os
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
import qgis.utils
from pytest_qgis import utils as pytest_qgis_utils
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QDate, Qt

from jakarto_layers_qgis import supabase_postgrest
from jakarto_layers_qgis.layer import Layer
from jakarto_layers_qgis.supabase_session import SupabaseSession

from .utils import get_response

PLUGIN_NAME = "jakarto_layers_qgis"
MOCK_SESSION = not bool(os.environ.get("NO_MOCK_SESSION"))


@pytest.fixture(autouse=True, scope="session")
def plugin(qgis_app):
    qgis.utils.loadPlugin(PLUGIN_NAME)
    qgis.utils.startPlugin(PLUGIN_NAME)
    plugin_object = qgis.utils.plugins[PLUGIN_NAME]

    return plugin_object


@pytest.fixture(autouse=True)
def mock_session(plugin, monkeypatch) -> Mock:
    if MOCK_SESSION:
        session = Mock(spec=SupabaseSession)
        plugin.adapter._session = session
        plugin.adapter._postgrest_client._session = session
        monkeypatch.setattr(supabase_postgrest.requests, "request", session.request)

    return plugin.adapter._session


@contextmanager
def mock_response(plugin, filename: str):
    if MOCK_SESSION:
        old_request = plugin.adapter._session.request
        response = get_response(filename)
        plugin.adapter._session.request.return_value = response

    yield

    if MOCK_SESSION:
        plugin.adapter._session.request = old_request


@pytest.fixture
def load_layers(plugin) -> list[Layer]:
    with mock_response(plugin, "get_layers.json"):
        plugin.reload_layers()

    return list(plugin.adapter._all_layers.values())


@pytest.fixture
def add_layer(plugin, load_layers) -> Layer:
    layer: Layer = load_layers[0]
    with mock_response(plugin, "get_points.json"):
        plugin.add_layer(layer.supabase_layer_id)

    # needed for QgsTask to process
    pytest_qgis_utils.wait(wait_time_milliseconds=1)

    return layer


def test_get_layers(plugin, load_layers):
    assert len(plugin.adapter._all_layers) == 1
    orig_layer = load_layers[0]
    attrs = orig_layer.attributes
    supabase_layer_id = orig_layer.supabase_layer_id

    layer: Layer = plugin.adapter._all_layers[supabase_layer_id]
    assert layer.name == "road_signs_sample"
    assert layer.geometry_type == "point"
    assert layer.attributes == attrs
    assert layer.supabase_srid == 2949
    assert layer.supabase_parent_layer_id is None

    assert plugin.panel.layerTree.topLevelItemCount() == 1
    item = plugin.panel.layerTree.topLevelItem(0)
    assert item.text(0) == "road_signs_sample"
    assert item.text(1) == "point"
    assert item.text(2) == "2949"
    assert item.data(0, Qt.ItemDataRole.UserRole) == supabase_layer_id


def test_add_layer(plugin, add_layer):
    tree_root = QgsProject.instance().layerTreeRoot()
    qgis_id = add_layer.qgis_layer.id()
    layer_node = tree_root.findLayer(qgis_id)
    assert layer_node is not None

    features = list(layer_node.layer().getFeatures())
    assert len(features) == 9

    geom = list(features[0].geometry().vertices())[0]
    assert geom.x() == 243778.215
    assert geom.y() == 5178023.057
    assert geom.z() == 29.817
    assert features[0].attributes() == [
        1243,
        "506ebca3-eba4-4021-a935-1072bc2372a5",
        "80ba8743-c8ae-4c05-9bf1-b20e581efed9",
        "JAK-I-140",
        "3.02",
        "Rue De La Corniche",
        "Ville",
        "./model_panneau/jak-i-140.png",
        "./photo_panneau/jak2_20240727_63011s041ms.png",
        "https://maps.jakarto.com/?lat=46.738992&lng=-71.298528&uid=jak2_20240727_63012s921ms",
        QDate(2024, 7, 27),
    ]
