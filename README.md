# BotHost Manager (MVP)

A personal Telegram-based manager for Python Telegram bots. This is a prototype, not a hardened multi-tenant hosting platform.

## Features
- Admin-ID restricted Telegram manager
- Reply keyboard menu
- Upload `.py` or `.zip` bots
- Start/stop/restart separate processes
- View stdout/stderr logs and basic error reports
- Replace an existing file through Telegram and validate Python syntax
- Optional per-bot `.env` file (never commit secrets)

## Requirements
- Ubuntu Linux
- Python 3.10+
- Git
- A Telegram manager bot token and your Telegram numeric admin ID

## Setup
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
export MANAGER_BOT_TOKEN='YOUR_MANAGER_BOT_TOKEN'
export ADMIN_ID='YOUR_TELEGRAM_NUMERIC_ID'
./venv/bin/python main.py
```

Do not commit real tokens, `.env` files, logs, or user bot code.

## Upload format
- `.py`: uploaded file becomes `main.py`
- `.zip`: must contain `main.py` or `bot.py`, and optionally `requirements.txt`
- If `requirements.txt` is present, the manager creates a per-bot venv and installs dependencies.

## Important security limits
- Run this manager under a dedicated unprivileged Linux account, not root.
- Uploaded code executes as that account and can access its files/network. This MVP is NOT a strong sandbox.
- Do not expose this manager to untrusted users. Use only your own admin ID.
- Resource quotas, robust process supervision, zip-bomb limits, process identity verification, and full crash/exit monitoring should be added before production use.
- A bot process may continue after its manager is closed, but without a systemd service it will not automatically restart after VPS reboot, and crash auto-restart is not yet implemented.
