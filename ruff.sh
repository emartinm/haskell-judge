#!/bin/bash
# Lint and format check (the CI gate)
cd "$(dirname "$0")" || exit 1
[ -f venv/bin/activate ] && . venv/bin/activate
ruff check . && ruff format --check .
