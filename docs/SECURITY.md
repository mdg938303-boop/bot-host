# Security checklist before production

- Create a dedicated non-root Linux user for the manager.
- Restrict the Telegram manager to a numeric admin ID.
- Never commit tokens. Store manager secrets in a root-readable environment file.
- Treat uploaded Python code as arbitrary code: it can read manager-accessible files and make network connections.
- For stronger isolation, use containers or systemd sandboxing per bot with CPU/memory/process limits.
- Add process supervision using systemd/cgroups; the current MVP records a PID and is not robust against PID reuse or manager crashes.
- Add zip expansion total-size/file-count limits and review archive contents before extracting.
- Add dependency installation allowlists or require admin confirmation before installing packages.
- Back up bot files and state before editing; current editor makes `.bak` backups.
