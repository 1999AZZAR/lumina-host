#!/bin/bash
set -e

# Initialize DB (if not exists)
python3 -c 'import database; database.init_db()'

# Run migrations
echo "Running migrations..."
python3 -m migrations.add_user_system
python3 -m migrations.add_albums
python3 -m migrations.add_nested_albums

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:5050 --workers 4 --threads 2 --access-logfile - --error-logfile - app:app
