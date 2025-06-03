import time
from dataclasses import dataclass
from typing import Optional, Union

import requests
from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import QgsApplication, QgsAuthMethodConfig
from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .constants import anon_key, auth_url, verify_ssl
from .messages import log
from .vendor import sentry_sdk

AUTH_CONFIG_ID_KEY = "jakarto_auth_config_id"


class JakartoAuthentication(QObject):
    access_token_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self.user_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None

        self._qsettings = QSettings("Jakarto", "JakartoPlugin")

        # Refresh access token every 5 minutes
        self._refresh_token_timer = QTimer(self)
        self._refresh_token_timer.timeout.connect(self.refresh_access_token)
        self._refresh_token_timer.setInterval(5 * 60 * 1000)

    def is_authenticated(self) -> bool:
        return self._username is not None and self._password is not None

    def setup_auth(self, ask=True) -> bool:
        """Setup authentication for the plugin.

        If the authentication database is set, it will store the credentials in the
        authentication database.

        If the authentication database is not set, it will store the credentials in
        the settings (not recommended).

        If the credentials are valid, the `username` and `password` attributes will
        be set.

        Args:
            ask: If True, the user will be asked for credentials.

        Returns:
            True if the credentials are valid, False otherwise.
        """

        if self.is_authenticated():
            return True

        if self._is_auth_database_set():
            # store credentials in auth database
            username, password = self._get_credentials_from_auth_database()
            if username and password and self._check_auth(username, password):
                log(f"Using credentials from auth database: {username}")
                return True
            # check in settings, if we have credentials there, store them in auth database
            username, password = self.get_credentials_from_settings()
            if username and password and self._check_auth(username, password):
                self._set_credentials_in_auth_database(username, password)
                log(f"Stored credentials from settings in auth database: {username}")
                return True
            if ask:
                while True:
                    username, password = _ask_credentials(in_qsettings=False)
                    if username is None or password is None:
                        break
                    if self._check_auth(username, password):
                        self._set_credentials_in_auth_database(username, password)
                        log(f"Stored credentials in auth database: {username}")
                        return True
                    log(f"Invalid credentials for username: {username}")
        else:
            # legacy way, store credentials in settings
            username, password = self.get_credentials_from_settings()
            if username and password and self._check_auth(username, password):
                log(f"Using credentials from settings: {username}")
                return True
            if ask:
                while True:
                    username, password = _ask_credentials(in_qsettings=True)
                    if username is None or password is None:
                        break
                    if self._check_auth(username, password):
                        self._set_credentials_in_settings(username, password)
                        log(f"Stored credentials in settings: {username}")
                        return True
                    log(f"Invalid credentials for username: {username}")

        return False

    def _check_auth(self, username: str, password: str) -> bool:
        try:
            token_response = _get_token(username=username, password=password)
        except requests.HTTPError as e:
            if 400 <= e.response.status_code < 500:
                return False
            raise
        if token_response is None:
            return False

        sentry_sdk.set_user({"email": username})
        self.user_id = token_response.user_id
        self.access_token = token_response.access_token
        self._refresh_token = token_response.refresh_token

        self.access_token_updated.emit()
        self._refresh_token_timer.start()

        return True

    def refresh_access_token(self) -> bool:
        if self._refresh_token is None:
            return False
        token_response = _get_token(refresh_token=self._refresh_token, session=None)
        if token_response is None:
            return False

        self.access_token = token_response.access_token
        self._refresh_token = token_response.refresh_token

        self.access_token_updated.emit()
        self._refresh_token_timer.start()

        return True

    def _get_auth_config_id(self) -> str:
        """Get the stored authentication configuration ID from QSettings."""
        return self._qsettings.value(AUTH_CONFIG_ID_KEY, "")

    def _set_auth_config_id(self, authcfg: str) -> None:
        """Store the authentication configuration ID in QSettings."""
        self._qsettings.setValue(AUTH_CONFIG_ID_KEY, authcfg)

    def get_credentials_from_settings(self) -> tuple[Optional[str], Optional[str]]:
        """Get credentials from QSettings if they exist."""
        username = self._qsettings.value("jakartowns/username")
        password = self._qsettings.value("jakartowns/password")
        if isinstance(username, bytes):
            username = username.decode()
        if isinstance(password, bytes):
            password = password.decode()
        if username and password:
            return username, password
        return None, None

    def _set_credentials_in_settings(self, username: str, password: str) -> None:
        """Store credentials in QSettings."""
        self._qsettings.setValue("jakartowns/username", username)
        self._qsettings.setValue("jakartowns/password", password)

    def _is_auth_database_set(self) -> bool:
        """Check if the authentication database is set."""
        auth_mgr = QgsApplication.authManager()
        # check if any master password exists
        if auth_mgr.masterPasswordHashInDatabase():
            # Will fetch the master password from the wallet on linux.
            # This function also pops up a dialog to enter the master password, but it
            # shouldn't because we checked masterPasswordHashInDatabase first.
            auth_mgr.setMasterPassword(verify=False)
            # returns True if the auth config is setup and ready to use
            return auth_mgr.masterPasswordIsSet()
        return False

    def _get_credentials_from_auth_database(
        self,
    ) -> tuple[Optional[str], Optional[str]]:
        """Get credentials from the authentication database."""
        auth_mgr = QgsApplication.authManager()
        if not self._is_auth_database_set():
            return None, None
        authcfg = self._get_auth_config_id()
        if authcfg and authcfg in auth_mgr.configIds():
            config = QgsAuthMethodConfig()
            if auth_mgr.loadAuthenticationConfig(authcfg, config, True):
                if config.isValid():
                    username = config.config("username")
                    password = config.config("password")
                    if isinstance(username, bytes):
                        username = username.decode()
                    if isinstance(password, bytes):
                        password = password.decode()
                    return username, password
        return None, None

    def _set_credentials_in_auth_database(self, username: str, password: str) -> None:
        """Store credentials in the authentication database."""
        auth_mgr = QgsApplication.authManager()
        authcfg = self._get_auth_config_id()
        config = QgsAuthMethodConfig()
        if authcfg:
            config.setId(authcfg)
        config.setName("Jakarto Basic Auth")
        config.setMethod("Basic")
        config.setConfig("username", username)
        config.setConfig("password", password)
        if config.isValid():
            auth_mgr.storeAuthenticationConfig(config, overwrite=True)
            self._set_auth_config_id(config.id())


