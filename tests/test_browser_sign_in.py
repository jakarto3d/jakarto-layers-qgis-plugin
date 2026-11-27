from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests

from jakarto_layers_qgis import auth, browser_sign_in, session_store
from jakarto_layers_qgis.auth import BROWSER_SIGN_IN, JakartoAuthentication
from jakarto_layers_qgis.browser_sign_in import BrowserSignInError


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(str(self.status_code), response=self)


class FakeSession(requests.Session):
    def __init__(self, *responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get("json")))
        return self.responses.pop(0)


CODE = {
    "device_code": "dc",
    "user_code": "ABCD1234",
    "verification_uri": "https://account.jakarto.com/device",
    "verification_uri_complete": "https://account.jakarto.com/device?user_code=ABCD1234",
    "expires_in": 600,
    "interval": 5,
}
TOKEN = {"access_token": "jwt-1", "expires_at": 0, "user": {"sub": "user-uuid"}}


def test_asks_for_a_code_as_the_layers_plugin():
    session = FakeSession(FakeResponse(200, CODE))

    code = browser_sign_in.request_device_code(session)

    assert session.calls[0][2] == {"client_id": "jakarto-layers-qgis-plugin"}
    assert code.display_code == "ABCD-1234"


def test_poll_until_approved_and_stop_on_refusal():
    code = browser_sign_in.DeviceCode(**CODE)
    session = FakeSession(
        FakeResponse(400, {"error": "authorization_pending"}),
        FakeResponse(200, {"success": True}),
        FakeResponse(403, {"error": "access_denied"}),
    )

    assert browser_sign_in.poll(session, code) == browser_sign_in.PENDING
    assert browser_sign_in.poll(session, code) == browser_sign_in.APPROVED
    with pytest.raises(BrowserSignInError, match="refused"):
        browser_sign_in.poll(session, code)


def test_supabase_token_comes_from_the_token_function():
    session = FakeSession(FakeResponse(200, TOKEN))

    token = browser_sign_in.supabase_token(session, "https://supabase.jakarto.com")

    assert session.calls[0][:2] == (
        "GET",
        "https://supabase.jakarto.com/functions/v1/token",
    )
    # the same Supabase user id as a password sign-in, so the realtime channel
    # jakartowns_positions_<user_id> is unchanged
    assert (token.user_id, token.access_token) == ("user-uuid", "jwt-1")


def test_saved_cookies_come_back_without_their_expiry_and_bad_entries_are_ignored():
    session = requests.Session()
    session.cookies.set("s", "tok.sig", domain=".jakarto.com", expires=1)
    saved = browser_sign_in.export_cookies(session) + [None, {"name": "x"}, "junk"]

    restored = requests.Session()
    browser_sign_in.restore_cookies(restored, saved)
    browser_sign_in.restore_cookies(restored, {"not": "a list"})

    (cookie,) = list(restored.cookies)
    assert (cookie.name, cookie.value, cookie.expires) == ("s", "tok.sig", None)


@pytest.fixture
def settings(monkeypatch):
    values = {}
    mock = Mock()
    mock.value.side_effect = values.get
    mock.setValue.side_effect = values.__setitem__
    mock.remove.side_effect = lambda key: values.pop(key, None)
    monkeypatch.setattr(auth, "QSettings", Mock(return_value=mock))
    # the session store reads the same settings
    monkeypatch.setattr(session_store, "QSettings", Mock(return_value=mock))
    monkeypatch.setattr(session_store, "_auth_database_ready", lambda: False)
    # no QGIS auth database: the legacy path, simplest to drive
    monkeypatch.setattr(
        JakartoAuthentication, "_is_auth_database_set", lambda self: False
    )
    return values


def saved_session():
    return json.dumps(
        [{"name": "s", "value": "tok.sig", "domain": ".jakarto.com", "path": "/"}]
    )


def test_a_saved_browser_sign_in_is_used_before_any_password(settings, monkeypatch):
    settings[browser_sign_in.SESSION_SETTING] = saved_session()
    settings["jakartowns/username"] = "me@example.com"
    settings["jakartowns/password"] = "secret"
    monkeypatch.setattr(
        auth.browser_sign_in,
        "supabase_token",
        lambda session, url: browser_sign_in.SupabaseToken("user-uuid", "jwt-1", 0),
    )
    get_token = Mock()
    monkeypatch.setattr(auth, "_get_token", get_token)

    authentication = JakartoAuthentication()
    assert authentication.setup_auth(ask=False)

    assert (authentication.user_id, authentication.access_token) == (
        "user-uuid",
        "jwt-1",
    )
    get_token.assert_not_called()


def test_an_expired_browser_sign_in_falls_back_to_the_password(settings, monkeypatch):
    settings[browser_sign_in.SESSION_SETTING] = saved_session()
    settings["jakartowns/username"] = "me@example.com"
    settings["jakartowns/password"] = "secret"

    def refused(session, url):
        raise requests.HTTPError("401")

    monkeypatch.setattr(auth.browser_sign_in, "supabase_token", refused)
    monkeypatch.setattr(
        auth, "_get_token", lambda **_: auth._TokenResponse("u", "password-jwt", "r", 0)
    )

    authentication = JakartoAuthentication()
    assert authentication.setup_auth(ask=False)
    assert authentication.access_token == "password-jwt"


def test_refreshing_after_a_browser_sign_in_asks_the_token_function(
    settings, monkeypatch
):
    tokens = iter(["jwt-1", "jwt-2"])
    monkeypatch.setattr(
        auth.browser_sign_in,
        "supabase_token",
        lambda session, url: browser_sign_in.SupabaseToken(
            "user-uuid", next(tokens), 0
        ),
    )
    authentication = JakartoAuthentication()
    updates = []
    authentication.access_token_updated.connect(lambda: updates.append(1))

    assert authentication._use_browser_session(requests.Session())
    assert authentication.refresh_access_token()

    assert authentication.access_token == "jwt-2"
    assert len(updates) == 2  # the realtime worker re-authenticates on each


