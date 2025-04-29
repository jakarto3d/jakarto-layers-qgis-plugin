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

    echo "Activate the venv with: "
    echo ". .venv/bin/activate"

# Run the tests
test *args:
    .venv/bin/pytest tests {{ args }}

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

# Install dependencies in the `jakarto_layers_qgis_plugin/vendor` folder
vendorize:
    #!/usr/bin/env bash
    . .venv/bin/activate && vendoring sync

# Compile the resources.qrc file (only necessary when it changed)
compile:
    pyrcc5 jakarto_layers_qgis/ui/resources.qrc -o jakarto_layers_qgis/ui/resources_rc.py
