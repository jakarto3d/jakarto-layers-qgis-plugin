from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .postgrest import PostgrestFeature


def parse_message(message: dict) -> UpdateMessage | None:
    type_ = message.get("data", {}).get("type")
    if type_ == "UPDATE":
        return UpdateMessage.from_json(message)
    return None


@dataclass
class UpdateMessage:
    table: str
    type: Literal["UPDATE"]
    record: PostgrestFeature
    columns: list[dict[str, str]]
    errors: dict | None
    schema: str
    old_record: dict | None

    @classmethod
    def from_json(cls, json_data: dict) -> UpdateMessage:
        json_data = json_data["data"]
        if json_data["type"] != "UPDATE":
            raise ValueError(f"Expected UPDATE, got {json_data['type']}")
        return cls(
            table=json_data["table"],
            type=json_data["type"],
            record=PostgrestFeature.from_json(json_data["record"]),
            columns=json_data["columns"],
            errors=json_data["errors"],
            schema=json_data["schema"],
            old_record=json_data["old_record"],
        )
