import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from unittest.mock import Mock

import pytest
import qgis.utils
from pytest_qgis import utils as pytest_qgis_utils
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPoint,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QMetaType, QPoint, Qt
from qgis.PyQt.QtWidgets import QAction, QDialog, QInputDialog, QMenu, QMessageBox

import jakarto_layers_qgis.plugin
from jakarto_layers_qgis import supabase_postgrest
from jakarto_layers_qgis.layer import Layer
from jakarto_layers_qgis.supabase_models import LayerAttribute
from jakarto_layers_qgis.supabase_session import SupabaseSession
from jakarto_layers_qgis.ui.create_sub_layer import CreateSubLayerDialog

from .utils import get_data_path, get_response, get_response_file

PLUGIN_NAME = "jakarto_layers_qgis"
MOCK_SESSION = not bool(os.environ.get("NO_MOCK_SESSION"))


@dataclass
class Request:
    method: str
    url: str
    params: dict = field(default_factory=dict)
    json: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    timeout: int = field(default=5)


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
def clear_layers(plugin):
    plugin.adapter.remove_all_layers()
    plugin.adapter._all_layers.clear()


@pytest.fixture
def load_layers(plugin, clear_layers, mock_session) -> list[Layer]:
    with mock_response(plugin, "get_layers.json"):
        plugin.reload_layers()

    if MOCK_SESSION:
        mock_session.request.reset_mock()

    return list(plugin.adapter._all_layers.values())


@pytest.fixture
def add_layer(plugin, load_layers, mock_session) -> Layer:
    layer: Layer = load_layers[0]
    with mock_response(plugin, "get_points.json"):
        plugin.add_layer(layer.supabase_layer_id)

    # needed for QgsTask to process
    pytest_qgis_utils.wait(wait_time_milliseconds=1)

    if MOCK_SESSION:
        mock_session.request.reset_mock()

    return layer


def first_point_attrs(attributes: list[LayerAttribute]):
    sample_data = get_response("get_points.json").json()
    attrs = [sample_data[0]["attributes"][key] for key in [a.name for a in attributes]]
    attrs[-1] = QDate(2024, 7, 27)
    return attrs


@pytest.fixture
def message_box():
    _originals = {}
    _messages = {}

    def capture(level: str):
        def _capture(parent, title, text, buttons=None):
            _messages[level].append((title, text))

        _originals[level] = getattr(QMessageBox, level)
        setattr(QMessageBox, level, _capture)
        _messages[level] = []

    capture("information")
    capture("warning")
    capture("critical")

    yield _messages

    for level, original in _originals.items():
        setattr(QMessageBox, level, original)


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


def test_add_layer(plugin, add_layer: Layer):
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
    assert features[0].attributes() == first_point_attrs(add_layer.attributes)


def test_create_sub_layer_no_selection(plugin, add_layer: Layer, message_box):
    plugin.create_sub_layer(add_layer.supabase_layer_id)
    assert message_box["warning"][0][0] == "No Features Selected"


def test_create_sub_layer_from_sub_layer(
    plugin, add_layer: Layer, message_box, monkeypatch
):
    monkeypatch.setattr(add_layer, "supabase_parent_layer_id", "123")
    plugin.create_sub_layer(add_layer.supabase_layer_id)
    assert message_box["warning"][0][0] == "Already a sub-layer"


