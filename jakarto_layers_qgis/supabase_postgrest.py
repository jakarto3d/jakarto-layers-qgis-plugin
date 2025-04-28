from __future__ import annotations

from queue import Queue
from typing import Any, Callable, overload

import requests
from qgis.core import QgsApplication, QgsTask

from .constants import (
    anon_key,
    geometry_types,
    postgrest_url,
    verify_ssl,
)
from .supabase_models import LayerAttribute, SupabaseFeature, SupabaseLayer
from .supabase_session import SupabaseSession

DEFAULT_TIMEOUT = 5


class Postgrest:
    def __init__(self, session: SupabaseSession) -> None:
        self._session = session
        self._tasks = Queue(maxsize=100)

    def get_layers(self) -> list[SupabaseLayer]:
        response = self._request("GET", table_name="layers")
        response.raise_for_status()  # type: ignore
        layers = [
            SupabaseLayer(
                name=layer["name"],
                id=layer["id"],
                geometry_type=layer["geometry_type"],
                srid=layer["srid"],
                attributes=[
                    LayerAttribute.from_json(a) for a in (layer["attributes"] or [])
                ],
                parent_id=layer["parent_id"],
            )
            for layer in response.json()
        ]
        return sorted(layers, key=lambda x: x.name)

    def get_features(
        self,
        geometry_type: str,
        layer_id: str,
        callback: Callable[[list[SupabaseFeature]], Any],
    ) -> None:
        if geometry_type not in geometry_types:
            raise ValueError(f"Invalid geometry type: {geometry_type}")

        def _sub_callback(result: list) -> None:
            features = [SupabaseFeature.from_json(feature) for feature in result]
            callback(features)

        self._request(
            "GET",
            geometry_type=geometry_type,
            params={"layer_id": f"eq.{layer_id}"},
            callback=_sub_callback,
            timeout=30,
        )

    def add_feature(self, feature: SupabaseFeature) -> None:
        self._request(
            "POST",
            geometry_type=feature.geometry_type,
            json=feature.to_json(),
        )

    def add_features(self, features: list[SupabaseFeature]) -> None:
        geom_type = set(feature.geometry_type for feature in features)
        if len(geom_type) != 1:
            raise ValueError("All features must have the same geometry type")
        if (geom := geom_type.pop()) != "point":
            raise ValueError("Only point geometry type is supported")

        self._request(
            "POST",
            geometry_type=geom,
            json=[f.to_json() for f in features],
            timeout=30,
        )

    def remove_feature(self, supabase_feature_id: str) -> None:
        self._request(
            "DELETE",
            geometry_type="point",  # to select the table
            params={"id": f"eq.{supabase_feature_id}"},
        )

    def update_feature(self, feature: SupabaseFeature) -> None:
        if not feature.id:
            raise ValueError("Feature has no source ID")
        self._request(
            "PATCH",
            geometry_type=feature.geometry_type,
            json=feature.to_json(),
            params={"id": f"eq.{feature.id}"},
        )

    def update_attributes(self, layer_id: str, attributes: list[dict]) -> None:
        self._request(
            "PATCH",
            table_name="layers",
            params={"id": f"eq.{layer_id}"},
            json={"attributes": attributes},
        )

    def create_layer(self, layer: SupabaseLayer) -> None:
        self._request(
            "POST",
            table_name="layers",
            json=layer.to_json(),
        )

    def drop_layer(self, layer_id: str) -> None:
        self._request(
            "DELETE",
            table_name="layers",
            params={"id": f"eq.{layer_id}"},
        )

    def merge_sub_layer(self, layer_id: str) -> None:
        self._request(
            "POST",
            rpc="merge_sub_layer",
            json={"sub_layer_id": layer_id},
        )

    def rename_layer(self, layer_id: str, new_name: str) -> None:
        self._request(
            "PATCH",
            table_name="layers",
            params={"id": f"eq.{layer_id}"},
            json={"name": new_name},
        )

    @overload
    def _request(
        self,
        method: str,
        *,
        callback: None = None,
        rpc: str | None = None,
        table_name: str | None = None,
        geometry_type: str | None = None,
        json=None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> requests.Response: ...

    @overload
    def _request(
        self,
        method: str,
        *,
        callback: Callable,
        rpc: str | None = None,
        table_name: str | None = None,
        geometry_type: str | None = None,
        json=None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None: ...

    def _request(
        self,
        method: str,
        *,
        callback: Callable | None = None,
        rpc: str | None = None,
        table_name: str | None = None,
        geometry_type: str | None = None,
        json=None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> requests.Response | None:
        if table_name is None and geometry_type is None and not rpc:
            raise ValueError("Either table_name or geometry_type must be provided")
        if table_name is None:
            table_name = f"{geometry_type}s"

        if not rpc:
            url = f"{postgrest_url}/{table_name}"
        else:
            url = f"{postgrest_url}/rpc/{rpc}"
        kwargs = {
            "method": method,
            "url": url,
            "params": params,
            "json": json,
            "headers": {
                "Authorization": f"Bearer {self._session.access_token}",
                "apiKey": anon_key,
            },
            "timeout": timeout,
            "verify": verify_ssl,
        }
        if callback is None:
            response = self._session.request(**kwargs)
            _raise_for_status(response)
            return response

        task = _WebRequestTask(
            description=f"Fetching features from {table_name}",
            args=kwargs,
            raise_for_status=_raise_for_status,
            callback=callback,
        )
        self._queue_task(task)
        return None

    def _queue_task(self, task: QgsTask) -> None:
        self._tasks.put(task)
        QgsApplication.taskManager().addTask(task)


class _WebRequestTask(QgsTask):
    def __init__(
        self,
        description: str,
        args: dict[str, Any],
        raise_for_status: Callable[[requests.Response], None],
        callback: Callable,
    ):
        super().__init__(description, QgsTask.Flag.CanCancel)
        self.args = args
        self.response = None
        self.raise_for_status = raise_for_status
        self.callback = callback
        self._result = None

    def run(self):
        response = requests.request(**self.args)
        self.raise_for_status(response)
        self._result = response.json()
        return True

    def finished(self, result: bool):
        if result and self._result is not None:
            self.callback(self._result)


def _raise_for_status(response: requests.Response) -> None:
    """
    Raise an HTTPError if the response is not OK.
    If the response is JSON, extract the error message.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        error = e.response.text
        content_type = e.response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                error = e.response.json()["message"]
            except Exception:
                pass
        raise requests.HTTPError(f"({e.response.status_code}) {error}")