def _ask_credentials(
    in_qsettings: bool = False,
) -> Union[tuple[str, str], tuple[None, None]]:
    """Ask for credentials and store them in the authentication database."""
    description = "Please enter your credentials to access Jakarto services."
    if in_qsettings:
        description += "\nThe credentials will be stored in clear text on your machine."
        description += "\nSetup the QGIS authentication database for more security."
    else:
        description += (
            "\nThe credentials will be stored in the QGIS authentication database."
        )
    dialog = _make_auth_dialog(
        title="Jakarto Authentication",
        description=description,
    )
    if dialog.exec_() == QDialog.Accepted:
        username = dialog.username_edit.text()
        password = dialog.password_edit.text()
        return username, password
    return None, None


class _AuthDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)


def _make_auth_dialog(
    title: str,
    description: str,
    username_label: str = "Email:",
    password_label: str = "Password:",
) -> _AuthDialog:
    # Show dialog to get new credentials

    dialog = _AuthDialog()
    dialog.setWindowTitle(title)
    layout = QVBoxLayout()

    username_label = QLabel(username_label)
    password_label = QLabel(password_label)

    button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    description_label = QLabel(description)

    layout.addWidget(description_label)
    layout.addWidget(username_label)
    layout.addWidget(dialog.username_edit)
    layout.addWidget(password_label)
    layout.addWidget(dialog.password_edit)
    layout.addWidget(button_box)

    dialog.setLayout(layout)

    return dialog


@dataclass
class _TokenResponse:
    user_id: str
    access_token: str
    refresh_token: str
    token_expires_at_timestamp: int


def _get_token(
    *_,
    username: Optional[str] = None,
    password: Optional[str] = None,
    refresh_token: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Optional[_TokenResponse]:
    if (username is None or password is None) and not refresh_token:
        raise ValueError("Either username and password or refresh token is required")
    if not refresh_token:
        json_data = {"email": username, "password": password}
        params = {"grant_type": "password"}
    else:
        json_data = {"refresh_token": refresh_token}
        params = {"grant_type": "refresh_token"}

    max_retries = 3
    retry_delay = 0.25  # seconds
    last_exception = None

    if session is None:
        session = requests.Session()

    for attempt in range(max_retries):
        try:
            response = session.post(
                auth_url,
                json=json_data,
                params=params,
                headers={"apiKey": anon_key},
                verify=verify_ssl,
            )
            response.raise_for_status()
            data = response.json()
            return _TokenResponse(
                user_id=data["user"]["id"],
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                token_expires_at_timestamp=data["expires_at"],
            )
        except requests.RequestException as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                print(f"Error when getting token: {e.response.text}")
                attempt = max_retries  # don't retry on invalid credentials
            else:
                print(f"Unexpected error when getting token: {e}")
            last_exception = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            raise last_exception
