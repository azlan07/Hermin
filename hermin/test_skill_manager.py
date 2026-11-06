import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skill_manager import SkillManager


class SkillManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.manager = SkillManager(self.base / 'stack', self.base / 'home')
        self.skill = self.manager.hermes / 'skills/example/SKILL.md'
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text('---\nname: example\ndescription: Test instruction\n---\nPrivate instruction.\n')

    def test_pause_resume_reload_and_recoverable_delete(self):
        item = self.manager.files()[0][0]
        self.manager.control(item['id'], 'pause')
        paused = self.manager.files()[0][0]
        self.assertEqual(paused['id'], item['id'])
        self.assertEqual(paused['status'], 'paused')
        self.assertFalse(self.skill.exists())
        self.manager.control(item['id'], 'start')
        self.assertTrue(self.skill.exists())
        self.manager.control(item['id'], 'restart')
        self.manager.control(item['id'], 'delete')
        self.assertEqual(self.manager.files()[0], [])
        archived = list(self.manager.backups.glob('*/example/SKILL.md'))
        self.assertEqual(len(archived), 1)
        self.assertIn('Private instruction.', archived[0].read_text())

    def test_outside_symlink_cannot_be_deleted_or_paused(self):
        outside = self.base / 'unmanaged'
        outside.mkdir()
        (outside / 'SKILL.md').write_text(self.skill.read_text())
        (self.skill.parent.parent / 'linked').symlink_to(outside, target_is_directory=True)
        item = next(x for x in self.manager.files()[0] if x['path'].startswith(str(outside)))
        self.assertFalse(item['writable'])
        for operation in ('delete', 'pause'):
            with self.assertRaises(ValueError):
                self.manager.control(item['id'], operation)
        self.assertTrue((outside / 'SKILL.md').exists())

    def test_duplicate_shared_path_and_invalid_frontmatter(self):
        shared = self.base / 'shared'
        target = shared / 'sample'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('broken')
        with patch.object(self.manager, 'roots', return_value=([(shared, 'Hermes'), (shared, 'OpenCode')], [])):
            items, _ = self.manager.files()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['apps'], ['Hermes', 'OpenCode'])
            self.assertEqual(items[0]['status'], 'error')
            with self.assertRaises(ValueError):
                self.manager.control(items[0]['id'], 'restart')

    def test_arbitrary_ids_and_builtin_deletion_refused(self):
        for identifier in ('../../private', '/home/private', 'router:password'):
            with self.assertRaises(ValueError):
                self.manager.control(identifier, 'delete')
        with self.assertRaises(ValueError):
            self.manager.control('router:ponytail', 'delete')

    def test_router_changes_only_selected_setting(self):
        with patch.object(self.manager, 'router', return_value={'ponytailEnabled': True}) as router:
            self.manager.control('router:ponytail', 'pause')
            router.assert_any_call('settings', 'PATCH', {'ponytailEnabled': False})
        backup = list(self.manager.backups.glob('*/setting.json'))
        self.assertEqual(json.loads(backup[0].read_text()), {'ponytailEnabled': True})

    def test_headroom_pause_does_not_kill_external_process(self):
        with patch.object(self.manager, 'router', return_value={'headroomEnabled': True}) as router:
            self.manager.control('router:headroom', 'pause')
            self.assertEqual(router.call_count, 2)
            router.assert_called_with('settings', 'PATCH', {'headroomEnabled': False})

    def test_reload_does_not_activate_paused_router_feature(self):
        with patch.object(self.manager, 'router', return_value={'ponytailEnabled': False}) as router:
            self.manager.control('router:ponytail', 'restart')
            router.assert_called_once_with('settings')
