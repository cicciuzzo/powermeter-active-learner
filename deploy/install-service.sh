#!/usr/bin/env bash
# Install and enable the powermeter systemd service on the RPi.
# Run on the RPi after rsync: bash deploy/install-service.sh
# Automatically uses the current user and home directory.

set -euo pipefail

SERVICE_NAME="powermeter"
SERVICE_TEMPLATE="deploy/powermeter.service"
DEST="/etc/systemd/system/${SERVICE_NAME}.service"

DEPLOY_USER="$(whoami)"
DEPLOY_HOME="$(eval echo ~${DEPLOY_USER})"

echo "Installing ${SERVICE_NAME}.service for user ${DEPLOY_USER} ..."

# Generate service file from template
sed -e "s|DEPLOY_USER|${DEPLOY_USER}|g" \
    -e "s|DEPLOY_HOME|${DEPLOY_HOME}|g" \
    "${SERVICE_TEMPLATE}" | sudo tee "$DEST" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
echo "Done. Check status: sudo systemctl status ${SERVICE_NAME}"
