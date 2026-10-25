#!/bin/bash
# Tests with coverage (it must be 100%). The executor is simulated: only PostgreSQL is needed.
. "$(dirname "$0")/config.sh"
cd lhaskell || exit 1
coverage erase
coverage run manage.py test judge "$@" || exit 1
coverage report -m --fail-under=100
