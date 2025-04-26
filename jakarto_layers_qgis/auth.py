from typing import Callable

from qgis.core import Qgis, QgsApplication, QgsAuthMethodConfig, QgsMessageLog
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

AUTH_CONFIG_ID_KEY = "jakarto_auth_config_id"


def _log(message: str) -> None:
    QgsMessageLog.logMessage(message, "Jakarto Layers", Qgis.MessageLevel.Info)


def setup_auth(check_function: Callable[[str, str], bool]) -> bool:
    """Setup authentication for the plugin.

    If the authentication database is set, it will store the credentials in the
    authentication database.

    If the authentication database is not set, it will store the credentials in
    the settings ().
    """

    if _is_auth_database_set():
        # store credentials in auth database
        username, password = _get_credentials_from_auth_database()
        if username and password and check_function(username, password):
            _log(f"Using credentials from auth database: {username}")
            return True
        # check in settings, if we have credentials there, store them in auth database
        username, password = get_credentials_from_settings()
        if username and password and check_function(username, password):
            _set_credentials_in_auth_database(username, password)
            _log(f"Stored credentials from settings in auth database: {username}")
            return True
        while True:
            username, password = _ask_credentials(in_qsettings=False)
            if username is None or password is None:
                break
            if check_function(username, password):
                _set_credentials_in_auth_database(username, password)
                _log(f"Stored credentials in auth database: {username}")
                return True
            _log(f"Invalid credentials for username: {username}")
    else:
        # legacy way, store credentials in settings
        username, password = get_credentials_from_settings()
        if username and password and check_function(username, password):
            _log(f"Using credentials from settings: {username}")
            return True
        while True:
            username, password = _ask_credentials(in_qsettings=True)
            if username is None or password is None:
                break
            if check_function(username, password):
                _set_credentials_in_settings(username, password)
                _log(f"Stored credentials in settings: {username}")
                return True
            _log(f"Invalid credentials for username: {username}")

    return False


def _ask_credentials(in_qsettings: bool = False) -> tuple[str | None, str | None]:
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


def _get_auth_config_id() -> str:
    """Get the stored authentication configuration ID from QSettings."""
    settings = QSettings("Jakarto", "JakartoPlugin")
    return settings.value(AUTH_CONFIG_ID_KEY, "")


def _set_auth_config_id(authcfg: str) -> None:
    """Store the authentication configuration ID in QSettings."""
    settings = QSettings("Jakarto", "JakartoPlugin")
    settings.setValue(AUTH_CONFIG_ID_KEY, authcfg)


def get_credentials_from_settings() -> tuple[str | None, str | None]:
    """Get credentials from QSettings if they exist."""
    settings = QSettings("Jakarto", "JakartoPlugin")
    username = settings.value("jakartowns/username")
    password = settings.value("jakartowns/password")
    if isinstance(username, bytes):
        username = username.decode()
    if isinstance(password, bytes):
        password = password.decode()
    if username and password:
        return username, password
    return None, None


def _set_credentials_in_settings(username: str, password: str) -> None:
    """Store credentials in QSettings."""
    settings = QSettings("Jakarto", "JakartoPlugin")
    settings.setValue("jakartowns/username", username)
    settings.setValue("jakartowns/password", password)


def _is_auth_database_set() -> bool:
    """Check if the authentication database is set."""
    auth_mgr = QgsApplication.authManager()
    # check if any master password exists
    if auth_mgr.masterPasswordHashInDatabase():
        # will fetch the master password from the wallet on linux
        # will also pop up a dialog to enter the master password, but it
        # shouldn't because we checked masterPasswordHashInDatabase first
        auth_mgr.setMasterPassword(verify=False)
        # returns True if the auth config is setup and ready to use
        return auth_mgr.masterPasswordIsSet()
    return False


def _get_credentials_from_auth_database() -> tuple[str | None, str | None]:
    """Get credentials from the authentication database."""
    auth_mgr = QgsApplication.authManager()
    if not _is_auth_database_set():
        return None, None
    authcfg = _get_auth_config_id()
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


def _set_credentials_in_auth_database(username: str, password: str) -> None:
    """Store credentials in the authentication database."""
    auth_mgr = QgsApplication.authManager()
    authcfg = _get_auth_config_id()
    config = QgsAuthMethodConfig()
    if authcfg:
        config.setId(authcfg)
    config.setName("Jakarto Basic Auth")
    config.setMethod("Basic")
    config.setConfig("username", username)
    config.setConfig("password", password)
    if config.isValid():
        auth_mgr.storeAuthenticationConfig(config, overwrite=True)
        _set_auth_config_id(config.id())


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
