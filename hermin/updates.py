"""Read-only GitHub update checks. Applying code updates remains a terminal action."""
import json
import shlex
import urllib.request
from settings import STATE, ROOT


def check_update():
    try:
        installed = json.loads((STATE / 'installation.json').read_text())
        request = urllib.request.Request('https://api.github.com/repos/azlan07/Hermin/commits/main',
                                         headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'HERMIN'})
        with urllib.request.urlopen(request, timeout=12) as response:
            latest = json.load(response)['sha']
        current = installed['revision']
        available = latest != current
        command = shlex.join([installed['python'], str(__import__('pathlib').Path(installed['repository']) / 'manage.py'), 'update', '--root', str(ROOT)])
        return {'ok': True, 'available': available, 'current': current, 'latest': latest,
                'message': f'Pembaruan tersedia: {current[:8]} → {latest[:8]}.' if available else f'HERMIN sudah sesuai main ({current[:8]}).',
                'command': command if available else ''}
    except (OSError, ValueError, KeyError, TypeError):
        return {'ok': False, 'available': None,
                'message': 'Versi belum dapat diperiksa. Pastikan instalasi melalui manage.py selesai dan GitHub dapat diakses.'}
