"""Local paths shared by the dashboard and its maintenance commands."""
import getpass
import os
from pathlib import Path

ROOT = Path(os.environ.get('HERMIN_ROOT', str(Path.home() / 'server-lokal'))).expanduser().resolve()
STATE = ROOT / 'hermin/state'
ADMIN_USER = os.environ.get('HERMIN_ADMIN_USER', getpass.getuser())
