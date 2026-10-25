#!/bin/bash
# Development server at http://localhost:8000/haskell/
. "$(dirname "$0")/config.sh"
cd lhaskell && python manage.py runserver
