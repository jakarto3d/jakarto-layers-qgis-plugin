from __future__ import annotations

import contextlib
import time

import requests

from .constants import anon_key, auth_url


class SupabaseSession:
    # seconds, should be less than 1 hour (default token expiration time)
    _session_max_age = 5 * 60

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._user_id: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at_timestamp: int | None = None
        self._session: requests.Session | None = None
        self._session_time = time.time()

    def setup_auth(self, email: str, password: str) -> bool:
        try:
            self._get_token(email, password, force_refresh=True)
        except requests.HTTPError as e:
            if 400 <= e.response.status_code < 500:
                return False
            raise
        self._email = email
        self._password = password
        return True

    @property
    def session(self) -> requests.Session:
        session_is_old = time.time() - self._session_time > self._session_max_age
        if session_is_old and self._session:
            with contextlib.suppress(Exception):
                sess = self._session
                self._session = None
                sess.close()
        if self._session is None:
            self._session = requests.Session()
            self._session_time = time.time()
            self._get_token(self._email, self._password)
        return self._session

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        return self.session.request(method, url, **kwargs)

    @property
    def access_token(self) -> str | None:
        self.session  # refresh token if needed
        return self._access_token

    @property
    def user_id(self) -> str:
        self.session  # refresh token if needed
        if not self._user_id:
            raise ValueError("Could not get user ID")
        return self._user_id

    def _get_token(self, email, password, *_, force_refresh: bool = False) -> bool:
        if not self._refresh_token or force_refresh:
            json_data = {"email": email, "password": password}
            params = {"grant_type": "password"}
        else:
            json_data = {"refresh_token": self._refresh_token}
            params = {"grant_type": "refresh_token"}

        max_retries = 3
        retry_delay = 0.25  # seconds
        last_exception = None

        post = (
            self._session.post if self._session and not force_refresh else requests.post
        )

        for attempt in range(max_retries):
            try:
                response = post(
                    auth_url,
                    json=json_data,
                    params=params,
                    headers={"apiKey": anon_key},
                )
                response.raise_for_status()
                data = response.json()
                self._user_id = data["user"]["id"]
                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]
                self._token_expires_at_timestamp = data["expires_at"]
                return True
            except requests.RequestException as e:
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                raise last_exception
        return False  # This line should never be reached due to the raise above, but satisfies the type checker

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
