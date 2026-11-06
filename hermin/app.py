#!/usr/bin/env python3
"""Loopback-only control panel for native Hermes and 9Router services."""
from __future__ import annotations

import json
import base64
import binascii
import errno
import hmac
import hashlib
import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from opencode_web import web_state as opencode_web_state, control as opencode_web_control
from privacy_policy import native_config, policy_present, with_policy
from skill_manager import SkillManager
from settings import ROOT, STATE, ADMIN_USER
from updates import check_update

HERE = Path(__file__).resolve().parent
SERVICE_UNITS = {
    "hermes": Path.home() / ".config/systemd/user/hermes-gateway.service",
    "dashboard": Path.home() / ".config/systemd/user/hermes-dashboard.service",
    "router": Path.home() / ".config/systemd/user/9router.service",
}
ENV_FILE = ROOT / "hermes" / "data" / ".env"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
CONFIG = ROOT / "hermes" / "data" / "config.yaml"
DATA = ROOT / "hermes" / "data"
SESSIONS_DB = DATA / "state.db"
SECURITY_DIR = ROOT / "hermes" / "security"
ADMIN_TOKEN_FILE = SECURITY_DIR / "hermin-admin-token"
TEXT_FILES = {
    "soul": DATA / "SOUL.md",
    "memory": DATA / "memories" / "MEMORY.md",
    "user_memory": DATA / "memories" / "USER.md",
}
PORT = int(os.environ.get("HERMES_PANEL_PORT", "1515"))
ROUTER_USAGE_DB = Path(os.environ.get("NINE_ROUTER_USAGE_DB", str(ROOT / "9router" / "data" / "db" / "data.sqlite")))
NOUS_CACHE = STATE / "nous_catalog_cache.json"
ROUTER_CATALOG_CACHE = STATE / "router_catalog_cache.json"
NOUS_RECOMMENDATIONS = DATA / "cache" / "nous_recommended_cache.json"
NOUS_METADATA = DATA / "cache" / "endpoint_model_metadata.json"
CSRF = secrets.token_urlsafe(32)
SKILLS = SkillManager(ROOT)


