import contextlib
import time
from typing import Any

import requests

from .constants import geometry_types


class Postgrest:
    auth_url = "http://localhost:8000/auth/v1/token"
    postgrest_url = "http://localhost:3000"
    anon_key = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyAgCiAgICAicm9sZSI6ICJhbm9uIiwKICAgI"
        "CJpc3MiOiAic3VwYWJhc2UtZGVtbyIsCiAgIC"
        "AiaWF0IjogMTY0MTc2OTIwMCwKICAgICJleHA"
        "iOiAxNzk5NTM1NjAwCn0.dc_X5iR_VP_qT0zs"
        "iyj_I_OZ2T9FtRU2BBNWN8Bu4GE"
    )

    _session_max_age = 5 * 60  # seconds

    def __init__(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at_timestamp: int | None = None
        self._session: requests.Session | None = None
        self._session_time = time.time()

    def get_layers(self) -> list[tuple]:
        response = self._get("layers")
        layers = [
            (
                layer["name"],
                layer["id"],
                layer["geometry_type"],
                layer["attributes"],
            )
            for layer in response.json()
        ]
        return sorted(layers, key=lambda x: x[0])

    def get_features(
        self, geometry_type: str, layer_id: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if geometry_type not in geometry_types:
            raise ValueError(f"Invalid geometry type: {geometry_type}")

        if params is None:
            params = {}

        params["layer"] = f"eq.{layer_id}"
        table_name = f"{geometry_type}s"
        response = self._get(table_name, params=params)
        response.raise_for_status()
        return response.json()

    def _get(
        self, table_name: str, params: dict[str, Any] | None = None
    ) -> requests.Response:
        response = self.session.get(
            f"{self.postgrest_url}/{table_name}",
            params=params,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        return response

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
            self._get_token()
        return self._session

    def _get_token(self) -> None:
        if not self._refresh_token:
            json_data = {"email": "someone@jakarto.com", "password": "password"}
            params = {"grant_type": "password"}
        else:
            json_data = {"refresh_token": self._refresh_token}
            params = {"grant_type": "refresh_token"}

        response = self.session.post(
            self.auth_url,
            json=json_data,
            params=params,
            headers={"apiKey": self.anon_key},
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        self._token_expires_at_timestamp = data["expires_at"]

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
