"""Run the installed app against an empty stack and validate auth, CSRF and inventory."""
import base64
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

root=Path(sys.argv[1]);port=int(sys.argv[2]); url=f'http://127.0.0.1:{port}'
env={**os.environ,'HERMIN_ROOT':str(root),'HERMES_PANEL_PORT':str(port)}
process=subprocess.Popen([root/'hermin/venv/bin/python',root/'hermes/control-dashboard/app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
try:
    for attempt in range(40):
        if process.poll() is not None:raise RuntimeError(process.stderr.read().decode())
        try:urllib.request.urlopen(url,timeout=.5)
        except urllib.error.HTTPError as error:
            assert error.code==401;break
        except OSError:time.sleep(.1)
        else:raise AssertionError('Authentication missing')
    else:raise AssertionError('Server did not start')
    token=(root/'hermes/security/hermin-admin-token').read_text().strip()
    headers={'Authorization':'Basic '+base64.b64encode((getpass.getuser()+':'+token).encode()).decode()}
    for route in ('/','/skills.js','/api/skills','/api/state','/api/update'):
        with urllib.request.urlopen(urllib.request.Request(url+route,headers=headers),timeout=45) as response:
            assert response.status==200,route
    try:urllib.request.urlopen(urllib.request.Request(url+'/api/action',data=b'{"action":"skill-control"}',headers=headers),timeout=3)
    except urllib.error.HTTPError as error:assert error.code==403
    else:raise AssertionError('CSRF missing')
    assert not (root/'hermes/data/config.yaml').exists(),'Install overwrote agent config'
    print('Clean install smoke: auth, assets, empty-stack state, inventory and CSRF passed.')
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()
