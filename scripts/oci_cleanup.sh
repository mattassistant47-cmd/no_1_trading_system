#!/bin/bash
set -euo pipefail
echo "=== OCI Cleanup ==="
docker ps -q 2>/dev/null | xargs -r docker stop || true
docker ps -aq 2>/dev/null | xargs -r docker rm -f || true
docker images -q 2>/dev/null | xargs -r docker rmi -f || true
docker volume prune -f || true
docker network prune -f || true
sudo find /home/ubuntu -name "*.log" -mtime +7 -delete 2>/dev/null || true
echo "=== Disk space ==="
df -h /
echo "=== Cleanup complete ==="