def admin_token() -> str:
    SECURITY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECURITY_DIR, 0o700)
    try:
        fd = os.open(ADMIN_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(secrets.token_urlsafe(48) + "\n")
    info = ADMIN_TOKEN_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Token admin HERMIN harus file biasa milik user ini.")
    os.chmod(ADMIN_TOKEN_FILE, 0o600)
    token = ADMIN_TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 48:
        raise RuntimeError("Token admin HERMIN tidak valid; dashboard ditahan.")
    return token


ADMIN_TOKEN = admin_token()
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_env(contents: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            result[key] = value.strip().strip('"').strip("'")
    return result


def set_env_value(contents: str, key: str, value: str) -> str:
    """Replace one .env entry without exposing or changing unrelated values."""
    lines = contents.splitlines()
    entry = f"{key}={value}"
    matches = [i for i, line in enumerate(lines) if re.match(rf"^\s*{re.escape(key)}\s*=", line)]
    if matches:
        lines[matches[0]] = entry
        for index in reversed(matches[1:]):
            del lines[index]
    else:
        lines.append(entry)
    return "\n".join(lines).rstrip("\n") + "\n"


def safe_backup(path: Path) -> None:
    if not path.exists():
        return
    backup_dir = ROOT / "hermin/backups/files"
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
    shutil.copy2(path, backup)
    if path in {ENV_FILE, OPENCODE_CONFIG}:
        backup.chmod(0o600)


def atomic_write(path: Path, value: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode & 0o777 if path.exists() else (mode or 0o600)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(value)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temp_name, mode if mode is not None else old_mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def run(command: list[str], timeout: int = 15) -> dict:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return {"ok": result.returncode == 0, "code": result.returncode,
                "stdout": result.stdout[-12000:], "stderr": result.stderr[-4000:]}
    except FileNotFoundError as exc:
        return {"ok": False, "code": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": 124, "stdout": "", "stderr": "Perintah melewati batas waktu."}


def control_service(target: str, action: str) -> dict:
    if target == "hermes":
        units = ["hermes-gateway.service", "hermes-dashboard.service"]
    else:
        units = ["9router.service"]
    if action == "logs":
        return run(["journalctl", "--user", *[arg for unit in units for arg in ("-u", unit)],
                    "-n", "80", "--no-pager"], timeout=30)
    if action == "start":
        command = ["systemctl", "--user", "enable", "--now", *units]
    elif action == "shutdown":
        command = ["systemctl", "--user", "disable", "--now", *units]
    elif action in {"stop", "restart"}:
        command = ["systemctl", "--user", action, *units]
    else:
        return {"ok": False, "error": "Aksi layanan tidak dikenal."}
    return run(command, timeout=60 if action in {"start", "restart"} else 30)


def wait_for_hermes_dashboard(seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:9119/", timeout=1):
                return True
        except urllib.error.HTTPError:
            return True  # An auth challenge also means the dashboard is listening.
        except (OSError, ValueError):
            time.sleep(0.4)
    return False


def restore_privacy() -> dict:
    config = yaml.safe_load(read(CONFIG)) or {}
    if not isinstance(config, dict):
        raise ValueError("config.yaml harus berisi objek konfigurasi.")
    updates = {CONFIG: yaml.safe_dump(native_config(config), sort_keys=False, allow_unicode=True)}
    updates.update({path: with_policy(name, read(path)) for name, path in TEXT_FILES.items()})
    for path, contents in updates.items():
        safe_backup(path)
        atomic_write(path, contents, 0o600)
    return {"ok": True, "message": "Aturan privasi dipulihkan. Buka sesi Hermes baru untuk memakai Soul/memory terbaru. Ini instruksi perilaku, bukan sandbox."}


def get_models(env: dict[str, str], base_url: str) -> dict:
    url = base_url.rstrip("/") + "/models"
    cache_key = hashlib.sha256((url + "\0" + env.get("OPENAI_API_KEY", "")).encode()).hexdigest()

    def last_known(error: str) -> dict:
        try:
            cache = json.loads(ROUTER_CATALOG_CACHE.read_text(encoding="utf-8"))
            models = cache["models"]
            if (cache.get("key") == cache_key and isinstance(models, list)
                    and 0 <= time.time() - cache.get("updated_at", 0) <= 86400):
                return {"ok": False, "models": models, "count": len(models), "url": url,
                        "error": f"{error} Menampilkan katalog terakhir yang berhasil dibaca."}
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return {"ok": False, "models": [], "count": 0, "url": url, "error": error}

    headers = {"Accept": "application/json"}
    if env.get("OPENAI_API_KEY"):
        headers["Authorization"] = "Bearer " + env["OPENAI_API_KEY"]
    request = urllib.request.Request(url, headers=headers)
    try:
        # 9Router refreshes live catalogs from multiple providers before answering.
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        raw_models = data.get("data", data.get("models", []))
        models = []
        for item in raw_models:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            model_id = str(item["id"])
            provider = item.get("provider") or item.get("owned_by") or ""
            raw_kind = item.get("kind") or item.get("type") or ""
            kind = "combo" if item.get("owned_by") == "combo" or str(raw_kind).lower() in {"websearch", "webfetch"} or "combo" in model_id.lower() else (raw_kind or "model")
            title = item.get("title") or item.get("name") or model_id
            detail = item.get("description") or item.get("model") or raw_kind or ""
            models.append({"id": model_id, "label": str(title), "kind": str(kind),
                           "provider": str(provider), "detail": str(detail)[:180]})
        models.sort(key=lambda item: (0 if item["kind"].lower() == "combo" else 1, item["label"].lower()))
        try:
            atomic_write(ROUTER_CATALOG_CACHE, json.dumps({"key": cache_key,
                         "updated_at": time.time(), "models": models}, ensure_ascii=False), 0o600)
        except OSError:
            pass  # Catalog persistence is optional; a live response still succeeds.
        return {"ok": True, "models": models, "count": len(models), "url": url}
    except urllib.error.HTTPError as exc:
        return last_known(f"HTTP {exc.code} — periksa API key atau endpoint.")
    except Exception as exc:
        return last_known(f"Tidak tersambung ({type(exc).__name__}). Pastikan 9Router aktif.")


def get_usage_stats(period: str = "24h") -> dict:
    windows = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    if period not in windows:
        raise ValueError("Periode statistik tidak valid.")
    if not ROUTER_USAGE_DB.is_file():
        return {"available": False, "period": period, "error": "Database pemakaian 9Router belum ditemukan."}
    cutoff = (datetime.now(timezone.utc) - windows[period]).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    try:
        with sqlite3.connect(f"file:{ROUTER_USAGE_DB}?mode=ro", uri=True, timeout=2) as conn:
            conn.execute("PRAGMA query_only=ON")
            summary = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(promptTokens),0), COALESCE(SUM(completionTokens),0), "
                "COALESCE(SUM(cost),0) FROM usageHistory WHERE timestamp >= ?", (cutoff,)
            ).fetchone()
            top = conn.execute(
                "SELECT model, SUM(COALESCE(promptTokens,0)+COALESCE(completionTokens,0)) AS total "
                "FROM usageHistory WHERE timestamp >= ? AND model IS NOT NULL "
                "GROUP BY model ORDER BY total DESC LIMIT 1", (cutoff,)
            ).fetchone()
        prompt = int(summary[1] or 0)
        completion = int(summary[2] or 0)
        return {"available": True, "period": period, "requests": int(summary[0]),
                "prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": prompt + completion, "estimated_cost_usd": round(float(summary[3] or 0), 6),
                "top_model": str(top[0]) if top else ""}
    except (OSError, sqlite3.Error):
        return {"available": False, "period": period, "error": "Statistik 9Router belum dapat dibaca."}


def opencode_model_state() -> dict:
    """Return model choices without sending provider credentials to the browser."""
    if not OPENCODE_CONFIG.is_file():
        return {"ok": False, "error": f"Konfigurasi OpenCode tidak ditemukan: {OPENCODE_CONFIG}"}
    try:
        config = json.loads(read(OPENCODE_CONFIG))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"JSON OpenCode tidak valid pada baris {exc.lineno}."}
    if not isinstance(config, dict) or not isinstance(config.get("provider"), dict):
        return {"ok": False, "error": "Bagian provider di konfigurasi OpenCode tidak valid."}
    providers = config["provider"]
    router = providers.get("9router", {})
    router_options = router.get("options", {}) if isinstance(router, dict) else {}
    router_options = router_options if isinstance(router_options, dict) else {}
    base_url = str(router_options.get("baseURL") or "http://127.0.0.1:20128/v1").rstrip("/")
    if re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):\d+/v1", base_url):
        key = router_options.get("apiKey")
        if not isinstance(key, str) or key.startswith("{env:"):
            key = parse_env(read(ENV_FILE)).get("OPENAI_API_KEY", "")
        catalog = get_models({"OPENAI_API_KEY": key}, base_url)
    else:
        catalog = {"ok": False, "models": [], "count": 0,
                   "error": "URL 9Router OpenCode harus menunjuk ke localhost /v1."}
    live = {item["id"]: item for item in catalog["models"]}
    choices = []
    seen = set()
    for provider_id, provider in providers.items():
        if not isinstance(provider_id, str) or not isinstance(provider, dict):
            continue
        configured = provider.get("models", {})
        if not isinstance(configured, dict):
            continue
        if provider_id == "9router":
            for model_id, item in live.items():
                full_id = f"9router/{model_id}"
                choices.append({"id": full_id, "label": str(item.get("label") or model_id),
                                "provider": "9Router", "available": True})
                seen.add(full_id)
        for model_id, meta in configured.items():
            if not isinstance(model_id, str):
                continue
            full_id = f"{provider_id}/{model_id}"
            if full_id in seen:
                continue
            label = meta.get("name", model_id) if isinstance(meta, dict) else model_id
            choices.append({"id": full_id, "label": str(label), "provider": provider_id,
                            "available": provider_id != "9router"})
            seen.add(full_id)
    agents = config.get("agent", {})
    agents = agents if isinstance(agents, dict) else {}
    return {"ok": True, "path": str(OPENCODE_CONFIG),
            "model": str(config.get("model") or ""),
            "small_model": str(config.get("small_model") or ""),
            "agents": [{"id": name, "model": str(value.get("model") or "")}
                       for name, value in agents.items() if isinstance(value, dict)],
            "models": choices, "router": {"ok": catalog["ok"], "count": catalog["count"],
                                          "error": catalog.get("error", ""), "base_url": base_url}}


def save_opencode_models(payload: dict) -> dict:
    before = opencode_model_state()
    if not before["ok"]:
        raise ValueError(before["error"])
    config = json.loads(read(OPENCODE_CONFIG))
    selected = {name: str(payload.get(name) or "").strip()
                for name in ("model", "small_model", "agent_model")}
    agent_name = str(payload.get("agent_name") or "")
    if not selected["model"]:
        raise ValueError("Pilih model utama OpenCode.")
    agent_map = {item["id"]: item["model"] for item in before["agents"]}
    if agent_name and agent_name not in agent_map:
        raise ValueError("Agent OpenCode tidak ditemukan di konfigurasi.")
    allowed = {item["id"] for item in before["models"] if item["available"]}
    old_values = {"model": before["model"], "small_model": before["small_model"],
                  "agent_model": agent_map.get(agent_name, "")}
    for field, model_id in selected.items():
        if not model_id:
            continue
        if model_id not in allowed and model_id != old_values[field]:
            raise ValueError(f"Model {model_id} belum tersedia pada katalog provider. Muat ulang 9Router.")
    router_models = {item["id"]: item for item in before["models"] if item["provider"] == "9Router"}
    for model_id in selected.values():
        if model_id.startswith("9router/") and model_id in allowed:
            raw_id = model_id.removeprefix("9router/")
            config["provider"]["9router"].setdefault("models", {}).setdefault(
                raw_id, {"name": router_models[model_id]["label"]})
    config["model"] = selected["model"]
    if selected["small_model"]:
        config["small_model"] = selected["small_model"]
    else:
        config.pop("small_model", None)
    if agent_name:
        agent = config["agent"][agent_name]
        if selected["agent_model"]:
            agent["model"] = selected["agent_model"]
        else:
            agent.pop("model", None)
    safe_backup(OPENCODE_CONFIG)
    atomic_write(OPENCODE_CONFIG, json.dumps(config, ensure_ascii=False, indent=2) + "\n", 0o600)
    return {"ok": True, "message": "Model OpenCode disimpan. Sesi baru memakai default ini; pilihan model pada sesi aktif dapat tetap berlaku."}


def state() -> dict:
    env_text = read(ENV_FILE)
    env = parse_env(env_text)
    try:
        config = yaml.safe_load(read(CONFIG)) or {}
    except yaml.YAMLError as exc:
        config = {}
        config_error = str(exc)
    else:
        config_error = ""
    model = config.get("model", {}) if isinstance(config, dict) else {}
    status = run(["systemctl", "--user", "show", "hermes-gateway.service",
                  "--property=ActiveState", "--property=SubState", "--property=ExecStart"], timeout=5)
    fields = dict(line.split("=", 1) for line in status["stdout"].splitlines() if "=" in line)
    dashboard_status = run(["systemctl", "--user", "show", "hermes-dashboard.service",
                            "--property=ActiveState", "--property=SubState", "--property=ExecStart"], timeout=5)
    dashboard_fields = dict(line.split("=", 1) for line in dashboard_status["stdout"].splitlines() if "=" in line)
    router_status = run(["systemctl", "--user", "show", "9router.service",
                         "--property=ActiveState", "--property=SubState", "--property=ExecStart"], timeout=5)
    router_fields = dict(line.split("=", 1) for line in router_status["stdout"].splitlines() if "=" in line)
    hermes_enabled = run(["systemctl", "--user", "is-enabled", "hermes-gateway.service",
                          "hermes-dashboard.service"], timeout=5)
    router_enabled = run(["systemctl", "--user", "is-enabled", "9router.service"], timeout=5)
    running = fields.get("ActiveState") == "active" and dashboard_fields.get("ActiveState") == "active"
    services = [{"Service": "hermes", "State": fields.get("ActiveState", "unknown"),
                 "Status": fields.get("SubState", "")},
                {"Service": "dashboard", "State": dashboard_fields.get("ActiveState", "unknown"),
                 "Status": dashboard_fields.get("SubState", "")}] if status["ok"] and dashboard_status["ok"] else []
    router_url = str((model.get("base_url") if model.get("provider") == "custom" else None)
                     or env.get("OPENAI_BASE_URL") or "http://127.0.0.1:20128/v1")
    models = get_models(env, router_url) if router_url.startswith(("http://127.0.0.1", "http://localhost")) else {
        "ok": False, "models": [], "count": 0, "url": router_url,
        "error": "Untuk keamanan, pemeriksaan model hanya dilakukan ke 9Router lokal (localhost)."}
    return {
        "csrf": CSRF,
        "files": {"service_hermes": read(SERVICE_UNITS["hermes"]),
                  "service_dashboard": read(SERVICE_UNITS["dashboard"]),
                  "service_router": read(SERVICE_UNITS["router"]), "config": read(CONFIG)},
        "texts": {key: read(path) for key, path in TEXT_FILES.items()},
        "secrets": {"api_key_set": bool(env.get("OPENAI_API_KEY"))},
        # Never return arbitrary env values: the file may contain unrelated tokens.
        "environment": {"OPENAI_BASE_URL": env.get("OPENAI_BASE_URL", ""),
                        "TERMINAL_ENV": env.get("TERMINAL_ENV", "")},
        "model": {"provider": model.get("provider", "custom"),
                  "default": model.get("default") or model.get("model") or "",
                  "base_url": router_url,
                  "key_env": model.get("key_env", "OPENAI_API_KEY"),
                  "terminal_backend": (config.get("terminal") or {}).get("backend", "local")},
        "config_error": config_error,
        "hermes": {"running": running, "services": services,
                   "output": status["stderr"] if not status["ok"] else ""},
        "router_service": {"running": router_fields.get("ActiveState") == "active",
                           "state": router_fields.get("ActiveState", "unknown"),
                           "detail": router_fields.get("SubState", ""),
                           "enabled": router_enabled["ok"]},
        "opencode_web": opencode_web_state(),
        "router": models,
        "usage": get_usage_stats(),
        "nous_models": get_nous_models(),
        "security": {"mode": "sandbox" if any("run_sandbox.py" in source for source in
                         (fields.get("ExecStart", ""), dashboard_fields.get("ExecStart", "")))
                     else "native" if fields.get("ExecStart") and dashboard_fields.get("ExecStart") else "unknown",
                     "policy_installed": policy_present({key: read(path) for key, path in TEXT_FILES.items()}),
                     "approval_mode": (config.get("approvals") or {}).get("mode", "smart"),
                     "lazy_installs": (config.get("security") or {}).get("allow_lazy_installs", True),
                     "redact_secrets": (config.get("security") or {}).get("redact_secrets", True),
                     "autostart": hermes_enabled["ok"]},
        "files_present": {"services": all(path.exists() for path in SERVICE_UNITS.values()),
                          "env": ENV_FILE.exists(), "config": CONFIG.exists()},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesLocalPanel/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Avoid logging URL query strings, form values, or API keys.
        print(f"[panel] {self.address_string()} {fmt % args}")

    def _security(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost", "[::1]"}:
            self.send_error(403, "Dashboard hanya tersedia dari komputer ini.")
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                self.send_error(403, "Origin tidak diizinkan.")
                return False
        authorization = self.headers.get("Authorization", "")
        try:
            scheme, encoded = authorization.split(" ", 1)
            raw = base64.b64decode(encoded, validate=True).decode("utf-8") if scheme.lower() == "basic" else ""
            username, password = raw.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            username, password = "", ""
        if username != ADMIN_USER or not hmac.compare_digest(password, ADMIN_TOKEN):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="HERMIN Admin", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False
        return True

    def _send(self, status: int, value: dict | str, content_type: str = "application/json") -> None:
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        ancestors = "'self'" if urlparse(self.path).path == "/opencode-web" else "'none'"
        self.send_header("Content-Security-Policy", f"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'self' http://127.0.0.1:4096; img-src 'self' data:; base-uri 'none'; frame-ancestors {ancestors}")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._security():
            return
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, read(HERE / "index.html"), "text/html")
        elif path == "/style.css":
            self._send(200, read(HERE / "style.css"), "text/css")
        elif path == "/app.js":
            self._send(200, read(HERE / "app.js"), "application/javascript")
        elif path == "/opencode-web":
            self._send(200, read(HERE / "opencode-web.html"), "text/html")
        elif path in {"/opencode-web.js", "/opencode-web.css"}:
            self._send(200, read(HERE / path.lstrip("/")),
                       "application/javascript" if path.endswith(".js") else "text/css")
        elif path == "/api/opencode/web":
            self._send(200, {**opencode_web_state(), "csrf": CSRF})
        elif path == "/api/update":
            self._send(200, check_update())
        elif path == "/api/skills":
            self._send(200, {**SKILLS.inventory(), "csrf": CSRF})
        elif path == "/skills.js":
            self._send(200, read(HERE / "skills.js"), "application/javascript")
        elif path == "/api/state":
            self._send(200, state())
        elif path == "/api/opencode":
            self._send(200, opencode_model_state())
        elif path == "/api/sessions":
            self._send(200, {"sessions": list_sessions()})
        elif path == "/api/usage":
            try:
                period = parse_qs(urlparse(self.path).query).get("period", ["24h"])[0]
                self._send(200, get_usage_stats(period))
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
        elif path == "/api/env/full":
            self._send(200, {"csrf": CSRF, "text": read(ENV_FILE)})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if not self._security():
            return
        if self.headers.get("X-CSRF-Token") != CSRF:
            self.send_error(403, "Token sesi tidak valid; muat ulang dashboard.")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2_000_000:
                raise ValueError("Isi terlalu besar.")
            payload = json.loads(self.rfile.read(length) or b"{}")
            action = payload.get("action")
            if action == "save-model":
                result = self.save_model(payload)
            elif action in {"opencode-open", "opencode-start", "opencode-stop", "opencode-restart"}:
                result = opencode_web_control(action.removeprefix("opencode-"))
            elif action == "skill-control":
                result = SKILLS.control(str(payload.get("id", "")), str(payload.get("operation", "")))
            elif action == "save-opencode-models":
                result = save_opencode_models(payload)
            elif action == "save-env":
                result = self.save_env(payload)
            elif action == "save-service":
                result = self.save_service(payload)
            elif action == "save-text":
                result = self.save_text(payload)
            elif action == "restore-privacy":
                result = restore_privacy()
            elif action in {"start", "stop", "restart", "shutdown", "logs"}:
                result = control_service("hermes", action)
            elif action in {"router-start", "router-stop", "router-restart", "router-shutdown", "router-logs"}:
                result = control_service("router", action.removeprefix("router-"))
            elif action == "refresh-models":
                current = state()
                result = {"ok": current["router"]["ok"], "data": current["router"]}
            elif action == "refresh-nous-models":
                result = refresh_nous_models()
            else:
                result = {"ok": False, "error": "Aksi tidak dikenal."}
            self._send(200 if result.get("ok") else 400, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": str(exc)})
        except OSError as exc:
            if exc.errno in {errno.EROFS, errno.EACCES, errno.EPERM}:
                target = str(OPENCODE_CONFIG.parent) if locals().get("action") == "save-opencode-models" else str(ROOT / "hermes")
                self._send(503, {"ok": False, "error": f"HERMIN tidak memiliki akses tulis ke {target}. Periksa izin file dan user yang menjalankan dashboard."})
            else:
                self._send(500, {"ok": False, "error": f"Gagal menyimpan file: {exc.strerror or type(exc).__name__}"})
        except Exception as exc:
            self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def save_model(self, payload: dict) -> dict:
        raw = read(CONFIG)
        config = yaml.safe_load(raw) if raw.strip() else {}
        if config is None:
            config = {}
        if not isinstance(config, dict):
            return {"ok": False, "error": "config.yaml harus berupa YAML object."}
        model = config.setdefault("model", {})
        if not isinstance(model, dict):
            return {"ok": False, "error": "Bagian model di config.yaml tidak valid."}
        provider = str(payload.get("provider", "custom")).strip()
        if provider not in {"custom", "nous"}:
            return {"ok": False, "error": "Provider yang didukung dashboard ini: custom (9Router) atau nous (Nous Portal)."}
        old_provider = str(model.get("provider", "custom"))
        old_default = str(model.get("default") or model.get("model") or "")
        old_base_url = str(model.get("base_url") or "")
        model["provider"] = provider
        model["default"] = str(payload.get("default", "")).strip()
        if not model["default"]:
            return {"ok": False, "error": "Isi model ID dulu."}
        if provider == "custom":
            base_url = str(payload.get("base_url", "")).strip().rstrip("/")
            if not re.fullmatch(r"http://(127\.0\.0\.1|localhost):\d+/v1", base_url):
                return {"ok": False, "error": "Untuk koneksi lokal, base URL harus seperti http://127.0.0.1:20128/v1."}
            model["base_url"] = base_url
            model["key_env"] = "OPENAI_API_KEY"
            new_key = str(payload.get("api_key", "")).strip()
            if new_key and (len(new_key) > 512 or not re.fullmatch(r"[A-Za-z0-9._-]+", new_key)):
                return {"ok": False, "error": "Format API key 9Router tidak valid."}
            env_before = read(ENV_FILE)
            env_after = set_env_value(env_before, "OPENAI_BASE_URL", base_url)
            if new_key:
                env_after = set_env_value(env_after, "OPENAI_API_KEY", new_key)
        else:
            model.pop("base_url", None)
            model.pop("key_env", None)
            env_before = env_after = ""
        encoded = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        safe_backup(CONFIG)
        if env_after != env_before:
            safe_backup(ENV_FILE)
        atomic_write(CONFIG, encoded, 0o600)
        try:
            if env_after != env_before:
                atomic_write(ENV_FILE, env_after, 0o600)
        except OSError:
            atomic_write(CONFIG, raw, 0o600)
            raise
        changed = (old_provider != provider or old_default != model["default"] or
                   (provider == "custom" and old_base_url != model["base_url"]))
        restarted = False
        chat_ready = False
        if changed or env_after != env_before:
            running = run(["systemctl", "--user", "is-active", "hermes-gateway.service"], timeout=5)
            if running["stdout"].strip() == "active":
                restart = run(["systemctl", "--user", "restart", "hermes-gateway.service", "hermes-dashboard.service"], timeout=60)
                if not restart["ok"]:
                    return {"ok": False, "error": "Model tersimpan, tetapi restart Hermes gagal. Periksa log layanan."}
                restarted = True
                chat_ready = wait_for_hermes_dashboard(20.0)
        return {"ok": True, "model_changed": changed, "restarted": restarted,
                "chat_ready": chat_ready,
                "message": "Model aktif untuk sesi baru. HERMIN membuka chat bersih; riwayat lama tetap tersimpan." if changed and chat_ready
                           else "Model disimpan. Buka chat baru saat Hermes siap." if changed
                           else "Pengaturan model disimpan."}

    def save_env(self, payload: dict) -> dict:
        contents = str(payload.get("text", ""))
        keys = []
        for line in contents.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    return {"ok": False, "error": f"Nama variabel tidak valid: {key}"}
                keys.append(key)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            return {"ok": False, "error": "Variabel duplikat: " + ", ".join(duplicates)}
        safe_backup(ENV_FILE)
        atomic_write(ENV_FILE, contents.rstrip() + "\n", 0o600)
        return {"ok": True, "message": "File .env disimpan dengan izin 600. Restart layanan Hermes agar perubahan diterapkan."}

    def save_service(self, payload: dict) -> dict:
        name = str(payload.get("name", ""))
        path = SERVICE_UNITS.get(name)
        if path is None:
            return {"ok": False, "error": "Layanan tidak dikenal."}
        contents = str(payload.get("text", ""))
        if len(contents.encode("utf-8")) > 100_000 or "[Service]" not in contents or "ExecStart=" not in contents:
            return {"ok": False, "error": "Unit systemd harus memuat [Service] dan ExecStart, maksimal 100 KB."}
        old = read(path)
        safe_backup(path)
        atomic_write(path, contents, 0o644)
        checked = run(["systemd-analyze", "verify", str(path)], timeout=20)
        if not checked["ok"]:
            atomic_write(path, old, 0o644)
            return {"ok": False, "error": "Unit systemd tidak valid; perubahan dibatalkan. " + (checked["stderr"] or checked["stdout"])[-1000:]}
        reload_result = run(["systemctl", "--user", "daemon-reload"], timeout=15)
        return {"ok": True, "message": ("Unit tersimpan dan daemon dimuat ulang. Restart layanan untuk menerapkan perubahan."
                                         if reload_result["ok"] else
                                         "Unit tersimpan. Jalankan systemctl --user daemon-reload di terminal biasa sebelum restart.")}

    def save_text(self, payload: dict) -> dict:
        name = str(payload.get("name", ""))
        path = TEXT_FILES.get(name)
        if path is None:
            return {"ok": False, "error": "File teks tidak diizinkan."}
        contents = str(payload.get("text", ""))
        if len(contents.encode("utf-8")) > 200_000:
            return {"ok": False, "error": "Batas ukuran file adalah 200 KB."}
        safe_backup(path)
        atomic_write(path, contents, 0o600)
        return {"ok": True, "message": f"{path.name} disimpan. Perubahan Soul/memory berlaku pada sesi baru atau setelah dimuat ulang Hermes."}

def get_nous_models() -> list[dict]:
    """Combine Hermes' curated IDs with Portal's cached free picks and pricing."""
    def object_at(path: Path) -> dict:
        try:
            value = json.loads(read(path))
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    curated = object_at(DATA / "cache" / "model_catalog.json").get("providers", {}).get("nous", {}).get("models", [])
    ids = {str(item["id"]) for item in curated if isinstance(item, dict) and item.get("id")}
    panel_cache = object_at(NOUS_CACHE)
    hermes_recs = object_at(NOUS_RECOMMENDATIONS).get("https://portal.nousresearch.com", {})
    hermes_meta = object_at(NOUS_METADATA).get("https://inference-api.nousresearch.com/v1", {})
    rec_source = max((panel_cache.get("recommendations", {}), hermes_recs),
                     key=lambda value: value.get("at", value.get("ts", 0)) if isinstance(value, dict) else 0)
    meta_source = max((panel_cache.get("pricing", {}), hermes_meta),
                      key=lambda value: value.get("at", 0) if isinstance(value, dict) else 0)
    rec_data = rec_source.get("data", {}) if isinstance(rec_source, dict) else {}
    metadata = meta_source.get("models", {}) if isinstance(meta_source, dict) else {}
    rec_fresh = 0 <= time.time() - rec_source.get("at", rec_source.get("ts", 0)) < 86_400
    meta_fresh = 0 <= time.time() - meta_source.get("at", 0) < 86_400
    free_recommended = {
        str(item["modelName"]).strip() for item in rec_data.get("freeRecommendedModels", [])
        if isinstance(item, dict) and item.get("modelName")
    } if isinstance(rec_data, dict) else set()
    ids.update(free_recommended)

    def price_tier(item: dict) -> str:
        pricing = item.get("pricing")
        if not isinstance(pricing, dict) or pricing.get("billing_mode") == "subscription":
            return "unknown"
        try:
            prices = [Decimal(str(pricing[key])) for key in ("prompt", "completion")]
            if any(not price.is_finite() or price < 0 for price in prices):
                return "unknown"
            return "free" if all(price == 0 for price in prices) else "paid"
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return "unknown"

    if isinstance(metadata, dict):
        ids.update(mid for mid, item in metadata.items()
                   if "/" in mid and isinstance(item, dict) and meta_fresh and price_tier(item) == "free")
    result = []
    for mid in ids:
        item = metadata.get(mid, {}) if isinstance(metadata, dict) else {}
        item = item if isinstance(item, dict) else {}
        pricing_tier = price_tier(item) if meta_fresh else "unknown"
        recommended_free = rec_fresh and mid in free_recommended
        tier = "unknown" if recommended_free and pricing_tier == "paid" else (
            "free" if recommended_free or pricing_tier == "free" else pricing_tier)
        result.append({"id": mid, "label": str(item.get("name") or mid), "kind": "model",
                       "provider": "Nous Portal", "tier": tier,
                       "detail": "Status harga bertentangan dengan rekomendasi gratis; cek Portal." if recommended_free and pricing_tier == "paid"
                                 else "Gratis menurut rekomendasi/harga Portal (cache ≤24 jam)." if tier == "free"
                                 else "Berbayar menurut harga Portal." if tier == "paid"
                                 else "Harga belum terverifikasi; cek Nous Portal sebelum memakai."})
    return sorted(result, key=lambda item: ({"free": 0, "unknown": 1, "paid": 2}[item["tier"]], item["id"].lower()))


def refresh_nous_models() -> dict:
    """Refresh public Portal metadata; no OAuth token or API key is sent."""
    sources = {
        "recommendations": "https://portal.nousresearch.com/api/nous/recommended-models",
        "pricing": "https://inference-api.nousresearch.com/v1/models",
    }
    try:
        cache = json.loads(read(NOUS_CACHE) or "{}")
        if not isinstance(cache, dict):
            cache = {}
    except (json.JSONDecodeError, OSError):
        cache = {}
    updated = []
    errors = []
    for kind, url in sources.items():
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read(4_000_001)
            if len(body) > 4_000_000:
                raise ValueError("Katalog terlalu besar.")
            data = json.loads(body)
            if kind == "recommendations":
                if not isinstance(data, dict) or not isinstance(data.get("freeRecommendedModels"), list):
                    raise ValueError("Format rekomendasi tidak dikenal.")
                cache[kind] = {"at": time.time(), "data": data}
            else:
                models = data.get("data", []) if isinstance(data, dict) else []
                if not isinstance(models, list) or not models:
                    raise ValueError("Format daftar model tidak dikenal.")
                reduced = {str(item["id"]): {"name": item.get("name"), "pricing": item.get("pricing")}
                           for item in models if isinstance(item, dict) and item.get("id")}
                cache[kind] = {"at": time.time(), "models": reduced}
            updated.append(kind)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{kind}: {type(exc).__name__}")
    if updated:
        atomic_write(NOUS_CACHE, json.dumps(cache, ensure_ascii=False), 0o600)
    models = get_nous_models()
    return {"ok": bool(updated) or bool(models), "models": models,
            "message": "Katalog Nous diperbarui." if updated else "Memakai cache Hermes; Portal belum dapat dihubungi.",
            "warning": ", ".join(errors)}


def connect_sessions_db():
    if not SESSIONS_DB.exists():
        return None
    db = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True, timeout=0.5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def list_sessions() -> list[dict]:
    sessions: list[dict] = []
    db = connect_sessions_db()
    stores = [(db, "", None)] if db is not None else []
    for store, instance_id, port in stores:
        try:
            rows = store.execute("""SELECT id, source, title, started_at, last_activity_at, ended_at,
                                message_count, profile_name FROM sessions
                                WHERE hidden=0 AND archived=0
                                ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 300""").fetchall()
            for row in rows:
                sessions.append({"id": row["id"], "source": row["source"],
                                 "title": row["title"] or "Sesi tanpa judul",
                                 "started_at": row["started_at"], "last_activity_at": row["last_activity_at"],
                                 "active": row["ended_at"] is None, "messages": row["message_count"] or 0,
                                 "profile": row["profile_name"] or "default",
                                 "instance_id": instance_id, "url": f"http://127.0.0.1:{port}/chat" if port else ""})
        except sqlite3.Error:
            pass
        finally:
            store.close()
    sessions.sort(key=lambda item: item["last_activity_at"] or item["started_at"] or 0, reverse=True)
    return sessions[:300]


if __name__ == "__main__":
    print(f"Hermes Control Panel: http://127.0.0.1:{PORT}")
    print("Bound to loopback only. Press Ctrl+C to stop.")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
