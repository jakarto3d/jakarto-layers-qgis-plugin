from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .supabase_feature import SupabaseFeature


def parse_message(
    message: dict,
) -> InsertMessage | UpdateMessage | DeleteMessage | None:
    type_ = message.get("data", {}).get("type")
    if type_ == "INSERT":
        return InsertMessage.from_json(message)
    elif type_ == "UPDATE":
        return UpdateMessage.from_json(message)
    elif type_ == "DELETE":
        return DeleteMessage.from_json(message)
    return None


@dataclass
class InsertMessage:
    table: str
    type: Literal["INSERT"]
    record: SupabaseFeature
    columns: list[dict[str, str]]
    errors: dict | None
    schema: str
    commit_timestamp: str

    @classmethod
    def from_json(cls, json_data: dict) -> InsertMessage:
        json_data = json_data["data"]
        if json_data["type"] != "INSERT":
            raise ValueError(f"Expected INSERT, got {json_data['type']}")
        return cls(
            table=json_data["table"],
            type=json_data["type"],
            record=SupabaseFeature.from_json(json_data["record"]),
            columns=json_data["columns"],
            errors=json_data["errors"],
            schema=json_data["schema"],
            commit_timestamp=json_data["commit_timestamp"],
        )


@dataclass
class UpdateMessage:
    table: str
    type: Literal["UPDATE"]
    record: SupabaseFeature
    columns: list[dict[str, str]]
    errors: dict | None
    schema: str
    commit_timestamp: str
    old_record: dict | None

    @classmethod
    def from_json(cls, json_data: dict) -> UpdateMessage:
        json_data = json_data["data"]
        if json_data["type"] != "UPDATE":
            raise ValueError(f"Expected UPDATE, got {json_data['type']}")
        return cls(
            table=json_data["table"],
            type=json_data["type"],
            record=SupabaseFeature.from_json(json_data["record"]),
            columns=json_data["columns"],
            errors=json_data["errors"],
            schema=json_data["schema"],
            commit_timestamp=json_data["commit_timestamp"],
            old_record=json_data["old_record"],
        )


@dataclass
class DeleteMessage:
    table: str
    type: Literal["DELETE"]
    columns: list[dict[str, str]]
    errors: dict | None
    schema: str
    commit_timestamp: str
    old_record_id: str

    @classmethod
    def from_json(cls, json_data: dict) -> DeleteMessage:
        json_data = json_data["data"]
        if json_data["type"] != "DELETE":
            raise ValueError(f"Expected DELETE, got {json_data['type']}")
        return cls(
            table=json_data["table"],
            type=json_data["type"],
            columns=json_data["columns"],
            errors=json_data["errors"],
            schema=json_data["schema"],
            commit_timestamp=json_data["commit_timestamp"],
            old_record_id=json_data["old_record"]["id"],
        )
