#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/src/.venv"

python3 -m venv "${VENV_DIR}" --system-site-packages
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install numpy pyyaml

echo "Created ${VENV_DIR}"
echo "Activate with: source ${VENV_DIR}/bin/activate"
