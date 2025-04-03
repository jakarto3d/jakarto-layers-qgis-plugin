import json
from pathlib import Path
from unittest.mock import Mock

HERE = Path(__file__).parent
RESPONSES_DIR = HERE / "responses"


def get_response(filename: str) -> Mock:
    data = json.loads((RESPONSES_DIR / filename).read_text())
    return Mock(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: data,
    )
