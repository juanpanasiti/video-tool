#!/usr/bin/env bash
set -e

# Directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure virtual environment exists with system site packages for GTK/WebKit
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment with system site-packages..."
    uv venv --python 3.12 --system-site-packages .venv
    uv pip install -e .
fi

exec uv run vtool "$@"

