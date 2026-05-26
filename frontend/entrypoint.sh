#!/bin/sh
set -ex

echo "=== SOLVE STARTUP ==="
echo "PORT=${PORT:-8000}"
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo YES || echo NO)"
echo "RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-not-set}"

echo "--- migrate ---"
python manage.py migrate --noinput

echo "--- collectstatic ---"
python manage.py collectstatic --noinput --clear

echo "--- startup checks ---"
python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django; django.setup()
from apps.dashboard import views, achievements, context_processors
print('imports OK')
"

echo "--- starting gunicorn ---"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --timeout 120 \
    --preload \
    --access-logfile - \
    --error-logfile -