def test_create_sub_layer_3_features(
    plugin, add_layer: Layer, monkeypatch, mock_session
):
    # given
    # Select some features from the layer
    layer = add_layer.qgis_layer
    features = list(layer.getFeatures())
    layer.selectByIds([f.id() for f in features[:3]])  # Select first 3 features

    props = Mock()
    props.name = "test_sub_layer"
    dialog = Mock(
        return_value=Mock(
            spec=CreateSubLayerDialog,
            exec_=Mock(return_value=QDialog.DialogCode.Accepted),
            properties=props,
        )
    )
    monkeypatch.setattr(jakarto_layers_qgis.plugin, "CreateSubLayerDialog", dialog)

    # when
    plugin.create_sub_layer(add_layer.supabase_layer_id)

    # then
    ids = list(plugin.adapter._all_layers.keys())
    assert len(ids) == 2
    sub_layer_id = ids[1]

    assert plugin.panel.layerTree.topLevelItemCount() == 1
    parent_item = plugin.panel.layerTree.topLevelItem(0)
    item = parent_item.child(0)
    assert item.text(0) == "test_sub_layer"
    assert item.text(1) == "point"
    assert item.text(2) == "2949"
    assert item.data(0, Qt.ItemDataRole.UserRole) == sub_layer_id

    assert mock_session.request.call_count == 2
    layer_post = mock_session.request.call_args_list[0]
    request = Request(**layer_post.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.json["name"] == "test_sub_layer"
    assert request.json["parent_id"] == add_layer.supabase_layer_id

    points_post = mock_session.request.call_args_list[1]
    request = Request(**points_post.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/points"
    assert request.json[0]["layer_id"] == sub_layer_id
    assert len(request.json) == 3


def test_merge_sub_layer(plugin, add_layer: Layer, mock_session):
    """We don't test the actual sql function, because supabase is not running during tests"""
    # given
    layer = add_layer.qgis_layer
    features = list(layer.getFeatures())
    layer.selectByIds([f.id() for f in features[:3]])  # Select first 3 features
    plugin.adapter.create_sub_layer(add_layer, "test_sub_layer")
    sub_layer_id = list(plugin.adapter._all_layers.keys())[1]

    mock_session.request.reset_mock()

    # when
    plugin.merge_sub_layer(sub_layer_id)

    # then
    assert mock_session.request.call_count == 1
    merge_call = mock_session.request.call_args_list[0]
    request = Request(**merge_call.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/rpc/merge_sub_layer"
    assert request.json["sub_layer_id"] == sub_layer_id


def test_rename_layer(plugin, add_layer: Layer, mock_session, monkeypatch):
    # given
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("new_name", True))

    # when
    plugin.rename_layer(add_layer.supabase_layer_id)

    # then
    assert mock_session.request.call_count == 1
    rename_call = mock_session.request.call_args_list[0]
    request = Request(**rename_call.kwargs)
    assert request.method == "PATCH"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.params["id"] == f"eq.{add_layer.supabase_layer_id}"
    assert request.json["name"] == "new_name"


def test_add_feature_in_qgis(add_layer: Layer, mock_session):
    # given
    qgis_feature = QgsFeature()
    qgis_feature.setGeometry(QgsGeometry.fromPoint(QgsPoint(243778, 5178023, 29)))
    attrs = first_point_attrs(add_layer.attributes)
    qgis_feature.setAttributes(attrs)

    # when
    add_layer.on_event_added(add_layer.supabase_layer_id, [qgis_feature])
    add_layer.after_commit()

    # then
    assert mock_session.request.call_count == 1
    add_call = mock_session.request.call_args_list[0]
    request = Request(**add_call.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/points"
    assert request.json["attributes"]["fid"] == 1243


def test_update_feature_in_qgis(add_layer: Layer, mock_session):
    # given
    qgis_feature = list(add_layer.qgis_layer.getFeatures())[0]

    # when
    add_layer.qgis_layer.startEditing()
    qgis_feature.setAttribute(0, 1111)
    add_layer.qgis_layer.updateFeature(qgis_feature)
    add_layer.qgis_layer.commitChanges()

    # then
    assert mock_session.request.call_count == 1
    update_call = mock_session.request.call_args_list[0]
    request = Request(**update_call.kwargs)
    assert request.method == "PATCH"
    assert request.url == "http://localhost:8000/rest/v1/points"
    assert request.json["attributes"]["fid"] == 1111


def test_delete_feature_in_qgis(add_layer: Layer, mock_session):
    # given
    qgis_feature = list(add_layer.qgis_layer.getFeatures())[0]
    supabase_id = add_layer.get_supabase_feature_id(qgis_feature.id())

    # when
    add_layer.qgis_layer.startEditing()
    add_layer.qgis_layer.deleteFeature(qgis_feature.id())
    add_layer.qgis_layer.commitChanges()

    # then
    assert mock_session.request.call_count == 1
    delete_call = mock_session.request.call_args_list[0]
    request = Request(**delete_call.kwargs)
    assert request.method == "DELETE"
    assert request.url == "http://localhost:8000/rest/v1/points"
    assert request.params["id"] == f"eq.{supabase_id}"


def test_add_attribute_in_qgis(add_layer: Layer, mock_session):
    # when
    attribs = [asdict(a) for a in add_layer.attributes]
    attribs.append({"name": "new_attr", "type": "str"})
    layer = add_layer.qgis_layer
    layer.startEditing()
    layer.addAttribute(QgsField("new_attr", QMetaType.QString))
    layer.commitChanges()

    # then
    assert mock_session.request.call_count == 1
    add_call = mock_session.request.call_args_list[0]
    request = Request(**add_call.kwargs)
    assert request.method == "PATCH"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.params["id"] == f"eq.{add_layer.supabase_layer_id}"
    assert request.json["attributes"] == attribs


def test_remove_attribute_in_qgis(add_layer: Layer, mock_session):
    # when
    attribs = [asdict(a) for a in add_layer.attributes]
    attribs.pop(0)
    layer = add_layer.qgis_layer
    layer.startEditing()
    layer.deleteAttribute(0)
    layer.commitChanges()

    # then
    assert mock_session.request.call_count == 1
    remove_call = mock_session.request.call_args_list[0]
    request = Request(**remove_call.kwargs)
    assert request.method == "PATCH"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.params["id"] == f"eq.{add_layer.supabase_layer_id}"
    assert request.json["attributes"] == attribs


def test_add_feature_in_supabase(plugin, add_layer: Layer):
    # given
    insert_event = get_response_file("supabase_insert_event.json")
    supabase_id = insert_event["data"]["record"]["id"]
    assert add_layer.qgis_layer.featureCount() == 9

    # when
    plugin.adapter.on_supabase_realtime_event(insert_event, only_print_errors=False)

    # then
    assert add_layer.qgis_layer.featureCount() == 10
    assert add_layer.get_qgis_feature_id(supabase_id) is not None


def test_update_feature_in_supabase(plugin, add_layer: Layer):
    # given
    update_event = get_response_file("supabase_update_event.json")
    supabase_id = update_event["data"]["record"]["id"]
    assert add_layer.qgis_layer.featureCount() == 9

    # when
    plugin.adapter.on_supabase_realtime_event(update_event, only_print_errors=False)

    # then
    assert add_layer.qgis_layer.featureCount() == 9
    feature_id = add_layer.get_qgis_feature_id(supabase_id)
    assert feature_id is not None
    qgis_feature = add_layer.get_qgis_feature(feature_id)
    assert qgis_feature is not None
    assert qgis_feature.attributeMap()["fid"] == 1246


def test_delete_feature_in_supabase(plugin, add_layer: Layer):
    # given
    delete_event = get_response_file("supabase_delete_event.json")
    supabase_id = delete_event["data"]["old_record"]["id"]
    assert add_layer.qgis_layer.featureCount() == 9

    # when
    plugin.adapter.on_supabase_realtime_event(delete_event, only_print_errors=False)

    # then
    assert add_layer.qgis_layer.featureCount() == 8
    assert add_layer.get_qgis_feature_id(supabase_id) is None


def test_import_layer(plugin, clear_layers, mock_session):
    # given
    geojson = get_data_path("road_signs_sample.geojson")
    layer = QgsVectorLayer(f"geojson://{geojson}", "road_signs_sample", "ogr")
    assert layer.featureCount() == 9

    # when
    plugin.adapter.import_layer(layer)

    # then
    assert len(plugin.adapter._all_layers) == 1
    layer = list(plugin.adapter._all_layers.values())[0]
    assert layer.name == "road_signs_sample"
    assert layer.geometry_type == "point"
    assert layer.attributes == [
        LayerAttribute(name="fid", type="int"),
        LayerAttribute(name="uuid", type="str"),
        LayerAttribute(name="uuid_support", type="str"),
        LayerAttribute(name="p_code", type="str"),
        LayerAttribute(name="degagement_m", type="str"),
        LayerAttribute(name="nom_rue", type="str"),
        LayerAttribute(name="classe_panneau", type="str"),
        LayerAttribute(name="model_panneau", type="str"),
        LayerAttribute(name="photo_panneau", type="str"),
        LayerAttribute(name="jakartowns_url", type="str"),
        LayerAttribute(name="date_numerisation", type="date"),
    ]

    assert mock_session.request.call_count == 2
    layer_call = mock_session.request.call_args_list[0]
    request = Request(**layer_call.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.json["name"] == "road_signs_sample"

    points_call = mock_session.request.call_args_list[1]
    request = Request(**points_call.kwargs)
    assert request.method == "POST"
    assert request.url == "http://localhost:8000/rest/v1/points"
    assert len(request.json) == 9
    assert request.json[0]["attributes"]["fid"] == 1243


def test_drop_layer(plugin, add_layer: Layer, mock_session):
    # given
    plugin.adapter.drop_layer(add_layer.supabase_layer_id)

    # then
    assert len(plugin.adapter._all_layers) == 0

    assert mock_session.request.call_count == 1
    drop_call = mock_session.request.call_args_list[0]
    request = Request(**drop_call.kwargs)
    assert request.method == "DELETE"
    assert request.url == "http://localhost:8000/rest/v1/layers"
    assert request.params["id"] == f"eq.{add_layer.supabase_layer_id}"


def test_context_menu(plugin, add_layer: Layer, monkeypatch):
    """Only test context menu generation"""
    monkeypatch.setattr(QMenu, "exec_", lambda *a, **kw: QAction(text="Load Layer"))
    plugin.show_layer_context_menu(QPoint(0, 0))
