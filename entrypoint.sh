#!/bin/bash
set -e

echo "=== Starting Lumina Host Entrypoint ==="

# Initialize DB (if not exists)
echo "→ Initializing database..."
python3 -c 'import database; database.init_db()' || {
    echo "✗ Database initialization failed"
    exit 1
}
echo "✓ Database initialized"

# Run migrations
echo "→ Running migrations..."
python3 -m migrations.add_user_system || echo "⚠ add_user_system migration skipped/failed"
python3 -m migrations.add_albums || echo "⚠ add_albums migration skipped/failed"
python3 -m migrations.add_nested_albums || echo "⚠ add_nested_albums migration skipped/failed"
echo "✓ Migrations completed"

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
