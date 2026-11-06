import unittest
from unittest.mock import MagicMock, patch

import opencode_web


class OpenCodeWebTest(unittest.TestCase):
    def test_title_attributes_do_not_turn_running_service_into_port_conflict(self):
        for title in (b'<title>OpenCode</title>', b'<title data-sm>OpenCode</title>'):
            with self.subTest(title=title), \
                    patch.object(opencode_web.CLI.__class__, 'is_file', return_value=True), \
                    patch.object(opencode_web.socket, 'create_connection'), \
                    patch.object(opencode_web.urllib.request, 'urlopen') as request:
                response = MagicMock(status=200)
                response.read.return_value = b'<!doctype html><head>' + title + b'</head>'
                request.return_value.__enter__.return_value = response
                state = opencode_web.web_state()
                self.assertTrue(state['running'])
                self.assertFalse(state['conflict'])

    def test_another_application_is_still_a_port_conflict(self):
        with patch.object(opencode_web.socket, 'create_connection'), \
                patch.object(opencode_web.urllib.request, 'urlopen') as request:
            response = MagicMock(status=200)
            response.read.return_value = b'<title>Other application</title>'
            request.return_value.__enter__.return_value = response
            state = opencode_web.web_state()
            self.assertFalse(state['running'])
            self.assertTrue(state['conflict'])
