#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Load seed data (skills + lessons) if not already present
python manage.py loaddata fixtures/skills.json || echo "Skills already loaded or loaddata skipped"

# Create superuser if missing
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); import os; email = os.environ.get('DJANGO_SUPERUSER_EMAIL'); password = os.environ.get('DJANGO_SUPERUSER_PASSWORD'); username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'); print('Superuser created.' if email and password and not User.objects.filter(email=email).exists() and User.objects.create_superuser(username=username, email=email, password=password) else 'Superuser already exists or env vars missing.')"