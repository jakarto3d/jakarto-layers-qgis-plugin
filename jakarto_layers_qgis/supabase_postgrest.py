from __future__ import annotations

from typing import Any

import requests

from .constants import (
    anon_key,
    geometry_types,
    postgrest_url,
)
from .supabase_models import SupabaseFeature, SupabaseLayer
from .supabase_session import SupabaseSession


class Postgrest:
    def __init__(self, session: SupabaseSession) -> None:
        self._session = session

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

    def add_features(self, features: list[SupabaseFeature]) -> None:
        geom_type = set(feature.geometry_type for feature in features)
        if len(geom_type) != 1:
            raise ValueError("All features must have the same geometry type")
        if (geom := geom_type.pop()) != "point":
            raise ValueError("Only point geometry type is supported")

        response = self._request(
            "POST",
            geometry_type=geom,
            json=[f.to_json() for f in features],
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

    def create_layer(self, layer: SupabaseLayer) -> None:
        response = self._request(
            "POST",
            table_name="layers",
            json=layer.to_json(),
        )
        response.raise_for_status()

    def _request(
        self,
        method: str,
        *,
        table_name: str | None = None,
        geometry_type: str | None = None,
        json=None,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        if table_name is None and geometry_type is None:
            raise ValueError("Either table_name or geometry_type must be provided")
        if table_name is None:
            table_name = f"{geometry_type}s"
        response = self._session.request(
            method,
            f"{postgrest_url}/{table_name}",
            params=params,
            json=json,
            headers={
                "Authorization": f"Bearer {self._session.access_token}",
                "apiKey": anon_key,
            },
        )
        return response
