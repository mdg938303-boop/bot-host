#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
echo "Install complete."
echo "Set MANAGER_BOT_TOKEN and ADMIN_ID, then run ./venv/bin/python main.py"
