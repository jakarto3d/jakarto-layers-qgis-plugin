from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Union

from .supabase_models import SupabaseFeature


def parse_message(
    message: dict,
) -> Optional[
    Union[SupabaseInsertMessage, SupabaseUpdateMessage, SupabaseDeleteMessage]
]:
    type_ = message.get("data", {}).get("type")
    if type_ == "INSERT":
        return SupabaseInsertMessage.from_json(message)
    elif type_ == "UPDATE":
        return SupabaseUpdateMessage.from_json(message)
    elif type_ == "DELETE":
        return SupabaseDeleteMessage.from_json(message)
    return None


@dataclass
class SupabaseInsertMessage:
    table: str
    type: Literal["INSERT"]
    record: SupabaseFeature
    columns: list[dict[str, str]]
    errors: Optional[dict]
    schema: str
    commit_timestamp: str

    @classmethod
    def from_json(cls, json_data: dict) -> SupabaseInsertMessage:
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
class SupabaseUpdateMessage:
    table: str
    type: Literal["UPDATE"]
    record: SupabaseFeature
    columns: list[dict[str, str]]
    errors: Optional[dict]
    schema: str
    commit_timestamp: str
    old_record: Optional[dict]

    @classmethod
    def from_json(cls, json_data: dict) -> SupabaseUpdateMessage:
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
class SupabaseDeleteMessage:
    table: str
    type: Literal["DELETE"]
    columns: list[dict[str, str]]
    errors: Optional[dict]
    schema: str
    commit_timestamp: str
    old_record_id: str

    @classmethod
    def from_json(cls, json_data: dict) -> SupabaseDeleteMessage:
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
