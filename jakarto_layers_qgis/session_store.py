"""Where the browser sign-in's session cookies are kept between QGIS sessions.

The cookies are a full Jakarto session -- one that has passed two-factor
authentication -- so they go to the QGIS authentication database when it is set
up (encrypted with the master password), and to QSettings in clear text only
otherwise. A session saved in clear text moves to the database as soon as one is
available.

The same keys, and the same file, exist in plugin-qgis: both
plugins share one sign-in, and one sign-out.
"""

from __future__ import annotations

import json

from qgis.core import QgsApplication, QgsAuthMethodConfig
from qgis.PyQt.QtCore import QSettings

# Clear-text fallback, and the id of the authentication database entry.
SETTING = "jakartowns/browser_session"
AUTH_CONFIG_SETTING = "jakartowns/browser_session_authcfg"
_AUTH_CONFIG_NAME = "Jakarto browser session"
_AUTH_CONFIG_KEY = "session"


def _settings() -> QSettings:
    return QSettings("Jakarto", "JakartoPlugin")


def _auth_database_ready() -> bool:
    """Whether the QGIS authentication database can be used without a prompt."""
    auth_manager = QgsApplication.authManager()
    if not auth_manager.masterPasswordHashInDatabase():
        return False
    # Fetches the master password from the system wallet; no dialog, since a
    # master password exists.
    auth_manager.setMasterPassword(verify=False)
    return auth_manager.masterPasswordIsSet()


def load() -> list | None:
    """The saved cookies, or None."""
    settings = _settings()
    auth_config_id = settings.value(AUTH_CONFIG_SETTING)
    if auth_config_id and _auth_database_ready():
        config = QgsAuthMethodConfig()
        if QgsApplication.authManager().loadAuthenticationConfig(
            auth_config_id, config, True
        ):
            return _parse(config.config(_AUTH_CONFIG_KEY))
    cookies = _parse(settings.value(SETTING))
    if cookies and _auth_database_ready():
        save(cookies)  # moves it out of clear text
    return cookies


def save(cookies: list) -> None:
    settings = _settings()
    value = json.dumps(cookies)
    if _auth_database_ready():
        auth_manager = QgsApplication.authManager()
        config = QgsAuthMethodConfig()
        existing = settings.value(AUTH_CONFIG_SETTING)
        if existing and existing in auth_manager.configIds():
            config.setId(existing)
        config.setName(_AUTH_CONFIG_NAME)
        config.setMethod("Basic")
        config.setConfig(_AUTH_CONFIG_KEY, value)
        if config.isValid() and auth_manager.storeAuthenticationConfig(
            config, overwrite=True
        ):
            settings.setValue(AUTH_CONFIG_SETTING, config.id())
            settings.remove(SETTING)
            return
    settings.setValue(SETTING, value)


def clear() -> None:
    settings = _settings()
    auth_config_id = settings.value(AUTH_CONFIG_SETTING)
    if auth_config_id:
        auth_manager = QgsApplication.authManager()
        if auth_config_id in auth_manager.configIds():
            auth_manager.removeAuthenticationConfig(auth_config_id)
        settings.remove(AUTH_CONFIG_SETTING)
    settings.remove(SETTING)


def is_saved() -> bool:
    settings = _settings()
    return bool(settings.value(AUTH_CONFIG_SETTING) or settings.value(SETTING))


def _parse(value) -> list | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    try:
        cookies = json.loads(value)
    except (TypeError, ValueError):
        return None
    return cookies if isinstance(cookies, list) else None
