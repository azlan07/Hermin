#!/usr/bin/env python3
"""Install, diagnose and update HERMIN without replacing agent runtimes or data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parent
RUNTIME_FILES = ('app.py', 'app.js', 'index.html', 'style.css', 'settings.py', 'updates.py',
                 'privacy_policy.py', 'skill_manager.py', 'skills.js', 'opencode_web.py',
                 'opencode-web.html', 'opencode-web.js', 'opencode-web.css')
ORIGIN = 'https://github.com/azlan07/Hermin.git'


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True, **kwargs)


def unit_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def unit_text(root, python, port):
    app = root / 'hermes/control-dashboard/app.py'
    return f'''[Unit]
Description=HERMIN local admin dashboard
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
Environment={unit_quote('HERMIN_ROOT=' + str(root))}
Environment=HERMES_PANEL_PORT={port}
WorkingDirectory={str(app.parent).replace('%', '%%')}
ExecStart={unit_quote(python)} {unit_quote(app)}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
UMask=0077
[Install]
WantedBy=default.target
'''


def install(root, port, no_systemd=False, no_start=False):
    if os.getuid() == 0:
        raise ValueError('Jalankan sebagai user biasa, tanpa sudo; HERMIN mengelola layanan user itu.')
    if any(char in str(root) for char in '\n\r'):
        raise ValueError('Lokasi instalasi tidak valid.')
    unit = Path.home() / '.config/systemd/user/hermin.service'
    if not no_systemd:
        run(['systemctl', '--user', 'show-environment'], capture_output=True)
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.4):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
            except urllib.error.HTTPError as error:
                if error.code != 401 or 'HERMIN Admin' not in error.headers.get('WWW-Authenticate', ''):
                    raise ValueError(f'Port {port} dipakai aplikasi lain; prosesnya tidak dihentikan.')
            else:
                raise ValueError(f'Port {port} dipakai aplikasi lain.')
            if no_systemd or not unit.exists():
                raise ValueError('HERMIN sudah berjalan. Hentikan instans manual sebelum install.')
    except (ConnectionError, TimeoutError):
        pass
    venv = root / 'hermin/venv'
    if not (venv / 'bin/python').exists():
        run([sys.executable, '-m', 'venv', venv])
    python = venv / 'bin/python'
    run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', REPO / 'requirements.txt'])
    run([python, '-m', 'unittest', 'discover', '-s', REPO / 'hermin', '-p', 'test_*.py'], cwd=REPO)
    target = root / 'hermes/control-dashboard'
    state = root / 'hermin/state'
    backup = root / 'hermin/backups' / datetime.now(timezone.utc).strftime('deploy-%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    paths = [*(target / name for name in RUNTIME_FILES), state / 'installation.json']
    if not no_systemd:
        paths.append(unit)
    original = {}
    for i, path in enumerate(paths):
        saved = backup / str(i) if path.exists() else None
        if saved:
            shutil.copy2(path, saved)
        original[path] = saved
    (backup / 'manifest.json').write_text(json.dumps({str(k): str(v) if v else None for k, v in original.items()}, indent=2))
    was_active = not no_systemd and subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'hermin.service']).returncode == 0
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name in RUNTIME_FILES:
            shutil.copy2(REPO / 'hermin' / name, target / name)
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        revision = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        metadata = {'revision': revision.stdout.strip() if revision.returncode == 0 else 'unversioned',
                    'repository': str(REPO), 'python': sys.executable, 'root': str(root), 'port': port,
                    'no_systemd': no_systemd, 'no_start': no_start}
        (state / 'installation.json').write_text(json.dumps(metadata, indent=2))
        if not no_systemd:
            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text(unit_text(root, python, port))
            run(['systemctl', '--user', 'daemon-reload'])
            if not no_start:
                run(['systemctl', '--user', 'enable', 'hermin.service'])
                run(['systemctl', '--user', 'restart', 'hermin.service'])
                for attempt in range(30):
                    try:
                        urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1)
                    except urllib.error.HTTPError as error:
                        if error.code == 401 and 'HERMIN Admin' in error.headers.get('WWW-Authenticate', ''):
                            break
                        raise
                    except OSError:
                        if attempt == 29:
                            raise
                        time.sleep(.3)
                    else:
                        raise ValueError('Dashboard tidak meminta login; pemasangan dibatalkan.')
        print(f'HERMIN terpasang. Backup: {backup}')
        print(f'URL: http://127.0.0.1:{port}/ | username: user Linux yang menjalankan HERMIN')
        print(f'Token login: {root}/hermes/security/hermin-admin-token')
        if no_systemd:
            import shlex
            print(shlex.join(['env', f'HERMIN_ROOT={root}', f'HERMES_PANEL_PORT={port}', str(python), str(target / 'app.py')]))
    except Exception:
        for path, saved in original.items():
            if saved:
                shutil.copy2(saved, path)
            elif path.exists():
                path.unlink()
        if not no_systemd:
            subprocess.run(['systemctl', '--user', 'daemon-reload'])
            if was_active:
                subprocess.run(['systemctl', '--user', 'restart', 'hermin.service'])
            else:
                subprocess.run(['systemctl', '--user', 'disable', '--now', 'hermin.service'])
        raise


def doctor(root):
    ok = True
    for name, port in [('HERMIN', 1515), ('Hermes', 9119), ('9Router', 20128), ('OpenCode', 4096)]:
        if name == 'HERMIN' and (root / 'hermin/state/installation.json').exists():
            port = json.loads((root / 'hermin/state/installation.json').read_text())['port']
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                print(f'OK {name}: localhost:{port}')
        except OSError:
            print(f'MISSING {name}: localhost:{port}'); ok = False
    for path in (root / 'hermes/data/config.yaml', root / 'hermes/data/.env', Path.home() / '.config/opencode/opencode.json'):
        exists = path.is_file(); print(f'{"OK" if exists else "MISSING"} {path}'); ok = ok and exists
    print('Socket/file checks only. Test one real model request in each agent before use.')
    return 0 if ok else 1


def update(root):
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Repo punya perubahan lokal. Commit atau stash terlebih dahulu; perubahan tidak ditimpa.')
    remote = subprocess.check_output(['git', '-C', str(REPO), 'remote', 'get-url', 'origin'], text=True).strip()
    if remote not in (ORIGIN, ORIGIN.removesuffix('.git'), 'git@github.com:azlan07/Hermin.git'):
        raise ValueError('Origin bukan azlan07/Hermin. Periksa remote terlebih dahulu.')
    metadata = json.loads((root / 'hermin/state/installation.json').read_text())
    run(['git', '-C', REPO, 'fetch', 'origin', 'main'])
    run(['git', '-C', REPO, 'merge', '--ff-only', 'origin/main'])
    run([sys.executable, REPO / 'manage.py', 'install', '--root', root, '--port', str(metadata['port']),
         *(['--no-systemd'] if metadata.get('no_systemd') else []), *(['--no-start'] if metadata.get('no_start') else [])])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'doctor', 'check-update', 'update'])
    parser.add_argument('--root', type=Path, default=Path.home() / 'server-lokal')
    parser.add_argument('--port', type=int, default=1515)
    parser.add_argument('--no-systemd', action='store_true', help='Install for manual foreground execution')
    parser.add_argument('--no-start', action='store_true', help='Write unit without enabling/restarting it')
    args = parser.parse_args(); root = args.root.expanduser().resolve()
    if not 1024 <= args.port <= 65535:
        parser.error('Port harus antara 1024 dan 65535.')
    try:
        if args.action == 'install': install(root, args.port, args.no_systemd, args.no_start)
        elif args.action == 'doctor': return doctor(root)
        elif args.action == 'update': update(root)
        else:
            os.environ['HERMIN_ROOT'] = str(root)
            sys.path.insert(0, str(REPO / 'hermin'))
            from updates import check_update
            print(json.dumps(check_update(), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Gagal: {error}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
