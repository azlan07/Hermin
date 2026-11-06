import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup import backup, restore, stopped_services


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'source';self.home=self.base/'home'
        self.data=self.root/'hermes/data';self.data.mkdir(parents=True)
        (self.data/'.env').write_text('OPENAI_API_KEY=private-test-value\n')
        (self.data/'SOUL.md').write_text('Private personality and '+str(self.root))
        skills=self.data/'skills/example';skills.mkdir(parents=True)
        (skills/'SKILL.md').write_text('Private skill')
        (skills/'script.sh').write_text('#!/bin/sh\ntrue\n');(skills/'script.sh').chmod(0o700)
        router=self.root/'9router/data/db';router.mkdir(parents=True)
        with sqlite3.connect(router/'data.sqlite') as db:
            db.execute('create table provider (secret text)');db.execute("insert into provider values ('private-provider')")
        (self.data/'tools').mkdir();(self.data/'tools/runtime').write_text('not portable')
        self.archive=backup(self.root,self.home)

    def test_private_roundtrip_includes_provider_secret_and_personality(self):
        self.assertEqual(self.archive.stat().st_mode & 0o777,0o600)
        target=self.base/'target';home=self.base/'other-home'
        recovery,count=restore(target,home,self.archive)
        self.assertGreater(count,3)
        self.assertEqual((target/'hermes/data/.env').read_text(),'OPENAI_API_KEY=private-test-value\n')
        self.assertIn(str(target),(target/'hermes/data/SOUL.md').read_text())
        self.assertFalse((target/'hermes/data/tools').exists())
        self.assertTrue(os.access(target/'hermes/data/skills/example/script.sh',os.X_OK))
        with sqlite3.connect(target/'9router/data/db/data.sqlite') as db:
            self.assertEqual(db.execute('select secret from provider').fetchone()[0],'private-provider')

    def test_existing_files_require_overwrite_and_have_recovery_copy(self):
        target=self.base/'target';restore(target,self.home,self.archive)
        soul=target/'hermes/data/SOUL.md';soul.write_text('changed')
        with self.assertRaises(ValueError):restore(target,self.home,self.archive)
        recovery,_=restore(target,self.home,self.archive,overwrite=True)
        mapping=json.loads((recovery/'manifest.json').read_text())
        self.assertEqual(Path(mapping[str(soul)]).read_text(),'changed')

    def test_archive_traversal_rejected_before_any_write(self):
        bad=self.base/'bad.tar.gz';data=b'attack'
        meta={'format':1,'root':'/old/stack','home':'/old/home','files':{'payload/hermes/../../escape':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
        with tarfile.open(bad,'w:gz') as arc:
            for name,value in [('manifest.json',json.dumps(meta).encode()),('payload/hermes/../../escape',data)]:
                info=tarfile.TarInfo(name);info.size=len(value);arc.addfile(info,io.BytesIO(value))
        with self.assertRaises(ValueError):restore(self.base/'target',self.home,bad)
        self.assertFalse((self.base/'escape').exists())

    def test_restart_is_attempted_on_failure(self):
        with patch('backup.subprocess.run',return_value=MagicMock(returncode=0)) as run:
            with self.assertRaises(ValueError):
                with stopped_services():raise ValueError('failed')
            self.assertEqual(sum('stop' in c.args[0] for c in run.call_args_list),5)
            self.assertEqual(sum('start' in c.args[0] for c in run.call_args_list),5)

    def test_failure_rolls_back_written_files(self):
        target=self.base/'target';restore(target,self.home,self.archive)
        secret=target/'hermes/data/.env';secret.write_text('keep current')
        real_replace=os.replace;calls=0
        def fail_once(*args):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('disk full')
            return real_replace(*args)
        with patch('backup.os.replace',side_effect=fail_once):
            with self.assertRaises(OSError):restore(target,self.home,self.archive,overwrite=True)
        self.assertEqual(secret.read_text(),'keep current')
