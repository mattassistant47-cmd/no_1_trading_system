#!/bin/bash
set -euo pipefail
export PYTHONPATH=/app
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export MODE=paper
export ENVIRONMENT=testing
export TESTING=1
export ALPACA_API_KEY_PAPER=test
export ALPACA_API_SECRET_PAPER=test
export FRED_API_KEY=test
export LOG_LEVEL=WARNING

echo "=== Running Unit & Integration Tests ==="
python -m pytest tests/ -m "not e2e" -v --tb=short \
  --cov=. --cov-report=term-missing \
  --junitxml=/app/test-reports/junit.xml 2>&1 | tee /app/test-reports/test_output.txt

EXIT_CODE=${PIPESTATUS[0]}
echo "=== Test Summary ==="
tail -20 /app/test-reports/test_output.txt
exit $EXIT_CODE
