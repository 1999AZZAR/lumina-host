#!/bin/bash
set -e

echo "=== Starting Lumina Host Entrypoint ==="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "✗ Python3 not found!"
    exit 1
fi

# Initialize DB (if not exists)
echo "→ Initializing database..."
if ! python3 -c 'import database; database.init_db()' 2>&1; then
    echo "✗ Database initialization failed"
    exit 1
fi
echo "✓ Database initialized"

# Run migrations (non-fatal)
echo "→ Running migrations..."
python3 -m migrations.add_user_system 2>&1 || echo "⚠ add_user_system migration skipped/failed"
python3 -m migrations.add_albums 2>&1 || echo "⚠ add_albums migration skipped/failed"
python3 -m migrations.add_nested_albums 2>&1 || echo "⚠ add_nested_albums migration skipped/failed"
echo "✓ Migrations completed"

# Verify Gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo "✗ Gunicorn not found!"
    exit 1
fi

# Start Gunicorn with improved configuration
echo "→ Starting Gunicorn on 0.0.0.0:5050..."
exec gunicorn \
    --bind 0.0.0.0:5050 \
    --workers 4 \
    --worker-class sync \
    --threads 2 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    app:app
