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
            with patch.object(r.traceback,'print_exc'):
                r.execute(request)
            self.assertEqual(p.read(r.STATE)['status'],'failed')

    def test_diagnostics_redacts_tokens(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'LOG',Path(folder)/'log'),patch.object(r,'active',return_value={}):
            r.LOG.write_text('access_token: secret-value\nrefresh_token: another-secret\nya29.sensitive')
            text=r.diagnostics()
            self.assertNotIn('secret-value',text); self.assertNotIn('another-secret',text); self.assertNotIn('ya29.sensitive',text)

    def test_update_reports_failing_test_and_saves_output(self):
        import subprocess
        output='ERROR: test_render (test_pipeline.PipelineTests)\nTraceback: example failure\nFAILED (errors=1)\n'
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'LOG',Path(folder)/'activity.log'), \
             patch.object(r,'stage'), patch('builtins.print'), patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stdout=output)):
            with self.assertRaisesRegex(RuntimeError,'test_render'):
                r.run_update_checks()
            self.assertEqual((Path(folder)/'update-checks.log').read_text(),output)

    def test_update_checks_accept_success_with_optional_skip(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'LOG',Path(folder)/'activity.log'), \
             patch.object(r,'stage'), patch('builtins.print'), patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='OK (skipped=1)')):
            r.run_update_checks()


class ResilienceTests(unittest.TestCase):
    def test_retry_recovers_from_transient_failure(self):
        calls=[]
        def flaky():
            calls.append(1)
            if len(calls)<3: raise ConnectionError('connection reset by peer')
            return 'ok'
        with patch.object(r,'stage'):
            self.assertEqual(r.retry(flaky,'Test',sleep=lambda s:None),'ok')
        self.assertEqual(len(calls),3)

    def test_retry_never_repeats_policy_errors(self):
        calls=[]
        def blocked():
            calls.append(1); raise ValueError('Music video excluded')
        with patch.object(r,'stage'), self.assertRaises(ValueError):
            r.retry(blocked,'Test',sleep=lambda s:None)
        self.assertEqual(len(calls),1)

    def test_retry_gives_up_after_attempts(self):
        def down(): raise TimeoutError('timed out')
        with patch.object(r,'stage'), self.assertRaises(TimeoutError):
            r.retry(down,'Test',attempts=2,sleep=lambda s:None)

    def test_discard_clip_removes_draft_but_keeps_published(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p,'DATA',Path(folder)):
            data=Path(folder)
            p.write(data/'exports'/'a'/'job.json',{}); p.write(data/'jobs'/'a.json',{})
            p.discard_clip('a')
            self.assertFalse((data/'exports'/'a').exists()); self.assertFalse((data/'jobs'/'a.json').exists())
            p.write(data/'exports'/'b'/'upload.json',{})
            with self.assertRaises(ValueError): p.discard_clip('b')

    def test_reconcile_marks_matching_upload_without_reuploading(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder); dest=data/'exports'/'job1'
            p.write(dest/'job.json',dict(title='Big moment'))
            p.write(dest/'upload.json',dict(state='uploading',attempted_at='2026-10-29T10:00:00+00:00'))
            recent=[dict(id='abc',title='Big moment',published='2026-10-29T10:05:00Z')]
            with patch.object(p,'DATA',data), patch.object(p,'recent_uploads',return_value=recent):
                self.assertEqual(p.reconcile_receipts(),1)
                receipt=p.read(dest/'upload.json')
            self.assertEqual((receipt['state'],receipt['video_id']),('uploaded','abc'))
