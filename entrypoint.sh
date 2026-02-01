#!/bin/bash
set -e

echo "Starting entrypoint script..."

# Initialize DB (if not exists)
echo "Initializing database..."
python3 -c 'import database; database.init_db()'

# Run migrations
echo "Running migrations..."
python3 -m migrations.add_user_system
python3 -m migrations.add_albums
python3 -m migrations.add_nested_albums

# Start Gunicorn
echo "Starting Gunicorn on port 5050..."
exec gunicorn --bind 0.0.0.0:5050 --workers 4 --threads 2 --access-logfile - --error-logfile - app:app
