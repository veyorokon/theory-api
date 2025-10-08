#!/usr/bin/env bash

set -eo pipefail
shopt -s nullglob

if [ $# -eq 0 ]; then
  echo "Collecting static files..."
  python ./manage.py collectstatic --noinput
  echo "Running migrations..."
  python ./manage.py migrate
  echo "Starting gunicorn with uvicorn workers..."
  exec gunicorn backend.asgi:application \
    --bind=0.0.0.0:8000 \
    --workers=${GUNICORN_WORKERS:-3} \
    --worker-class=uvicorn.workers.UvicornWorker \
    --timeout=120
else
  exec "$@"
fi
