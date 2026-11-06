"""OpenCode's native background service and single-use browser pairing."""
from pathlib import Path
import os
import shutil
from settings import ROOT
import re
import socket
import subprocess
import threading
import urllib.request

URL = "http://127.0.0.1:4096"
# Use a control-plane copy, outside Hermes' writable ~/.opencode grant.
CLI = Path(os.environ.get('HERMIN_OPENCODE_BIN') or (str(ROOT / 'opencode/bin/opencode') if (ROOT / 'opencode/bin/opencode').is_file() else shutil.which('opencode') or str(ROOT / 'opencode/bin/opencode')))
LOCK = threading.Lock()
UNIT = "opencode-web.service"


def command(*args):
    try:
        result = subprocess.run([str(CLI), *args], capture_output=True, text=True,
                                cwd=Path.home(), timeout=30)
    except subprocess.TimeoutExpired:
        raise ValueError("OpenCode belum merespons dalam 30 detik.") from None
    if result.returncode:
        # CLI output can contain authentication credentials; never return it.
        raise ValueError("Perintah OpenCode gagal. Periksa log lokal OpenCode.")
    return result.stdout


def service(action):
    try:
        result = subprocess.run(["systemctl", "--user", action, UNIT],
                                capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        raise ValueError("Layanan OpenCode belum merespons. Muat ulang status.") from None
    if result.returncode:
        raise ValueError("Layanan OpenCode gagal. Periksa `journalctl --user -u opencode-web.service`.")


def web_state():
    result = {"url": URL, "running": False, "conflict": False, "installed": CLI.is_file()}
    try:
        with socket.create_connection(("127.0.0.1", 4096), timeout=0.5):
            result["conflict"] = True
    except OSError:
        return result
    try:
        with urllib.request.urlopen(URL + "/", timeout=2) as response:
            result["running"] = response.status == 200 and bool(re.search(
                rb"<title\b[^>]*>\s*OpenCode\s*</title\s*>", response.read(32768), re.I))
        result["conflict"] = not result["running"]
    except OSError:
        pass
    return result


def control(action):
    if action not in {"open", "start", "stop", "restart"}:
        raise ValueError("Aksi OpenCode tidak dikenal.")
    with LOCK:
        state = web_state()
        if not state["installed"]:
            raise ValueError("Runtime OpenCode belum terpasang untuk HERMIN.")
        if state["conflict"]:
            raise ValueError("Port 4096 dipakai layanan lain. Proses itu tidak dihentikan.")
        # Reject configuration drift instead of pairing with a remote server.
        configured = command("service", "get", "port").strip()
        if configured != "4096":
            raise ValueError("Port layanan OpenCode berubah. Atur `opencode service set port 4096`.")
        if action in {"stop", "restart"} and state["running"]:
            if command("service", "status").strip() != URL:
                raise ValueError("Server 4096 bukan layanan bawaan OpenCode yang dikelola HERMIN.")
        if action == "open":
            if not state["running"]:
                service("start")
            # Wait for systemd's server startup rather than letting pair spawn a
            # second daemon inside HERMIN's cgroup.
            import time
            for _ in range(40):
                if web_state()["running"]:
                    break
                time.sleep(0.25)
            else:
                raise ValueError("Server OpenCode belum siap. Coba sambungkan lagi.")
            output = command("pair", "--url", URL)
            match = re.search(r"http://127\.0\.0\.1:4096/auth/connect/[A-Za-z0-9_-]+(?=\s|$)", output)
            if not match:
                raise ValueError("OpenCode belum memberikan tautan login lokal yang valid.")
            return {"ok": True, "url": match.group(0)}
        service(action)
        return {"ok": True, "message": f"OpenCode: {action} berhasil.", "state": web_state()}
