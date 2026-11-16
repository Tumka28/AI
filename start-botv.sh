#!/usr/bin/env sh
# Bot V: one command starts the model server, Bot V, OpenJarvis and the browser.
# The first run creates the Python environment and installs everything.
main() {
    cd "$(dirname "$0")" || exit 1
    if [ ! -x .venv/bin/python ]; then
        PY=$(command -v python3.13 || command -v python3.12 || command -v python3)
        if [ -z "$PY" ]; then
            echo "[!!] Python 3.10-3.13 was not found."
            exit 1
        fi
        echo "[..] First run: creating the Python environment with $PY"
        "$PY" -m venv .venv || exit 1
        .venv/bin/python -m pip install --upgrade pip || exit 1
        .venv/bin/python -m pip install -r requirements-dev.txt -r requirements-openjarvis.txt || exit 1
    fi
    # exec: the shell does not read this file again (an update may replace it).
    exec .venv/bin/python -m bot_v.launch "$@"
}
main "$@"
