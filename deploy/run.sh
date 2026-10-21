#!/usr/bin/env bash
# Run one pipeline command from cron: deploy/run.sh <command> [args]
#   * skips the run if the same command is still running (flock)
#   * appends output to logs/<command>.log
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
exec flock --nonblock "/tmp/catalogue-$1.lock" \
    .venv/bin/python -m pipeline "$@" >> "logs/$1.log" 2>&1
