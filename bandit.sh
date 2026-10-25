#!/bin/bash
# Security linter
cd "$(dirname "$0")" || exit 1
[ -f venv/bin/activate ] && . venv/bin/activate
bandit -q -r lhaskell -x lhaskell/judge/tests
