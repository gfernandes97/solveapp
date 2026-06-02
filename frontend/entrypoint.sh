#!/bin/sh
set -ex

echo "=== SOLVE STARTUP PORT=${PORT:-8000} ==="

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Cria superusuário se DJANGO_SUPERUSER_EMAIL estiver definido e não existir ainda
if [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
  python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created')
else:
    print('Superuser already exists')
"
fi

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
