#!/usr/bin/env python3
"""Create native user units for an already installed stack. Never overwrite existing units."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manage import unit_quote as q


def service(description, command, cwd, env):
    return '\n'.join(['[Unit]', 'Description='+description, 'After=network-online.target',
        'Wants=network-online.target', '[Service]', 'Type=simple', 'WorkingDirectory='+str(cwd).replace('%','%%'),
        *['Environment='+q(k+'='+str(v)) for k,v in env.items()],
        'ExecStart='+' '.join(q(x) for x in command), 'Restart=on-failure', 'RestartSec=5',
        'KillMode=mixed', 'TimeoutStopSec=70', 'NoNewPrivileges=true', 'UMask=0077',
        '[Install]', 'WantedBy=default.target', ''])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.home()/'server-lokal')
    p.add_argument('--hermes-bin', type=Path, default=shutil.which('hermes'))
    p.add_argument('--opencode-bin', type=Path, default=shutil.which('opencode'))
    p.add_argument('--node', type=Path, default=shutil.which('node'))
    p.add_argument('--output', type=Path, default=Path.home()/'.config/systemd/user', help='Alternate destination for review/tests')
    a=p.parse_args(); root=a.root.expanduser().resolve()
    if any(c in str(root) for c in '\r\n'):p.error('Invalid root path')
    if os.getuid()==0: p.error('Run as a normal user, not root.')
    for name in ('hermes_bin','opencode_bin','node'):
        file=getattr(a,name)
        if not file or not file.is_file() or not os.access(file,os.X_OK):p.error('Executable missing: '+name)
        if any(c in str(file) for c in '\r\n'):p.error('Invalid executable path')
    router=root/'9router/app/.next/standalone'
    if not (router/'custom-server.js').is_file():p.error('Build 9Router first: missing '+str(router/'custom-server.js'))
    for folder in ('hermes/data','hermes/workspace','9router/data'): (root/folder).mkdir(parents=True,exist_ok=True)
    env={'HERMES_HOME':root/'hermes/data','PATH':str(a.hermes_bin.parent)+':'+str(a.node.parent)+':'+os.environ.get('PATH','/usr/bin:/bin')}
    units={
      '9router.service':service('9Router local AI gateway',[a.node,router/'custom-server.js'],router,{'DATA_DIR':root/'9router/data','PORT':'20128','HOSTNAME':'127.0.0.1','NODE_ENV':'production'}),
      'hermes-gateway.service':service('Hermes gateway',[a.hermes_bin,'gateway','run'],root/'hermes/data',{**env,'HERMES_SUPERVISED_CHILD':'1'}),
      'hermes-dashboard.service':service('Hermes dashboard',[a.hermes_bin,'dashboard','--host','127.0.0.1','--port','9119','--no-open'],root/'hermes/workspace',env),
      'opencode-web.service':service('OpenCode v2 web',[a.opencode_bin,'serve','--service'],Path.home(),{'PATH':env['PATH']})}
    for name in units:
        if (a.output/name).exists():p.error('Existing unit retained: '+str(a.output/name)+'. Configure existing services manually.')
    a.output.mkdir(parents=True,exist_ok=True)
    for name,text in units.items(): (a.output/name).write_text(text)
    print('Units created in',a.output,'. Review them, then daemon-reload and start services as documented.')


if __name__=='__main__':main()
