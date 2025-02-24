_default:
    @just --list --unsorted

[linux]
venv:
    #!/usr/bin/env bash
    if [ -d ".venv" ]; then rm -rf .venv; fi
    /usr/bin/python3 -m venv --system-site-packages .venv
    . .venv/bin/activate
    pip install -r requirements-dev.txt

    echo "Activate the venv with: "
    echo ". .venv/bin/activate"
