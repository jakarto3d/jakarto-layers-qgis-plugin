"""Signing in to Jakarto through the browser (RFC 8628, device flow).

The plugin asks account.jakarto.com for a short code, the person approves it in
their browser -- signed in however they normally sign in, with two-factor
authentication or Google -- and the plugin receives the session cookie a browser
would get (Domain .jakarto.com). Supabase access then comes from its `token`
function, which the Jakarto proxy authorizes with that cookie: no password.

The same flow exists in plugin-qgis; both keep the session under the same
QSettings key, so signing in with one plugin signs in the other.

No Qt in here, so it can be tested on its own; the dialog is in
browser_sign_in_dialog.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

# Overridable to test against a local jakaccounts.
ACCOUNT_URL = os.environ.get(
    "JAKARTO_ACCOUNT_URL", "https://account.jakarto.com"
).rstrip("/")
CLIENT_ID = "jakarto-layers-qgis-plugin"

# Shared with plugin-qgis, which uses the same QSettings("Jakarto", "JakartoPlugin").
SESSION_SETTING = "jakartowns/browser_session"

# seconds (connect, read): polled from the QGIS interface thread, keep it short
_REQUEST_TIMEOUT = (5, 5)


class BrowserSignInError(Exception):
    """The sign-in cannot complete: denied, expired, or the server refused."""


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int

    @property
    def display_code(self) -> str:
        """ABCD1234 -> ABCD-1234, as the approval page shows it."""
        code = self.user_code
        return f"{code[:4]}-{code[4:]}" if len(code) == 8 else code


def request_device_code(session: requests.Session) -> DeviceCode:
    response = session.post(
        f"{ACCOUNT_URL}/api/auth/device/code",
        json={"client_id": CLIENT_ID},
        timeout=_REQUEST_TIMEOUT,
    )
    if not response.ok:
        raise BrowserSignInError(_describe_error(response))
    data = response.json()
    return DeviceCode(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        verification_uri_complete=data.get("verification_uri_complete")
        or data["verification_uri"],
        expires_in=int(data["expires_in"]),
        interval=int(data.get("interval", 5)),
    )


PENDING = "pending"
SLOW_DOWN = "slow_down"
APPROVED = "approved"


def poll(session: requests.Session, device_code: DeviceCode) -> str:
    """Ask once whether the code was approved.

    Returns PENDING or SLOW_DOWN while the person has not approved yet (wait
    `interval` seconds, plus 5 more after SLOW_DOWN, before asking again), and
    APPROVED once the session cookie is in `session`. Raises BrowserSignInError
    when it will never be approved.
    """
    response = session.post(
        f"{ACCOUNT_URL}/api/device/token",
        json={"device_code": device_code.device_code, "client_id": CLIENT_ID},
        timeout=_REQUEST_TIMEOUT,
    )
    if response.ok:
        return APPROVED
    error = _error_code(response)
    if error == "authorization_pending":
        return PENDING
    if error == "slow_down":
        return SLOW_DOWN
    raise BrowserSignInError(_describe_error(response))


@dataclass
class SupabaseToken:
    user_id: str
    access_token: str
    expires_at: int


def supabase_token(session: requests.Session, supabase_url: str) -> SupabaseToken:
    """A Supabase access token for the person signed in to `session`.

    It lasts an hour and comes without a refresh token: asking again is the
    refresh. Raises requests.HTTPError when the session is no longer accepted.
    """
    response = session.get(
        f"{supabase_url}/functions/v1/token", timeout=_REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    return SupabaseToken(
        user_id=data["user"]["sub"],
        access_token=data["access_token"],
        expires_at=int(data["expires_at"]),
    )


def sign_out(session: requests.Session) -> None:
    """End the session on the server; failures are ignored, the cookie is dropped anyway."""
    try:
        session.post(f"{ACCOUNT_URL}/users/logout", timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        pass
    session.cookies.clear()


def export_cookies(session: requests.Session) -> list:
    """The cookies to keep between QGIS sessions, as plain data for QSettings."""
    return [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
        for c in session.cookies
    ]


def restore_cookies(session: requests.Session, cookies) -> None:
    """Put saved cookies back, without their client-side expiry: the server
    extends a session while it is used, so it alone says whether it is valid."""
    for c in cookies if isinstance(cookies, list) else []:
        if isinstance(c, dict) and c.get("name") and c.get("value"):
            session.cookies.set(
                c["name"],
                c["value"],
                domain=c.get("domain") or "",
                path=c.get("path") or "/",
            )


_MESSAGES = {
    "expired_token": "The code expired. Start signing in again.",
    "access_denied": "The sign-in was refused.",
    "invalid_grant": "The code is no longer valid. Start signing in again.",
    "invalid_client": "This version of the plugin is not allowed to sign in.",
}


def _error_code(response: requests.Response) -> str | None:
    try:
        return response.json().get("error")
    except ValueError:
        return None


def _describe_error(response: requests.Response) -> str:
    error = _error_code(response)
    if error in _MESSAGES:
        return _MESSAGES[error]
    return f"Unexpected answer from Jakarto ({response.status_code})."
