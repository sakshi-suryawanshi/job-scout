#!/usr/bin/env bash
# scripts/run_pipeline.sh
#
# One-shot pipeline runner for cron on the Docker host.
# Run this instead of the long-running scheduler if you use system cron.
#
# Crontab example (7am daily):
#   0 7 * * * /path/to/job_scout/scripts/run_pipeline.sh >> /var/log/job_scout.log 2>&1
#
# Or if running inside the Docker compose stack:
#   0 7 * * * docker compose -f /path/to/docker-compose.yml run --rm pipeline --now

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Job Scout Pipeline — $(date) ==="

cd "$PROJECT_DIR"

# Load .env if present
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

export PYTHONPATH="$PROJECT_DIR"

exec python -m job_scout.pipeline.scheduler --now
