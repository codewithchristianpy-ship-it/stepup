#!/usr/bin/env bash
set -o errexit

echo "==== DEBUG: DATABASE_URL is set to: ${DATABASE_URL}"

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); import os; email = os.environ.get('DJANGO_SUPERUSER_EMAIL'); password = os.environ.get('DJANGO_SUPERUSER_PASSWORD'); username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'); print('Superuser created.' if email and password and not User.objects.filter(email=email).exists() and User.objects.create_superuser(username=username, email=email, password=password) else 'Superuser already exists or env vars missing.')"