import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manage
sys.path.insert(0, str(manage.REPO/'hermin'))
import updates


class InstallTest(unittest.TestCase):
    def test_runtime_manifest_is_complete_and_has_no_local_payload(self):
        for name in manage.RUNTIME_FILES:
            self.assertTrue((manage.REPO/'hermin'/name).is_file(),name)
            self.assertNotIn(name, ['.env', 'state.db', 'config.yaml'])

    def test_unit_escapes_spaces_and_specifiers(self):
        text=manage.unit_text(Path('/tmp/a b%/stack'),Path('/tmp/a b%/python'),1515)
        self.assertIn('%%',text)
        self.assertIn('"/tmp/a b%%/python"',text)
        self.assertIn('NoNewPrivileges=true',text)
        self.assertIn('WorkingDirectory=/tmp/a b%%/stack/hermes/control-dashboard',text)

    def test_update_check_only_compares_and_never_executes_code(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            (state/'installation.json').write_text(json.dumps({'revision':'a'*40,'python':'/usr/bin/python3','repository':'/tmp/repo with space'}))
            response=MagicMock();response.read.return_value=json.dumps({'sha':'b'*40}).encode()
            with patch.object(updates,'STATE',state),patch.object(updates.urllib.request,'urlopen') as request:
                request.return_value.__enter__.return_value=response
                result=updates.check_update()
                self.assertTrue(result['available']);self.assertIn("'/tmp/repo with space/manage.py'",result['command'])
            with patch.object(updates,'STATE',state),patch.object(updates.urllib.request,'urlopen',side_effect=OSError):
                self.assertIsNone(updates.check_update()['available'])
