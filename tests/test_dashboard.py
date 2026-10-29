"""Renders the real dashboard against a temporary data folder; never touches local data."""
import datetime as dt
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app_runtime as r
import content_policy as policy
import pipeline as p


@unittest.skipIf(importlib.util.find_spec('streamlit') is None,'Streamlit not installed')
class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        data=Path(self.temp.name)/'data'
        for patcher in [patch.object(p,'DATA',data),patch.object(r,'STATE',data/'activity.json'),
                        patch.object(r,'LOG',data/'logs'/'activity.log'),
                        patch.object(r,'readiness',return_value=[dict(name='Ollama running',ok=True,detail='',fix='',required=True)])]:
            patcher.start(); self.addCleanup(patcher.stop)
        now=dt.datetime.now(dt.timezone.utc)
        p.write(data/'ranked-candidates.json',[dict(id=f'video{i:06d}',title=f'Champions League fan reaction {i}',
            url=f'https://www.youtube.com/watch?v=video{i:06d}',source=f'Channel {i//3}',channel_id=f'UC{i//3}',
            published=(now-dt.timedelta(hours=2)).isoformat(),views=50000,likes=2000,average_views_per_hour=20000,
            measured_views_per_hour=None,duration_seconds=300,priority_score=100-i,policy_version=policy.VERSION,
            defaultAudioLanguage='en',signal_label='Lifetime average; growth not yet measured') for i in range(30)])
        source='https://www.youtube.com/watch?v=LRm3E-2xF-0'
        p.write(data/'exports'/'old'/'job.json',dict(id='old',title='Earlier upload',source_url=source,start=10,end=40))
        p.write(data/'exports'/'old'/'upload.json',dict(state='uploaded',video_id='abc',uploaded_at=now.isoformat(),privacy='public'))
        p.write(data/'exports'/'repeat'/'job.json',dict(id='repeat',title='Repeated moment',source_url=source,start=12,end=42,
                                                         input='unused',made_for_kids=False,privacy='public'))
        (data/'exports'/'repeat'/'clip.mp4').write_bytes(b'preview')
        p.write(data/'exports'/'missing'/'job.json',dict(id='missing',title='Missing render',source_url='x',start=0,end=5))

    def run_app(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(p.ROOT/'dashboard.py'),default_timeout=60)
        app.run()
        self.assertFalse(app.exception,[x.value for x in app.exception])
        return app

    def test_shortlist_tabs_and_duplicate_warning(self):
        app=self.run_app()
        self.assertEqual([t.label for t in app.tabs],['1 · Find videos','2 · Make clips','3 · Review & publish','Published','Activity & settings'])
        choices=[x for x in app.expander if x.label.startswith('Champions League fan reaction')]
        self.assertEqual(len(choices),10)
        self.assertTrue(any('Already published from this moment' in x.value and 'youtu.be/abc' in x.value for x in app.warning))
        self.assertTrue(any('video file is missing' in x.value for x in app.warning))

    def test_use_this_video_stays_enabled_while_busy(self):
        import os
        p.write(r.STATE,dict(status='running',pid=os.getpid(),action='prepare',stage='Working'))
        app=self.run_app()
        use=[b for b in app.button if b.label=='Use this video']
        self.assertEqual(len(use),10)
        self.assertFalse(any(b.disabled for b in use))
        self.assertTrue(all(b.disabled for b in app.button if b.label=='Generate clips from this video'))


if __name__=='__main__': unittest.main()
