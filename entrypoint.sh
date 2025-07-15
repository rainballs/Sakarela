#!/bin/sh
set -e

echo "Checking environment variables..."
env

echo "Checking file paths..."
ls -l /usr/src/app
ls -l /usr/src/app/Sakarela_DJANGO

echo "Checking Python and Gunicorn..."
python --version
gunicorn --version

echo "Waiting for database..."
./wait-for-it.sh db:5432 --timeout=60 -- echo "Database is up"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
# Run Gunicorn in the foreground without exec to keep container alive
gunicorn Sakarela_DJANGO.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --threads 2 \
    --log-level info \
    --access-logfile - \
    --error-logfile - &
GUNICORN_PID=$!
echo "Gunicorn started with PID $GUNICORN_PID"

# Keep container running
wait $GUNICORN_PID