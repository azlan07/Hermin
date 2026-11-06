import unittest

from privacy_policy import BEGIN, END, native_config, policy_present, with_policy


class PrivacyPolicyTest(unittest.TestCase):
    def test_defaults_preserve_model_and_unrelated_security_settings(self):
        old = {"model": {"provider": "custom", "default": "example/model"},
               "security": {"allow_private_urls": False, "allow_lazy_installs": True},
               "approvals": {"mode": "off", "timeout": 120}, "command_allowlist": ["*"]}
        config = native_config(old)
        self.assertEqual(config["model"], old["model"])
        self.assertFalse(config["security"]["allow_private_urls"])
        self.assertFalse(config["security"]["allow_lazy_installs"])
        self.assertEqual(config["approvals"]["mode"], "manual")
        self.assertEqual(config["approvals"]["timeout"], 120)
        self.assertEqual(config["command_allowlist"], [])
        self.assertTrue(config["memory"]["write_approval"])
        self.assertTrue(config["skills"]["write_approval"])
        self.assertEqual(old["approvals"]["mode"], "off")

    def test_document_restore_is_idempotent_and_preserves_user_notes(self):
        for name in ("soul", "memory", "user_memory"):
            with self.subTest(name=name):
                once = with_policy(name, "Catatan penting milik pengguna.\n")
                self.assertEqual(once, with_policy(name, once))
                self.assertIn("Catatan penting milik pengguna.", once)
                self.assertEqual(once.count(BEGIN), 1)
                self.assertEqual(once.count(END), 1)

    def test_old_mount_instructions_removed_but_other_soul_sections_preserved(self):
        old = "Nama saya Hermes.\n\n## Izin akses host melalui HERMIN\nMinta mount.\n\n## Preferensi\nBahasa santai.\n"
        new = with_policy("soul", old)
        self.assertNotIn("Minta mount.", new)
        self.assertIn("Bahasa santai.", new)
        self.assertIn("TUNGGU", new)
        self.assertIn("bukan sandbox", new)

    def test_policy_status_requires_all_three_documents(self):
        texts = {name: with_policy(name, "") for name in ("soul", "memory", "user_memory")}
        self.assertTrue(policy_present(texts))
        texts["soul"] = "Belum ada instruksi"
        self.assertFalse(policy_present(texts))


if __name__ == "__main__":
    unittest.main()
