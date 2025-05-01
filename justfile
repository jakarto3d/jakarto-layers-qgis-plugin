_default:
    @just --list --unsorted

# Recreate the virtual environment (only used by the IDE for development)
[linux]
venv:
    #!/usr/bin/env bash
    if [ -d ".venv" ]; then rm -rf .venv; fi
    uv venv --system-site-packages --python /usr/bin/python3
    uv pip install -r requirements.txt
    uv pip install -r requirements-dev.txt
    .venv/bin/pre-commit install

    echo "Downloading vendor dependencies..."
    just vendorize

    just compile

    echo "Activate the venv with: "
    echo ". .venv/bin/activate"

# Run the tests
test *args:
    .venv/bin/pytest tests {{ args }}

# Run tests for QGIS 3.22 and python 3.9 in a docker container (requires X11)
test-docker:
    docker build -f tests/Dockerfile-3.22-py3.9 -t jakarto-layers-qgis-test-3.22 .
    docker run -it --rm -v $(pwd):/code -v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY=unix$DISPLAY jakarto-layers-qgis-test-3.22

# Run tests with coverage
coverage:
    .venv/bin/coverage run -m pytest tests
    .venv/bin/coverage report
    .venv/bin/coverage html

# Format the code
format:
    .venv/bin/ruff format
    .venv/bin/ruff check --fix
    .venv/bin/pre-commit run --all-files

# Run QGIS with QGIS_PLUGINPATH=$(pwd)
[linux]
run-qgis:
    JAKARTO_LAYERS_VERBOSE=1 QGIS_PLUGINPATH=$(pwd) qgis &

# Run QGIS with QGIS_PLUGINPATH=$(pwd) using a local supabase instance
[linux]
run-qgis-local-supabase:
    JAKARTO_LAYERS_SUPABASE_LOCAL=1 just run-qgis

# Install dependencies in the `jakarto_layers_qgis/vendor` folder
vendorize:
    #!/usr/bin/env bash
    . .venv/bin/activate && vendoring sync
    touch jakarto_layers_qgis/vendor/__init__.py

# Compile the resources.qrc file
compile:
    pyrcc5 jakarto_layers_qgis/ui/resources.qrc -o jakarto_layers_qgis/ui/resources_rc.py

# Package the plugin into a zip file
package:
    #!/usr/bin/env bash
    set -e
    just vendorize
    just compile
    rm -rf jakarto_layers_qgis.zip
    # remove any __pycache__ folders
    find jakarto_layers_qgis -type d -name "__pycache__" -exec rm -rf {} +
    zip -r jakarto_layers_qgis.zip jakarto_layers_qgis
    echo "Package created: jakarto_layers_qgis.zip"
