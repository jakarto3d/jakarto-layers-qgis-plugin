from typing import Optional
from unittest.mock import Mock, call

from qgis.core import QgsAuthManager

from jakarto_layers_qgis import auth
from jakarto_layers_qgis.auth import JakartoAuthentication


def setup_mocks(
    monkeypatch,
    *_,
    is_auth_database_set: bool = True,
    auth_config_id: Optional[str] = None,
    auth_config: Optional[tuple[str, str]] = None,
    auth_settings: tuple[Optional[str], Optional[str]] = (None, None),
    ask_credentials_return_value: tuple[Optional[str], Optional[str]] = (None, None),
):
    auth_manager = Mock(spec=QgsAuthManager)
    monkeypatch.setattr(
        auth,
        "QgsApplication",
        Mock(authManager=Mock(return_value=auth_manager)),
    )
    auth_manager.masterPasswordHashInDatabase.return_value = is_auth_database_set
    auth_manager.masterPasswordIsSet.return_value = is_auth_database_set
    auth_manager.setMasterPassword.return_value = None
    config_ids = []
    auth_manager.configIds.return_value = config_ids

    mock_settings = Mock()
    monkeypatch.setattr(auth, "QSettings", Mock(return_value=mock_settings))
    settings_values = {}
    mock_settings.value.side_effect = settings_values.get
    if auth_config_id:
        settings_values["jakarto_auth_config_id"] = auth_config_id
        config_ids.append(auth_config_id)
    if auth_settings:
        settings_values["jakartowns/username"] = auth_settings[0]
        settings_values["jakartowns/password"] = auth_settings[1]

    config = Mock(isValid=lambda: True, id=lambda: "config_id")
    monkeypatch.setattr(auth, "QgsAuthMethodConfig", Mock(return_value=config))

    def get_token(*_, username=None, password=None, **__):
        token_response = auth._TokenResponse(
            user_id="user_id",
            access_token="access_token",
            refresh_token="refresh_token",
            token_expires_at_timestamp=1234567890,
        )
        if auth_config and [username, password] == list(auth_config):
            return token_response
        if auth_settings and [username, password] == list(auth_settings):
            return token_response
        if ask_credentials_return_value and [username, password] == list(
            ask_credentials_return_value
        ):
            return token_response
        return None

    monkeypatch.setattr(auth, "_get_token", get_token)
    if auth_config:
        config_values = {"username": auth_config[0], "password": auth_config[1]}
        config.config.side_effect = config_values.get
        auth_manager.loadAuthenticationConfig.return_value = True

    monkeypatch.setattr(
        auth, "_ask_credentials", Mock(return_value=ask_credentials_return_value)
    )

    return auth_manager, mock_settings


def check_function(username: str, password: str) -> bool:
    return (username, password) in [
        ("test@test.com", "password"),
    ]


def test_setup_auth_from_config_existing(monkeypatch):
    setup_mocks(
        monkeypatch,
        is_auth_database_set=True,
        auth_config_id="some_auth_config_id",
        auth_config=("test@test.com", "password"),
    )

    assert JakartoAuthentication().setup_auth()


def test_setup_auth_from_config_in_settings(monkeypatch):
    auth_manager, mock_settings = setup_mocks(
        monkeypatch,
        is_auth_database_set=True,
        auth_config_id="some_auth_config_id",
        auth_settings=("test@test.com", "password"),
    )

    assert JakartoAuthentication().setup_auth()
    mock_settings.setValue.assert_called_once_with(
        "jakarto_auth_config_id", "config_id"
    )
    assert auth_manager.storeAuthenticationConfig.called


def test_setup_auth_from_config_ask_success(monkeypatch):
    auth_manager, mock_settings = setup_mocks(
        monkeypatch,
        is_auth_database_set=True,
        auth_config_id="some_auth_config_id",
        ask_credentials_return_value=("test@test.com", "password"),
        auth_settings=(None, None),
    )

    assert JakartoAuthentication().setup_auth()

    mock_settings.setValue.assert_called_once_with(
        "jakarto_auth_config_id", "config_id"
    )
    assert auth_manager.storeAuthenticationConfig.called


def test_setup_auth_from_config_ask_cancel(monkeypatch):
    setup_mocks(
        monkeypatch,
        is_auth_database_set=True,
        auth_config_id="some_auth_config_id",
        ask_credentials_return_value=(None, None),
        auth_settings=(None, None),
    )

    assert not JakartoAuthentication().setup_auth()


def test_setup_auth_from_settings_existing(monkeypatch):
    setup_mocks(
        monkeypatch,
        is_auth_database_set=False,
        auth_settings=("test@test.com", "password"),
    )

    assert JakartoAuthentication().setup_auth()


def test_setup_auth_from_settings_ask_success(monkeypatch):
    _, mock_settings = setup_mocks(
        monkeypatch,
        is_auth_database_set=False,
        ask_credentials_return_value=("test@test.com", "password"),
    )

    assert JakartoAuthentication().setup_auth()
    mock_settings.setValue.assert_has_calls(
        [
            call("jakartowns/username", "test@test.com"),
            call("jakartowns/password", "password"),
        ]
    )


def test_setup_auth_from_settings_ask_cancel(monkeypatch):
    _, mock_settings = setup_mocks(
        monkeypatch,
        is_auth_database_set=False,
        ask_credentials_return_value=(None, None),
    )

    assert not JakartoAuthentication().setup_auth()
    mock_settings.setValue.assert_not_called()
