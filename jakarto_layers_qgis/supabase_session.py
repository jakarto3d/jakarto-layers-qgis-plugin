from __future__ import annotations

import contextlib
import time
from typing import Optional

import requests

from .auth import JakartoAuthentication


class SupabaseSession:
    # seconds, should be less than 1 hour (default token expiration time)
    _session_max_age = 5 * 60

    def __init__(self, auth: JakartoAuthentication) -> None:
        self._session: Optional[requests.Session] = None
        self._session_time = time.time()
        self._auth = auth

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

        return self._session

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        return self.session.request(method, url, **kwargs)

    @property
    def access_token(self) -> str:
        self.session  # refresh token if needed
        if not self._auth.access_token:
            raise RuntimeError("Could not get access token")
        return self._auth.access_token

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
