from unittest.mock import Mock

import pytest
import qgis.utils

from jakarto_layers_qgis.layer import Layer
from jakarto_layers_qgis.supabase_models import LayerAttribute
from jakarto_layers_qgis.supabase_session import SupabaseSession

from .utils import get_response

PLUGIN_NAME = "jakarto_layers_qgis"


@pytest.fixture(autouse=True, scope="session")
def plugin(qgis_app):
    qgis.utils.loadPlugin(PLUGIN_NAME)
    qgis.utils.startPlugin(PLUGIN_NAME)
    plugin_object = qgis.utils.plugins[PLUGIN_NAME]

    return plugin_object


@pytest.fixture
def mock_session(plugin) -> Mock:
    session = Mock(spec=SupabaseSession)
    plugin.adapter._session = session
    plugin.adapter._postgrest_client._session = session
    return session


def test_get_layers(plugin, mock_session):
    response = get_response("get_layers.json")
    mock_session.request.return_value = response

    plugin.adapter.fetch_layers()

    assert len(plugin.adapter._all_layers) == 1
    id_ = response.json()[0]["id"]
    attrs = [LayerAttribute(**attr) for attr in response.json()[0]["attributes"]]

    layer: Layer = plugin.adapter._all_layers[id_]
    assert layer.name == "road_signs_sample"
    assert layer.geometry_type == "point"
    assert layer.attributes == attrs
    assert layer.supabase_srid == 2949
    assert layer.supabase_parent_layer_id is None
