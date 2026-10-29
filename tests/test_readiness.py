import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app_runtime as r
import editorial as e
import pipeline as p


def tags(*names):
    return io.BytesIO(json.dumps(dict(models=[dict(name=x) for x in names])).encode())


class OllamaPreflightTests(unittest.TestCase):
    def test_installed_model_passes_including_latest_tag(self):
        with patch.object(e.urllib.request,'urlopen',return_value=tags('qwen2.5:7b','llama3:latest')):
            e.require_model('qwen2.5:7b')
        with patch.object(e.urllib.request,'urlopen',return_value=tags('llama3:latest')):
            e.require_model('llama3')

    def test_missing_model_and_stopped_ollama_give_exact_commands(self):
        with patch.object(e.urllib.request,'urlopen',return_value=tags('llama3:latest')):
            with self.assertRaisesRegex(RuntimeError,'ollama pull qwen2.5:7b'): e.require_model('qwen2.5:7b')
        with patch.object(e.urllib.request,'urlopen',side_effect=OSError('refused')):
            with self.assertRaisesRegex(RuntimeError,'Ollama is not running'): e.require_model('qwen2.5:7b')

    def test_cloud_models_still_rejected(self):
        with patch.object(e.urllib.request,'urlopen') as urlopen:
            with self.assertRaises(ValueError): e.require_model('gpt-oss:120b-cloud')
        urlopen.assert_not_called()

    def test_prepare_task_stops_before_download_when_editor_missing(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(p,'DATA',Path(folder)),patch.object(r,'STATE',Path(folder)/'state.json'):
            p.write(r.STATE,dict(status='running',pid=os.getpid()))
            request=Path(folder)/'request.json'
            p.write(request,dict(action='prepare',payload=dict(url='https://youtu.be/LRm3E-2xF-0',clearance='ref')))
            import preparation as prep
            with patch.object(e.urllib.request,'urlopen',side_effect=OSError('refused')), \
                 patch.object(prep,'import_video') as download,patch.object(r.traceback,'print_exc'),patch('builtins.print'):
                r.execute(request)
            download.assert_not_called()
            self.assertIn('Ollama',p.read(r.STATE)['error'])


class ReadinessTests(unittest.TestCase):
    def test_report_lists_fixes_without_reading_credentials(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(p,'DATA',Path(folder)), \
             patch.object(e.urllib.request,'urlopen',side_effect=OSError('refused')):
            p.write(p.DATA/'secrets'/'token.json',dict(refresh_token='do-not-show'))
            checks=r.readiness('qwen2.5:7b')
            report=r.readiness_report(checks)
        by_name={x['name']:x for x in checks}
        self.assertTrue(by_name['YouTube authorization']['ok'])
        self.assertFalse(by_name['Ollama running']['ok'])
        self.assertIn('ollama pull qwen2.5:7b',report)
        self.assertNotIn('do-not-show',report)
        self.assertFalse(by_name['Burned-in English subtitles']['required'])

    def test_missing_token_points_to_browser_sign_in(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(p,'DATA',Path(folder)), \
             patch.object(e.urllib.request,'urlopen',return_value=tags('qwen2.5:7b')):
            checks={x['name']:x for x in r.readiness('qwen2.5:7b')}
        self.assertTrue(checks['Local AI editor model']['ok'])
        self.assertIn('pipeline.py auth',checks['YouTube authorization']['fix'])


if __name__=='__main__': unittest.main()