def test_choosing_the_browser_in_the_credentials_window(settings, monkeypatch):
    monkeypatch.setattr(
        auth, "_ask_credentials", lambda in_qsettings: (BROWSER_SIGN_IN, None)
    )
    monkeypatch.setattr(
        JakartoAuthentication, "sign_in_with_browser", lambda self: True
    )

    assert JakartoAuthentication().setup_auth(ask=True)


def test_sign_out_forgets_the_shared_browser_session(settings, monkeypatch):
    settings[browser_sign_in.SESSION_SETTING] = saved_session()
    ended = []
    monkeypatch.setattr(
        auth.browser_sign_in, "sign_out", lambda session: ended.append(session)
    )
    authentication = JakartoAuthentication()
    authentication._jakarto_session = requests.Session()
    authentication.access_token = "jwt-1"

    authentication.sign_out()

    assert len(ended) == 1
    assert browser_sign_in.SESSION_SETTING not in settings
    assert authentication.access_token is None


def test_sign_out_also_forgets_a_saved_password(settings, monkeypatch):
    # Otherwise the next connection signs straight back in with it.
    settings["jakartowns/username"] = "me@example.com"
    settings["jakartowns/password"] = "secret"
    settings[auth.AUTH_CONFIG_ID_KEY] = "cfg-1"
    auth_manager = Mock()
    auth_manager.configIds.return_value = ["cfg-1"]
    monkeypatch.setattr(
        auth, "QgsApplication", Mock(authManager=Mock(return_value=auth_manager))
    )

    JakartoAuthentication().sign_out()

    assert "jakartowns/password" not in settings
    assert auth.AUTH_CONFIG_ID_KEY not in settings
    auth_manager.removeAuthenticationConfig.assert_called_once_with("cfg-1")
    # the address stays, to fill the form next time
    assert settings["jakartowns/username"] == "me@example.com"


class HTTPErrorWith(requests.HTTPError):
    def __init__(self, status):
        super().__init__(str(status), response=FakeResponse(status, {}))


def _token_raising(status):
    def raise_(session, url):
        raise HTTPErrorWith(status)

    return raise_


def test_a_refused_saved_session_is_forgotten_an_unreachable_one_kept(
    settings, monkeypatch
):
    settings[browser_sign_in.SESSION_SETTING] = saved_session()
    monkeypatch.setattr(auth, "_get_token", lambda **_: None)

    monkeypatch.setattr(auth.browser_sign_in, "supabase_token", _token_raising(502))
    JakartoAuthentication().setup_auth(ask=False)
    assert browser_sign_in.SESSION_SETTING in settings  # a passing server error

    monkeypatch.setattr(auth.browser_sign_in, "supabase_token", _token_raising(401))
    JakartoAuthentication().setup_auth(ask=False)
    assert browser_sign_in.SESSION_SETTING not in settings  # refused: not retried


def test_a_session_whose_supabase_token_fails_is_ended_on_the_server(
    settings, monkeypatch
):
    # Approved in the browser, then the token function fails: the account
    # session just opened must not stay valid with nothing knowing about it.
    class Dialog:
        def __init__(self, session):
            self.error = None

        def exec(self):
            return auth.QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "jakarto_layers_qgis.browser_sign_in_dialog.BrowserSignInDialog", Dialog
    )
    monkeypatch.setattr(auth.browser_sign_in, "supabase_token", _token_raising(500))
    ended = []
    monkeypatch.setattr(
        auth.browser_sign_in, "sign_out", lambda session: ended.append(session)
    )

    assert JakartoAuthentication().sign_in_with_browser() is False
    assert len(ended) == 1
    assert browser_sign_in.SESSION_SETTING not in settings


def test_sessions_honour_jakarto_verify_ssl(monkeypatch):
    monkeypatch.setattr(auth, "verify_ssl", False)
    assert auth._new_session().verify is False
    monkeypatch.setattr(auth, "verify_ssl", True)
    assert auth._new_session().verify is True


def test_sign_out_leaves_nothing_of_the_signed_in_state(settings, monkeypatch):
    monkeypatch.setattr(auth.browser_sign_in, "sign_out", lambda session: None)
    users = []
    monkeypatch.setattr(auth.sentry_sdk, "set_user", lambda user: users.append(user))
    authentication = JakartoAuthentication()
    authentication._jakarto_session = requests.Session()
    authentication.user_id = "user-uuid"
    authentication.access_token = "jwt"
    authentication._refresh_token = "refresh"

    authentication.sign_out()

    assert authentication.user_id is None
    assert authentication.access_token is None
    assert authentication._refresh_token is None
    assert users == [None]


@pytest.mark.parametrize(
    ("status", "payload"), [(500, {"error": "server_error"}), (502, None)]
)
def test_poll_keeps_waiting_through_a_passing_server_error(status, payload):
    code = browser_sign_in.DeviceCode(**CODE)
    session = FakeSession(FakeResponse(status, payload))

    assert browser_sign_in.poll(session, code) == browser_sign_in.PENDING


@pytest.mark.parametrize("payload", [{}, None, ["x"]])
def test_an_unexpected_device_code_answer_is_a_clear_error(payload):
    session = FakeSession(FakeResponse(200, payload))

    with pytest.raises(BrowserSignInError, match="Unexpected answer"):
        browser_sign_in.request_device_code(session)
