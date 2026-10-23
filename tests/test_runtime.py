import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app_runtime as r
import pipeline as p

class RuntimeTests(unittest.TestCase):
    def test_dead_process_is_interrupted(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'STATE',Path(folder)/'state.json'):
            p.write(r.STATE,dict(status='running',pid=123))
            with patch('os.kill',side_effect=ProcessLookupError):
                self.assertEqual(r.active()['status'],'interrupted')

    def test_unknown_action_fails_without_dispatch(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p,'DATA',Path(folder)),patch.object(r,'STATE',Path(folder)/'state.json'):
            import os
            p.write(r.STATE,dict(status='running',pid=os.getpid()))
            request=Path(folder)/'request.json'; p.write(request,dict(action='unknown',payload={}))
            r.execute(request)
            self.assertEqual(p.read(r.STATE)['status'],'failed')

    def test_diagnostics_redacts_tokens(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'LOG',Path(folder)/'log'),patch.object(r,'active',return_value={}):
            r.LOG.write_text('access_token: secret-value\nrefresh_token: another-secret\nya29.sensitive')
            text=r.diagnostics()
            self.assertNotIn('secret-value',text); self.assertNotIn('another-secret',text); self.assertNotIn('ya29.sensitive',text)
