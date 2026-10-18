import os
import re
import sys
import json
import shutil
import signal
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone

BOT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,48}$")

class BotManager:
    def __init__(self, base: Path, data: Path):
        self.base = base.resolve()
        self.data = data.resolve()
        self.bots_dir = self.base / "bots"
        self.logs_dir = self.base / "logs"
        self.state_dir = self.data / "state"
        for p in (self.bots_dir, self.logs_dir, self.state_dir):
            p.mkdir(parents=True, exist_ok=True)

    def _id(self, bot_id):
        bot_id = str(bot_id).strip()
        if not BOT_ID_RE.fullmatch(bot_id):
            raise ValueError("Invalid Bot ID.")
        return bot_id

    def _dir(self, bot_id):
        return self.bots_dir / self._id(bot_id)

    def _state(self, bot_id):
        p = self.state_dir / f"{self._id(bot_id)}.json"
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        return {}

    def _save_state(self, bot_id, **kwargs):
        p = self.state_dir / f"{self._id(bot_id)}.json"
        state = self._state(bot_id)
        state.update(kwargs)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps(state, indent=2))
        p.chmod(0o600)

    def _pid(self, bot_id):
        return self._state(bot_id).get("pid")

    def _alive(self, pid):
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def bot_exists(self, bot_id):
        try:
            return self._dir(bot_id).is_dir()
        except ValueError:
            return False

    def add_upload(self, source: Path, filename: str):
        if filename.endswith(".py"):
            bot_id = self._unique_id(Path(filename).stem)
            target = self._dir(bot_id)
            target.mkdir(mode=0o750)
            shutil.copy2(source, target / "main.py")
        elif filename.endswith(".zip"):
            bot_id = self._unique_id(Path(filename).stem)
            target = self._dir(bot_id)
            target.mkdir(mode=0o750)
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    name = Path(info.filename)
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError("ZIP contains an unsafe path.")
                    if info.file_size > 20 * 1024 * 1024:
                        raise ValueError("ZIP contains a file over 20 MB.")
                    out = (target / name).resolve()
                    if target.resolve() not in out.parents and out != target.resolve():
                        raise ValueError("Unsafe ZIP path.")
                zf.extractall(target)
            # If a single enclosing directory exists, flatten it.
            children = list(target.iterdir())
            if len(children) == 1 and children[0].is_dir():
                inner = children[0]
                for item in list(inner.iterdir()):
                    shutil.move(str(item), target / item.name)
                inner.rmdir()
        else:
            raise ValueError("Only .py and .zip uploads are supported.")
        entry = self._find_entry(target)
        if not entry:
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError("ZIP must contain main.py or bot.py.")
        req = target / "requirements.txt"
        if req.exists():
            # Requirements are user code; this MVP installs them only on explicit upload.
            venv = target / "venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=60)
            subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "-r", str(req)],
                           check=True, timeout=180, capture_output=True, text=True)
        self._save_state(bot_id, entry=entry.relative_to(target).as_posix(), created_at=datetime.now(timezone.utc).isoformat())
        return bot_id, f"Entry: {entry.relative_to(target)}"

    def _unique_id(self, name):
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-_").lower()[:35] or "bot"
        candidate, n = stem, 2
        while (self.bots_dir / candidate).exists():
            candidate = f"{stem}-{n}"
            n += 1
        return candidate

    def _find_entry(self, target):
        for name in ("main.py", "bot.py"):
            p = target / name
            if p.is_file():
                return p
        return None

    def list_bots(self):
        dirs = sorted(p for p in self.bots_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
        if not dirs:
            return "এখনো কোনো বট আপলোড করা হয়নি। 📤 Upload Bot চাপুন।"
        lines = ["🤖 Your Bots"]
        for d in dirs:
            state = self._state(d.name)
            pid = state.get("pid")
            status = "🟢 Running" if pid and self._alive(pid) else "🔴 Stopped"
            lines.append(f"\nID: {d.name}\nStatus: {status}\nEntry: {state.get('entry','main.py')}")
        return "\n".join(lines)

    def start_bot(self, bot_id):
        d = self._dir(bot_id)
        if not d.is_dir():
            raise ValueError("Bot ID পাওয়া যায়নি।")
        state = self._state(bot_id)
        pid = state.get("pid")
        if pid and self._alive(pid):
            return f"ℹ️ {bot_id} ইতিমধ্যে running (PID {pid})."
        entry = state.get("entry", "main.py")
        script = (d / entry).resolve()
        if d.resolve() not in script.parents or not script.is_file():
            raise ValueError("Entry file পাওয়া যায়নি।")
        py = d / "venv" / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable)
        logpath = self.logs_dir / f"{bot_id}.log"
        errpath = self.logs_dir / f"{bot_id}.err"
        out = open(logpath, "ab", buffering=0)
        err = open(errpath, "ab", buffering=0)
        env = os.environ.copy()
        # Per-bot secret env file support: bots/<id>/.env is parsed without shell evaluation.
        envfile = d / ".env"
        if envfile.exists():
            for line in envfile.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k.strip()):
                        env[k.strip()] = v.strip().strip('"').strip("'")
        proc = subprocess.Popen(
            [str(py), "-u", str(script)],
            cwd=str(d), env=env, stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, start_new_session=True,
            close_fds=True,
        )
        out.close(); err.close()
        self._save_state(bot_id, pid=proc.pid, started_at=datetime.now(timezone.utc).isoformat(), last_exit=None)
        return f"▶️ Started {bot_id}\nPID: {proc.pid}\nLog: logs/{bot_id}.log"

    def stop_bot(self, bot_id):
        pid = self._pid(bot_id)
        if not pid or not self._alive(pid):
            self._save_state(bot_id, pid=None, last_status="stopped")
            return f"ℹ️ {bot_id} is not running."
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        self._save_state(bot_id, pid=None, last_status="stopped")
        return f"⏹ Stop signal sent to {bot_id} (PID {pid})."

    def restart_bot(self, bot_id):
        self.stop_bot(bot_id)
        return self.start_bot(bot_id)

    def get_logs(self, bot_id):
        self._id(bot_id)
        p = self.logs_dir / f"{bot_id}.log"
        e = self.logs_dir / f"{bot_id}.err"
        chunks = []
        for f in (p, e):
            if f.exists():
                chunks.append(f"--- {f.name} ---\n" + f.read_text(errors="replace")[-6000:])
        return "\n".join(chunks) or "এখনো কোনো লগ নেই।"

    def get_crashes(self, bot_id):
        self._id(bot_id)
        p = self.logs_dir / f"{bot_id}.err"
        log = p.read_text(errors="replace")[-7000:] if p.exists() else ""
        state = self._state(bot_id)
        if not log.strip():
            return f"🐞 {bot_id}\nError log পাওয়া যায়নি। বটের process exit status এখনও স্বয়ংক্রিয়ভাবে নির্ণয় করা হচ্ছে না। Logs দেখুন।"
        advice = "সম্ভাব্য পরবর্তী পদক্ষেপ: traceback-এর শেষ 10-20 লাইন দেখুন; ModuleNotFoundError হলে requirements.txt পরীক্ষা করুন; SyntaxError হলে উল্লেখিত ফাইল ও লাইন পরীক্ষা করুন; token/API error হলে credentials পরীক্ষা করুন।"
        return f"🐞 Crash / Error Report: {bot_id}\nStarted: {state.get('started_at','unknown')}\n\n{log}\n\n{advice}"

    def prepare_edit(self, bot_id, relpath):
        d = self._dir(bot_id)
        rel = Path(relpath)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError("Invalid relative path.")
        target = (d / rel).resolve()
        if d.resolve() not in target.parents or not target.is_file():
            raise ValueError("ফাইল পাওয়া যায়নি বা path অনিরাপদ।")
        return f"Editing: {rel.as_posix()}\nCurrent size: {target.stat().st_size} bytes\nপরিবর্তিত ফাইলটি Document হিসেবে পাঠান।"

    def apply_edit(self, bot_id, relpath, replacement: Path):
        d = self._dir(bot_id)
        rel = Path(relpath)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError("Invalid relative path.")
        target = (d / rel).resolve()
        if d.resolve() not in target.parents or not target.is_file():
            raise ValueError("ফাইল পাওয়া যায়নি বা path অনিরাপদ।")
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        newdata = replacement.read_bytes()
        if len(newdata) > 2 * 1024 * 1024:
            raise ValueError("File too large.")
        if target.suffix == ".py":
            compile(newdata.decode("utf-8"), str(target), "exec")
        target.write_bytes(newdata)
        return f"✅ Saved {rel.as_posix()}\nBackup: {backup.name}\nPython syntax check passed if this is a .py file.\nপরিবর্তন কার্যকর করতে 🔄 Restart Bot চাপুন।"

    def system_status(self):
        import shutil as sh
        total, used, free = sh.disk_usage(self.base)
        return (
            "📊 System Status\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Managed bots: {sum(1 for p in self.bots_dir.iterdir() if p.is_dir())}\n"
            f"Disk free: {free // (1024**2)} MB\n"
            "Note: process health and memory are best-effort in this MVP."
        )
