#!/bin/bash
set -euo pipefail
export PYTHONPATH=/app
export E2E=1
export API_BASE_URL="${API_BASE_URL:-http://localhost:8001}"
export MODE=paper
export ENVIRONMENT=testing
export LOG_LEVEL=WARNING

echo "=== Running E2E Tests against $API_BASE_URL ==="
python -m pytest tests/e2e/ -v --tb=short -m e2e 2>&1 | tee /app/test-reports/e2e_output.txt
EXIT_CODE=${PIPESTATUS[0]}
tail -20 /app/test-reports/e2e_output.txt
exit $EXIT_CODE
