import os


def log(message: str) -> None:
    if not os.environ.get("JAKARTO_LAYERS_VERBOSE"):
        return
    print(message)
