#!/usr/bin/env python3
"""
RANEMAX Device Agent
=====================

Runs ON the Android cloud device (inside Termux) and connects it to your
RANEMAX dashboard via Supabase — no other backend needed.

What it does, every heartbeat:
  1. Logs in to Supabase using the same email/password as your RANEMAX
     dashboard account.
  2. Registers this device in the `devices` table if it doesn't exist yet
     (matched by `device_identifier`), or updates it if it does.
  3. Reports CPU %, RAM %, storage usage, and marks the device "online".
  4. Checks for pending file deployments targeting this device, downloads
     the file from Supabase Storage, and marks the deployment
     success/failed.
  5. Checks for pending tasks targeting this device and executes simple
     ones (currently: "command" tasks run a shell command from the task
     payload — see the security note in README.md before enabling this).

Requirements:
    pip install requests

Configuration:
    Copy config.example.json to config.json and fill it in, or set the
    equivalent environment variables (see README.md).

Run:
    python ranemax_agent.py
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing dependency. Run: pip install -r requirements.txt")
    sys.exit(1)

from security import decrypt_config, prompt_passphrase, harden_permissions

AGENT_VERSION = "v1.0.0"
CONFIG_JSON_PATH = Path(__file__).parent / "config.json"
CONFIG_ENC_PATH = Path(__file__).parent / "config.enc"
STATE_PATH = Path(__file__).parent / ".ranemax_state.json"
DOWNLOAD_DIR = Path(__file__).parent / "deployed_files"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Loads config, preferring the encrypted config.enc over plain
    config.json. Falls back to environment variables for anything missing."""
    config = {}

    if CONFIG_ENC_PATH.exists():
        harden_permissions(CONFIG_ENC_PATH)
        passphrase = prompt_passphrase()
        config = decrypt_config(CONFIG_ENC_PATH.read_bytes(), passphrase)
    elif CONFIG_JSON_PATH.exists():
        harden_permissions(CONFIG_JSON_PATH)
        config = json.loads(CONFIG_JSON_PATH.read_text())
        print(
            "[ranemax-agent] PERINGATAN: config.json belum terenkripsi — "
            "password kamu tersimpan sebagai teks polos di device ini.\n"
            "[ranemax-agent] Jalankan 'python encrypt_config.py' untuk mengamankannya."
        )

    def get(key, env_key, required=True, default=None):
        value = config.get(key) or os.environ.get(env_key) or default
        if required and not value:
            print(f"Missing required config: {key} (or env {env_key})")
            sys.exit(1)
        return value

    return {
        "supabase_url": get("supabase_url", "RANEMAX_SUPABASE_URL").rstrip("/"),
        "supabase_anon_key": get("supabase_anon_key", "RANEMAX_SUPABASE_ANON_KEY"),
        "email": get("email", "RANEMAX_EMAIL"),
        "password": get("password", "RANEMAX_PASSWORD"),
        "device_name": get(
            "device_name", "RANEMAX_DEVICE_NAME", default=get_device_model()
        ),
        "device_identifier": get(
            "device_identifier", "RANEMAX_DEVICE_IDENTIFIER", default=default_identifier()
        ),
        "heartbeat_seconds": int(config.get("heartbeat_seconds", 15)),
        "enable_command_tasks": bool(config.get("enable_command_tasks", False)),
    }


