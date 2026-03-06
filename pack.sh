#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT="${PROJECT_DIR}/../${PROJECT_NAME}_${TIMESTAMP}.tar.gz"

tar -czf "$OUTPUT" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.egg-info' \
    --exclude='.ruff_cache' \
    -C "$(dirname "$PROJECT_DIR")" \
    "$PROJECT_NAME"

echo "Created: $(realpath "$OUTPUT")"
