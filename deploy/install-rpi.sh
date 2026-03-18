#!/usr/bin/env bash
set -euo pipefail
declare -A PKGS=(
  ["spidev"]="spidev"
  ["Pillow"]="PIL"
  ["gpiozero"]="gpiozero"
  ["rpi-lgpio"]="lgpio"
)
for pypi_name in "${!PKGS[@]}"; do
  import_name="${PKGS[$pypi_name]}"
  python3 -c "import ${import_name}" 2>/dev/null \
    && echo "[OK] ${pypi_name}" \
    || { echo "[INSTALL] ${pypi_name}"; pip3 install --break-system-packages "${pypi_name}"; }
done
echo "Installazione completata."
