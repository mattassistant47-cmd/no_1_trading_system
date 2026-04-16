#!/bin/bash
set -euo pipefail
OCI_HOST="oci"
CODE_DIR="/home/ubuntu/trading-bot/code"
DEV_DIR="/home/ubuntu/trading-bot/dev"

echo "=== Pushing to GitHub ==="
git push origin main 2>/dev/null || echo "Push skipped"

echo "=== Pulling on OCI ==="
ssh "$OCI_HOST" "cd $CODE_DIR && git pull origin main"

echo "=== Copying configs ==="
ssh "$OCI_HOST" "cp $CODE_DIR/docker-compose.dev.yml $DEV_DIR/ && cp $CODE_DIR/nginx.dev.conf $DEV_DIR/"

echo "=== Building dev stack ==="
ssh "$OCI_HOST" "cd $DEV_DIR && docker compose -f docker-compose.dev.yml --env-file .env build"

echo "=== Starting services ==="
ssh "$OCI_HOST" "cd $DEV_DIR && docker compose -f docker-compose.dev.yml --env-file .env up -d db backend frontend"

echo "=== Waiting for health ==="
ssh "$OCI_HOST" "timeout 90 bash -c 'until curl -sf http://localhost:8001/api/health >/dev/null 2>&1; do sleep 3; done' && echo 'Backend healthy!'" || echo "WARNING: Health check timed out"

echo "=== Status ==="
ssh "$OCI_HOST" "cd $DEV_DIR && docker compose -f docker-compose.dev.yml ps"
echo "Frontend: http://132.145.202.121:8080"
echo "Backend:  http://132.145.202.121:8001/api/health"
