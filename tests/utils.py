import json
from pathlib import Path
from unittest.mock import Mock

HERE = Path(__file__).parent
RESPONSES_DIR = HERE / "responses"


def get_data_path(filename: str) -> Path:
    return HERE / "data" / filename


def get_data_file(filename: str, as_json: bool = False) -> str:
    text = get_data_path(filename).read_text()
    if as_json:
        return json.loads(text)
    return text


def get_response_file(filename: str) -> dict:
    return json.loads((RESPONSES_DIR / filename).read_text())


def get_response(filename: str) -> Mock:
    data = get_response_file(filename)
    return Mock(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: data,
    )
