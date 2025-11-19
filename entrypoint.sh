#!/bin/bash
set -e
echo "Entrypoint script started..."
export FLASK_APP=run.py
echo "Running database migrations..."
flask db upgrade

echo "Database migrations complete."
echo "Starting Gunicorn server..."
exec "$@"