#!/usr/bin/env bash
# Sync the project to rpi-learner.
# Configure REMOTE in .env or pass as environment variable:
#   REMOTE=user@host bash deploy/rsync.sh
set -euo pipefail

# Read REMOTE from .env if not set
if [ -z "${REMOTE:-}" ] && [ -f .env ]; then
    REMOTE=$(grep -E '^REMOTE=' .env | cut -d= -f2- || true)
fi

if [ -z "${REMOTE:-}" ]; then
    echo "Error: REMOTE not set. Either:"
    echo "  1. Add REMOTE=user@host to .env"
    echo "  2. Run: REMOTE=user@host bash deploy/rsync.sh"
    exit 1
fi

REMOTE_PATH="~/powermeter-active-learner"
rsync -avz \
  --exclude='*.db' \
  --exclude='*.pt' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='watt_history.json' \
  . "${REMOTE}:${REMOTE_PATH}/"
echo "Rsync completato → ${REMOTE}:${REMOTE_PATH}"
