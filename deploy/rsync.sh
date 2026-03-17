#!/usr/bin/env bash
set -euo pipefail
REMOTE="romano@10.0.0.47"
REMOTE_PATH="~/powermeter-active-learner"
rsync -avz \
  --exclude='*.db' \
  --exclude='*.pt' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  . "${REMOTE}:${REMOTE_PATH}/"
echo "Rsync completato → ${REMOTE}:${REMOTE_PATH}"
