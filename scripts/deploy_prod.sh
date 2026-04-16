#!/bin/bash
set -euo pipefail
OCI_HOST="oci"
CODE_DIR="/home/ubuntu/trading-bot/code"
PROD_DIR="/home/ubuntu/trading-bot/prod"

echo "=== PRODUCTION DEPLOYMENT ==="
read -p "Type APPROVED to continue: " CONFIRM
if [ "$CONFIRM" != "APPROVED" ]; then
    echo "Cancelled."
    exit 1
fi

ssh "$OCI_HOST" "cd $CODE_DIR && git pull origin main"
ssh "$OCI_HOST" "cp $CODE_DIR/docker-compose.prod.yml $PROD_DIR/ && cp $CODE_DIR/nginx.prod.conf $PROD_DIR/"
ssh "$OCI_HOST" "cd $PROD_DIR && docker compose -f docker-compose.prod.yml --env-file .env build"
ssh "$OCI_HOST" "cd $PROD_DIR && docker compose -f docker-compose.prod.yml --env-file .env up -d"
ssh "$OCI_HOST" "timeout 120 bash -c 'until curl -sf http://localhost:8000/api/health >/dev/null 2>&1; do sleep 5; done' && echo 'Prod healthy!'" || echo "WARNING: Health check timed out"
ssh "$OCI_HOST" "cd $PROD_DIR && docker compose -f docker-compose.prod.yml ps"
echo "Frontend: http://132.145.202.121"
echo "Backend:  http://132.145.202.121:8000/api/health"