def _getprop(prop: str) -> str:
    try:
        return subprocess.check_output(
            ["getprop", prop], stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
    except Exception:
        return ""


def get_device_model() -> str:
    """Auto-detects a human-readable device name, e.g. 'Samsung SM-A356E'
    or 'Google Pixel 7'. Falls back to a generic name if getprop is
    unavailable (e.g. running outside Termux/Android for testing)."""
    manufacturer = _getprop("ro.product.manufacturer").strip()
    model = _getprop("ro.product.model").strip()

    if model and manufacturer and manufacturer.lower() not in model.lower():
        return f"{manufacturer.title()} {model}"
    if model:
        return model
    return "Android Cloud Device"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "device"


def default_identifier() -> str:
    """Generates and persists a stable, human-readable identifier for this
    device, e.g. 'google-pixel-7-a1b2c3'. Reused across restarts so the
    same physical/cloud device always maps to the same dashboard entry."""
    id_file = Path(__file__).parent / ".device_identifier"
    if id_file.exists():
        return id_file.read_text().strip()
    slug = slugify(get_device_model())
    suffix = get_hwid()[:6]
    new_id = f"{slug}-{suffix}"
    id_file.write_text(new_id)
    return new_id


def get_hwid() -> str:
    """Best-effort stable hardware identifier. Falls back to a persisted UUID
    since Termux cannot read the real Android ID without extra permissions."""
    hwid_file = Path(__file__).parent / ".hwid"
    if hwid_file.exists():
        return hwid_file.read_text().strip()
    try:
        serial = subprocess.check_output(
            ["getprop", "ro.serialno"], stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
        if serial and serial.lower() != "unknown":
            hwid_file.write_text(serial)
            return serial
    except Exception:
        pass
    generated = hashlib.sha1(uuid.uuid4().bytes).hexdigest()[:20]
    hwid_file.write_text(generated)
    return generated


def get_android_version() -> str:
    try:
        version = subprocess.check_output(
            ["getprop", "ro.build.version.release"], stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
        return f"Android {version}" if version else "Android (unknown)"
    except Exception:
        return "Android (unknown)"


# ---------------------------------------------------------------------------
# Supabase REST helpers (no supabase-py dependency needed)
# ---------------------------------------------------------------------------

class Supabase:
    def __init__(self, url: str, anon_key: str):
        self.url = url
        self.anon_key = anon_key
        self.access_token = None
        self.user_id = None

    def sign_in(self, email: str, password: str):
        resp = requests.post(
            f"{self.url}/auth/v1/token?grant_type=password",
            headers={"apikey": self.anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Login failed ({resp.status_code}): {resp.text}")
        data = resp.json()
        self.access_token = data["access_token"]
        self.user_id = data["user"]["id"]

    def _headers(self, extra=None):
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def select(self, table: str, params: dict):
        resp = requests.get(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def insert(self, table: str, row: dict):
        resp = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers({"Prefer": "return=representation"}),
            json=row,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def update(self, table: str, match: dict, row: dict):
        params = {f"{k}": f"eq.{v}" for k, v in match.items()}
        resp = requests.patch(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers({"Prefer": "return=representation"}),
            params=params,
            json=row,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def download_storage_object(self, bucket: str, path: str) -> bytes:
        resp = requests.get(
            f"{self.url}/storage/v1/object/{bucket}/{path}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Local metrics (best-effort; works on most Termux setups)
# ---------------------------------------------------------------------------

_last_cpu_sample = None


def read_cpu_percent() -> int:
    global _last_cpu_sample
    try:
        with open("/proc/stat") as f:
            fields = [int(x) for x in f.readline().split()[1:]]
        idle, total = fields[3], sum(fields)
        if _last_cpu_sample is None:
            _last_cpu_sample = (idle, total)
            time.sleep(0.3)
            with open("/proc/stat") as f:
                fields = [int(x) for x in f.readline().split()[1:]]
            idle, total = fields[3], sum(fields)
        prev_idle, prev_total = _last_cpu_sample
        _last_cpu_sample = (idle, total)
        delta_idle = idle - prev_idle
        delta_total = total - prev_total
        if delta_total <= 0:
            return 0
        usage = 100 * (1 - delta_idle / delta_total)
        return max(0, min(100, round(usage)))
    except Exception:
        return 0


def read_ram_percent() -> int:
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, value = line.split(":")
                info[key.strip()] = int(value.strip().split()[0])
        total = info.get("MemTotal", 1)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        used_percent = 100 * (1 - available / total)
        return max(0, min(100, round(used_percent)))
    except Exception:
        return 0


def read_storage_gb(path: str = "."):
    try:
        stat = os.statvfs(path)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        used_gb = total_gb - free_gb
        return round(used_gb, 1), round(total_gb, 1)
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def ensure_device(sb: Supabase, cfg: dict) -> str:
    """Returns this device's row id, creating the row on first run."""
    existing = sb.select(
        "devices",
        {"device_identifier": f"eq.{cfg['device_identifier']}", "select": "id"},
    )
    storage_used, storage_total = read_storage_gb()

    payload = {
        "device_name": cfg["device_name"],
        "device_identifier": cfg["device_identifier"],
        "hwid": get_hwid(),
        "android_version": get_android_version(),
        "agent_version": AGENT_VERSION,
        "status": "online",
        "cpu_usage": read_cpu_percent(),
        "ram_usage": read_ram_percent(),
        "storage_used": storage_used,
        "storage_total": storage_total,
    }

    if existing:
        device_id = existing[0]["id"]
        sb.update("devices", {"id": device_id}, payload)
        return device_id

    payload["user_id"] = sb.user_id
    created = sb.insert("devices", payload)
    print(f"[ranemax-agent] Registered new device: {cfg['device_identifier']}")
    return created[0]["id"]


def heartbeat(sb: Supabase, device_id: str):
    storage_used, storage_total = read_storage_gb()
    sb.update(
        "devices",
        {"id": device_id},
        {
            "status": "online",
            "cpu_usage": read_cpu_percent(),
            "ram_usage": read_ram_percent(),
            "storage_used": storage_used,
            "storage_total": storage_total,
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        },
    )


def process_deployments(sb: Supabase, device_id: str):
    pending = sb.select(
        "deployments",
        {"device_id": f"eq.{device_id}", "status": "in.(pending,waiting_for_online)"},
    )
    for dep in pending:
        try:
            sb.update("deployments", {"id": dep["id"]}, {"status": "downloading"})
            files = sb.select("files", {"id": f"eq.{dep['file_id']}"})
            if not files:
                sb.update("deployments", {"id": dep["id"]}, {"status": "failed"})
                continue
            file_row = files[0]
            content = sb.download_storage_object("device-files", file_row["storage_path"])
            DOWNLOAD_DIR.mkdir(exist_ok=True)
            (DOWNLOAD_DIR / file_row["filename"]).write_bytes(content)
            sb.update("deployments", {"id": dep["id"]}, {"status": "success"})
            print(f"[ranemax-agent] Deployed file: {file_row['filename']}")
        except Exception as e:
            print(f"[ranemax-agent] Deployment failed: {e}")
            sb.update("deployments", {"id": dep["id"]}, {"status": "failed"})


def process_tasks(sb: Supabase, device_id: str, cfg: dict):
    pending = sb.select("tasks", {"device_id": f"eq.{device_id}", "status": "eq.pending"})
    for task in pending:
        sb.update("tasks", {"id": task["id"]}, {"status": "running"})
        task_type = task.get("task_type")
        payload = task.get("payload") or {}

        try:
            if task_type == "sync":
                # Sync just re-runs a heartbeat + deployment check immediately.
                heartbeat(sb, device_id)
                process_deployments(sb, device_id)
                sb.update("tasks", {"id": task["id"]}, {"status": "success"})

            elif task_type == "command" and cfg["enable_command_tasks"]:
                cmd = payload.get("command", "")
                if not cmd:
                    raise RuntimeError("No command in task payload")
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, timeout=60, text=True
                )
                status = "success" if result.returncode == 0 else "failed"
                sb.update("tasks", {"id": task["id"]}, {"status": status})

            else:
                # Unsupported task type on this simple agent build.
                sb.update("tasks", {"id": task["id"]}, {"status": "failed"})

        except Exception as e:
            print(f"[ranemax-agent] Task failed: {e}")
            sb.update("tasks", {"id": task["id"]}, {"status": "failed"})


def main():
    cfg = load_config()
    sb = Supabase(cfg["supabase_url"], cfg["supabase_anon_key"])

    print("[ranemax-agent] Signing in...")
    sb.sign_in(cfg["email"], cfg["password"])
    print(f"[ranemax-agent] Signed in as {cfg['email']}")

    device_id = ensure_device(sb, cfg)
    print(f"[ranemax-agent] Device ready. Heartbeat every {cfg['heartbeat_seconds']}s.")
    print("[ranemax-agent] Press Ctrl+C to stop.")

    while True:
        try:
            heartbeat(sb, device_id)
            process_deployments(sb, device_id)
            process_tasks(sb, device_id, cfg)
        except requests.exceptions.RequestException as e:
            print(f"[ranemax-agent] Network error, will retry: {e}")
        except Exception as e:
            print(f"[ranemax-agent] Unexpected error: {e}")
        time.sleep(cfg["heartbeat_seconds"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ranemax-agent] Stopped.")
