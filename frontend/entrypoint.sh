#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Cria superusuário se DJANGO_SUPERUSER_EMAIL estiver definido e não existir nenhum superuser
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
import os
email = os.environ['DJANGO_SUPERUSER_EMAIL']
password = os.environ['DJANGO_SUPERUSER_PASSWORD']
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(username=email, email=email, password=password)
    print('Superuser criado: ' + email)
else:
    print('Superuser ja existe, pulando.')
"
fi

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile -
