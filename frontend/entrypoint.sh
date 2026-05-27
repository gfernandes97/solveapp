#!/bin/sh
set -ex

echo "=== SOLVE STARTUP PORT=${PORT:-8000} ==="

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
