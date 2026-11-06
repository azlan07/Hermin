"""Inventory and reversible lifecycle for instruction files and 9Router savers."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error
import uuid

import yaml

LOCK = threading.Lock()
PAUSED = '.hermin-paused'
FEATURES = {
    'rtk': ('RTK', 'rtkEnabled', 'Ringkas output tool sebelum dikirim ke model.'),
    'headroom': ('Headroom', 'headroomEnabled', 'Proses kompresi konteks; status diperiksa lewat API 9Router.'),
    'caveman': ('Caveman', 'cavemanEnabled', 'Instruksi untuk mempersingkat jawaban model.'),
    'ponytail': ('Ponytail', 'ponytailEnabled', 'Instruksi kode minimal yang disisipkan 9Router.'),
    'customPrompt': ('Custom system prompt', 'customPromptEnabled', 'Instruksi khusus yang disisipkan pada permintaan model.'),
}


class SkillManager:
    def __init__(self, root, home=None):
        self.root = Path(root)
        self.home = Path(home) if home else Path.home()
        self.hermes = self.root / 'hermes/data'
        self.backups = self.root / 'maintenance/backups/skills'

    def roots(self):
        entries = [(self.hermes / 'skills', 'Hermes'),
                   (self.home / '.config/opencode/skills', 'OpenCode'),
                   (self.home / '.agents/skills', 'OpenCode'),
                   (self.home / '.claude/skills', 'OpenCode')]
        warnings = []
        try:
            config = yaml.safe_load((self.hermes / 'config.yaml').read_text()) or {}
            for p in config.get('skills', {}).get('external_dirs', []):
                entries.append((Path(os.path.expanduser(p)), 'Hermes'))
            cwd = config.get('terminal', {}).get('cwd')
            if cwd and Path(cwd).is_absolute():
                for folder in ('.agents/skills', '.hermes/skills'):
                    entries.append((Path(cwd) / folder, 'Hermes'))
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            warnings.append('Konfigurasi direktori Hermes tidak terbaca.')
        config_file = self.home / '.config/opencode/opencode.json'
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())
                for p in config.get('skills', []):
                    if isinstance(p, str) and (p.startswith('/') or p.startswith('~/')):
                        entries.append((Path(os.path.expanduser(p)), 'OpenCode'))
                    else:
                        warnings.append('Sumber skill OpenCode relatif/remote tidak dikelola di panel ini.')
            except (OSError, ValueError, TypeError):
                warnings.append('Sumber tambahan OpenCode tidak terbaca; direktori standar tetap ditampilkan.')
        return entries, warnings

    def files(self):
        roots, warnings = self.roots()
        allowed = [p.resolve() for p, _ in roots if p.is_dir()]
        found = {}
        for folder, app in roots:
            if not folder.is_dir():
                continue
            # Follow skill-directory symlinks, but never cycles or more than six levels.
            def visit(directory, depth, seen):
                real = directory.resolve()
                if depth > 6 or real in seen:
                    return
                seen = seen | {real}
                candidates = [directory / 'SKILL.md', directory / ('SKILL.md' + PAUSED)]
                selected = [p for p in candidates if p.is_file()]
                if not selected and depth == 0 and app == 'OpenCode':
                    selected = list(directory.glob('*.md')) + list(directory.glob('*.md' + PAUSED))
                for path in selected:
                    actual = path.resolve()
                    key = str(actual).removesuffix(PAUSED)
                    if key in found:
                        if app not in found[key]['apps']:
                            found[key]['apps'].append(app)
                        continue
                    safe = any(actual.is_relative_to(p) and actual.parent != p for p in allowed)
                    if path.name not in ('SKILL.md', 'SKILL.md' + PAUSED):
                        safe = any(actual.parent == p for p in allowed)
                    title, description, error = path.parent.name, '', ''
                    modified = None
                    try:
                        info = actual.stat()
                        modified = int(info.st_mtime)
                        if info.st_size > 1024 * 1024:
                            raise ValueError('SKILL.md melebihi 1 MB.')
                        text = actual.read_text(encoding='utf-8')
                        if not text.startswith('---'):
                            raise ValueError('Frontmatter name/description belum tersedia.')
                        parts = text.split('---', 2)
                        meta = yaml.safe_load(parts[1]) if len(parts) == 3 else None
                        if not isinstance(meta, dict) or not meta.get('name') or not meta.get('description'):
                            raise ValueError('Frontmatter name/description belum lengkap.')
                        title = str(meta['name'])[:160]
                        description = str(meta['description'])[:500]
                    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
                        error = str(exc)[:180]
                    paused = actual.name.endswith(PAUSED)
                    found[key] = {'id': hashlib.sha256(key.encode()).hexdigest(), 'name': title,
                                  'apps': [app], 'kind': 'Instruksi', 'path': str(actual),
                                  'description': description, 'error': error,
                                  'status': 'error' if error else 'paused' if paused else 'available',
                                  'paused': paused, 'writable': safe and os.access(actual.parent, os.W_OK),
                                  'deletable': safe, 'modified': modified}
                if any(p.is_file() for p in candidates):
                    return
                try:
                    for child in directory.iterdir():
                        if child.is_dir() and not child.name.startswith('.') and child.name not in ('node_modules', '__pycache__'):
                            visit(child, depth + 1, seen)
                except OSError:
                    warnings.append(f'Direktori tidak dapat dibaca: {directory}')
            visit(folder, 0, set())
        return list(found.values()), list(dict.fromkeys(warnings))

    def router(self, path, method='GET', body=None):
        # Local control-plane credential stays server-side, scoped to a short-lived session.
        secret = (self.root / '9router/data/jwt-secret').read_text().strip().encode()
        def enc(value):
            return base64.urlsafe_b64encode(value).rstrip(b'=')
        head = enc(b'{"alg":"HS256"}')
        payload = enc(json.dumps({'authenticated': True, 'iat': int(time.time()), 'exp': int(time.time()) + 60}).encode())
        signed = head + b'.' + payload
        token = (signed + b'.' + enc(hmac.new(secret, signed, hashlib.sha256).digest())).decode()
        request = urllib.request.Request('http://127.0.0.1:20128/api/' + path, method=method,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={'Cookie': 'auth_token=' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(f'9Router menolak operasi ({exc.code}); periksa login atau status proses di 9Router.') from None
        except (OSError, ValueError):
            raise ValueError('9Router tidak merespons; periksa layanan dan konfigurasi autentikasinya.') from None

    def inventory(self):
        items, warnings = self.files()
        try:
            settings = self.router('settings')
            try:
                health = self.router('headroom/status')
            except ValueError:
                health = None
            error = ''
        except (ValueError, OSError):
            settings, health, error = {}, None, 'Status 9Router tidak dapat dibaca.'
        for key, (name, setting, description) in FEATURES.items():
            enabled = settings.get(setting, key == 'rtk')
            status = 'error' if error else 'available' if enabled else 'paused'
            detail = error
            if key == 'headroom' and not error:
                status = 'unknown' if health is None else 'running' if health.get('running') else 'error' if enabled else 'stopped'
                detail = ('Status proses belum terbaca.' if health is None else
                          'Routing kompresi aktif tetapi proses tidak berjalan.' if enabled and not health.get('running') else '')
                description += ' Routing ' + ('aktif.' if enabled else 'dipause.')
            items.append({'id': 'router:' + key, 'name': name, 'apps': ['9Router'],
                          'kind': 'Proses' if key == 'headroom' else 'Fitur bawaan',
                          'path': str(self.root / '9router/app/open-sse/rtk'), 'description': description,
                          'status': status, 'error': detail, 'paused': not enabled,
                          'writable': not error, 'deletable': False, 'modified': None,
                          'level': settings.get(key + 'Level', '')})
        return {'items': sorted(items, key=lambda x: (x['apps'][0], x['name'].lower())), 'warnings': warnings,
                'scope': 'Skill global, direktori tambahan lokal, dan workspace Hermes. Skill proyek OpenCode lain, plugin hook, dan MCP tidak dihitung sebagai proses skill.'}

    def archive(self, target):
        self.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest = self.backups / (time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        dest.mkdir(mode=0o700)
        (dest / 'manifest.json').write_text(json.dumps({'original': str(target)}, indent=2))
        return dest

    def control(self, identifier, operation):
        if operation not in ('start', 'pause', 'restart', 'delete', 'open'):
            raise ValueError('Aksi skill tidak dikenal.')
        with LOCK:
            if identifier.startswith('router:'):
                key = identifier.split(':', 1)[1]
                if key not in FEATURES:
                    raise ValueError('Fitur tidak dikenal.')
                if operation == 'delete':
                    raise ValueError('Fitur bawaan 9Router hanya dapat dipause, bukan dihapus.')
                if operation == 'open':
                    return self.open_folder(self.root / '9router/app/open-sse/rtk')
                setting = FEATURES[key][1]
                settings = self.router('settings')
                if operation == 'restart' and key != 'headroom':
                    return {'ok': True, 'message': 'Pengaturan dibaca ulang. Status aktif atau pause tidak diubah.'}
                backup = self.archive(self.root / '9router/data/db/data.sqlite')
                (backup / 'setting.json').write_text(json.dumps({setting: settings.get(setting, key == 'rtk')}))
                if key == 'headroom':
                    if operation == 'pause':
                        self.router('settings', 'PATCH', {setting: False})
                        # Pause routing; a separately-owned Headroom process is not terminated.
                    else:
                        health = self.router('headroom/status')
                        if not health.get('canStart'):
                            raise ValueError('Headroom belum terpasang atau dikelola di host lain. Atur lewat 9Router.')
                        self.router('headroom/' + ('restart' if operation == 'restart' else 'start'), 'POST', {})
                        self.router('settings', 'PATCH', {setting: True})
                else:
                    self.router('settings', 'PATCH', {setting: operation != 'pause'})
                return {'ok': True, 'message': 'Pengaturan 9Router disimpan untuk permintaan berikutnya. Pause Headroom hanya menghentikan routing kompresi.'}
            items, _ = self.files()
            item = next((x for x in items if x['id'] == identifier), None)
            if not item:
                raise ValueError('Skill tidak ditemukan; muat ulang daftar.')
            path = Path(item['path'])
            if operation == 'open':
                return self.open_folder(path.parent)
            if not item['writable']:
                raise ValueError('Lokasi skill tidak berada dalam direktori kelolaan yang dapat ditulis.')
            if operation == 'restart':
                if item['error']:
                    raise ValueError(item['error'])
                return {'ok': True, 'message': 'File skill valid dan sudah dibaca ulang. Buka sesi baru untuk memuat instruksi terbaru; proses agent tidak direstart.'}
            if operation == 'delete':
                target = path.parent if path.name in ('SKILL.md', 'SKILL.md' + PAUSED) else path
                dest = self.archive(target)
                shutil.move(str(target), str(dest / target.name))
            elif operation == 'pause' and not item['paused']:
                dest = Path(str(path) + PAUSED)
                if dest.exists():
                    raise ValueError('Salinan paused sudah ada; periksa direktori terlebih dahulu.')
                path.rename(dest)
            elif operation == 'start' and item['paused']:
                if item['error']:
                    raise ValueError(item['error'])
                dest = Path(str(path).removesuffix(PAUSED))
                if dest.exists():
                    raise ValueError('Skill aktif sudah ada; tidak ditimpa.')
                path.rename(dest)
            return {'ok': True, 'message': 'Skill diperbarui. Buka sesi agent baru; konteks sesi yang sudah berjalan tidak dicabut. Penghapusan disimpan di backup skills.'}

    def open_folder(self, path):
        result = subprocess.run(['xdg-open', str(path)], capture_output=True, timeout=8)
        if result.returncode:
            raise ValueError('File manager tidak dapat dibuka. Gunakan tombol Salin lokasi; folder dibuka di laptop yang menjalankan HERMIN.')
        return {'ok': True, 'message': 'Lokasi dibuka di file manager laptop HERMIN.'}
