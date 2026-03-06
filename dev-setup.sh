#!/bin/sh
# Generates poetry.lock files for each service using Docker and copies them to the host.
# Run this once after adding or changing dependencies in any pyproject.toml.
set -e

SERVICES="db-service model-service"

for svc in $SERVICES; do
  echo "==> [$svc] Generating poetry.lock..."

  docker run --rm \
    -v "$(pwd)/$svc:/app" \
    -w /app \
    python:3.11-slim \
    sh -c "pip install --quiet poetry && poetry lock"

  echo "==> [$svc] poetry.lock updated."
done

echo ""
echo "All lock files generated. You can now run: docker compose up --build"
