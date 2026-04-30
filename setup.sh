#!/usr/bin/env bash
set -euo pipefail

# Detect Python 3.11+
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(sys.version_info >= (3, 11))')
        if [[ "$version" == "True" ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3.11+ not found." >&2
    exit 1
fi

echo "Using $($PYTHON --version)"

# Create venv
if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
else
    echo "Virtual environment already exists, skipping creation."
fi

# Resolve pip inside the venv
VENV_PYTHON=".venv/bin/python"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    VENV_PYTHON=".venv/Scripts/python"
fi

# Install dependencies
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "Installing with Windows extras..."
    "$VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$VENV_PYTHON" -m pip install --quiet -e ".[windows,dev]"
else
    echo "Installing dev dependencies (Linux/macOS — Windows extras skipped)..."
    "$VENV_PYTHON" -m pip install --quiet --upgrade pip
    "$VENV_PYTHON" -m pip install --quiet -e ".[dev]"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Activate the virtual environment:"
echo "  bash/zsh:  source .venv/bin/activate"
echo "  fish:      source .venv/bin/activate.fish"
echo ""
echo "Then run:"
echo "  python -m pytest tests/ -q   # tests"
echo "  make lint                    # lint"
