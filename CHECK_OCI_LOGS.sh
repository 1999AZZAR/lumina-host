#!/bin/bash
# Run this on your OCI instance to diagnose the crash

echo "=== Checking container logs ==="
docker compose logs web --tail=100

echo ""
echo "=== Checking if container can start ==="
docker compose up web --no-deps

# Alternative: inspect the last crash
echo ""
echo "=== Inspecting container ==="
docker inspect lumina-host-web-1 | grep -A 20 "State"
