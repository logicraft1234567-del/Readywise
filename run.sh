#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
