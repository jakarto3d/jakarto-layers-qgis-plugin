import pytest

from jakarto_layers_qgis import auth, constants


@pytest.fixture(autouse=True)
def mock_constants():
    constants.supabase_url = "http://127.0.0.1:9999"
    constants.jakartowns_url = "http://127.0.0.1:8888"
    auth.auth_url = "http://127.0.0.1:9999/auth/v1/token"
