from __future__ import annotations

import contextlib
import time
from typing import Any

import requests

from .constants import (
    anon_key,
    auth_url,
    geometry_types,
    postgrest_url,
)
from .supabase_feature import SupabaseFeature


class Postgrest:
    # seconds, should be less than 1 hour (default token expiration time)
    _session_max_age = 5 * 60

    def __init__(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at_timestamp: int | None = None
        self._session: requests.Session | None = None
        self._session_time = time.time()

    def get_layers(self) -> list[tuple]:
        response = self._request("GET", table_name="layers")
        response.raise_for_status()
        layers = [
            (
                layer["name"],
                layer["id"],
                layer["geometry_type"],
                layer["attributes"] or [],
            )
            for layer in response.json()
        ]
        return sorted(layers, key=lambda x: x[0])

    def get_features(
        self, geometry_type: str, layer_id: str, params: dict[str, Any] | None = None
    ) -> list[SupabaseFeature]:
        if geometry_type not in geometry_types:
            raise ValueError(f"Invalid geometry type: {geometry_type}")

        if params is None:
            params = {}

        params["layer"] = f"eq.{layer_id}"
        response = self._request(
            "GET",
            geometry_type=geometry_type,
            params=params,
        )
        response.raise_for_status()
        return [SupabaseFeature.from_json(feature) for feature in response.json()]

    def add_feature(self, feature: SupabaseFeature) -> None:
        response = self._request(
            "POST",
            geometry_type=feature.geometry_type,
            json=feature.to_json(),
        )
        response.raise_for_status()

    def remove_feature(self, supabase_feature_id: str) -> None:
        response = self._request(
            "DELETE",
            geometry_type="point",  # to select the table
            params={"id": f"eq.{supabase_feature_id}"},
        )
        response.raise_for_status()

    def update_feature(self, feature: SupabaseFeature) -> None:
        if not feature.id:
            raise ValueError("Feature has no source ID")
        response = self._request(
            "PATCH",
            geometry_type=feature.geometry_type,
            json=feature.to_json(),
            params={"id": f"eq.{feature.id}"},
        )
        response.raise_for_status()

    def update_attributes(self, layer_id: str, attributes: list[dict]) -> None:
        response = self._request(
            "PATCH",
            table_name="layers",
            params={"id": f"eq.{layer_id}"},
            json={"attributes": attributes},
        )
        response.raise_for_status()

    def _request(
        self,
        method: str,
        *,
        table_name: str | None = None,
        geometry_type: str | None = None,
        json: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        if table_name is None and geometry_type is None:
            raise ValueError("Either table_name or geometry_type must be provided")
        if table_name is None:
            table_name = f"{geometry_type}s"
        response = self.session.request(
            method,
            f"{postgrest_url}/{table_name}",
            params=params,
            json=json,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "apiKey": anon_key,
            },
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
            auth_url,
            json=json_data,
            params=params,
            headers={"apiKey": anon_key},
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
