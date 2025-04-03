_default:
    @just --list --unsorted

# Recreate the virtual environment (only used by the IDE for development)
[linux]
venv:
    #!/usr/bin/env bash
    if [ -d ".venv" ]; then rm -rf .venv; fi
    /usr/bin/python3 -m venv --system-site-packages .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    .venv/bin/pre-commit install

    echo "Activate the venv with: "
    echo ". .venv/bin/activate"

# Run the tests
test:
    .venv/bin/pytest tests

# Format the code
format:
    .venv/bin/ruff format
    .venv/bin/ruff check --fix
    .venv/bin/pre-commit run --all-files

# Run QGIS with the plugin folder set to the current directory
[linux]
run-qgis:
    JAKARTO_LAYERS_VERBOSE=1 QGIS_PLUGINPATH=$(pwd) qgis &

# Install dependencies in the `jakarto_layers_qgis_plugin/vendor` folder
vendorize:
    . .venv/bin/activate \
    && pip install --platform none --upgrade --no-deps --target jakarto_layers_qgis/vendor -r requirements-vendor.txt \
    && rm -rf jakarto_layers_qgis/vendor/*.dist-info

# Compile the resources.qrc file (only necessary when it changed)
compile:
    pyrcc5 jakarto_layers_qgis/ui/resources.qrc -o jakarto_layers_qgis/ui/resources_rc.py
