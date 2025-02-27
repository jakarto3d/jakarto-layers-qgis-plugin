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

    echo "Activate the venv with: "
    echo ". .venv/bin/activate"

# Run QGIS with the plugin folder set to the current directory
[linux]
run-qgis:
    QGIS_PLUGINPATH=$(pwd) qgis &

# Install dependencies in the `jakartowns_qgis_plugin/vendor` folder
vendorize:
    . .venv/bin/activate \
    && pip install --platform none --upgrade --no-deps --target jakartowns_qgis/vendor -r requirements-vendor.txt \
    && rm -rf jakartowns_qgis/vendor/*.dist-info

# Compile the resources.qrc file (only necessary when it changed)
compile:
    pyrcc5 jakartowns_qgis/ui/resources.qrc -o jakartowns_qgis/ui/resources_rc.py
