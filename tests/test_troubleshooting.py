import unittest
from unittest.mock import patch
from pathlib import Path
import troubleshooting as t


class TroubleshootingTests(unittest.TestCase):
    def test_expired_auth_has_exact_local_command_and_keeps_clips(self):
        with patch.object(t.p,'ROOT',Path('/Users/test/My Project')):
            help=t.explain("invalid_grant: Token has been expired or revoked.")
        self.assertIn("cd '/Users/test/My Project'",help['command'])
        self.assertIn('pipeline.py auth',help['command'])
        self.assertIn('saved',help['title'])
        self.assertTrue(any('Verify YouTube connection' in x for x in help['steps']))

    def test_unknown_error_does_not_echo_secret_or_invent_cause(self):
        help=t.explain('secret-value-123 obscure failure')
        self.assertNotIn('secret-value',str(help))
        self.assertIn('needs checking',help['title'])
        self.assertTrue(any('diagnostics' in x for x in help['steps']))

    def test_common_failures_have_specific_remedies(self):
        cases=[('Ollama is not running','local AI editor'),('Duplicate upload blocked','same clip twice'),
               ('Daily upload cap reached','daily publishing limit'),('quotaExceeded','limiting'),
               ('No complete scenes passed the final context review','spoken scene'),
               ('No space left on device','storage'),('ffmpeg not found','video-processing'),
               ('Use a finished video no longer than 20 minutes','too long'),
               ('Update validation failed','update'),('Another task is running','job')]
        for error,title in cases:
            with self.subTest(error=error):
                help=t.explain(error)
                self.assertIn(title,help['title'])
                self.assertGreaterEqual(len(help['steps']),2)

    def test_uncertain_upload_never_recommends_deleting_records(self):
        help=t.explain('Upload already attempted')
        self.assertTrue(any('Do not delete upload records' in x for x in help['steps']))
