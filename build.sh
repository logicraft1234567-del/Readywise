#!/usr/bin/env bash
# Render build step: install packages, collect static files, create/upgrade the PostgreSQL tables.
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py shell -c "from core.services import logic; logic.ensure_seed()"