import datetime as dt
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import autopilot as ap
import content_policy as policy
import pipeline as p
import scouting as s
import studio


class FocusTests(unittest.TestCase):
    def test_gta6_titles_match_focus(self):
        for title in ('GTA 6 funny moments','gta vi police chase','My first hour in GTA6','Grand Theft Auto VI gameplay'):
            self.assertTrue(policy.is_focus({'title':title}),title)
        for title in ('GTA 5 online heist','Fortnite gameplay','Top 60 facts'):
            self.assertFalse(policy.is_focus({'title':title}),title)

    def test_focus_videos_pass_category_filter_and_rank_first(self):
        now=dt.datetime.now(dt.timezone.utc)
        base=dict(published=(now-dt.timedelta(hours=5)).isoformat(),views=50000,average_views_per_hour=9000,
                  duration_seconds=600,source='Creator')
        items=[dict(base,id='a',title='Champions League goal reaction',priority_score=60),
               dict(base,id='b',title='GTA 6 police chase gone wrong',priority_score=50,source='Gamer')]
        prefs=dict(s.DEFAULTS,categories=['Champions League and football'])
        ranked=s.filter_ranked(items,prefs,now)
        self.assertEqual([x['id'] for x in ranked],['b','a'])
        self.assertTrue(ranked[0]['focus'])
        self.assertEqual([x['id'] for x in s.filter_ranked(items,dict(prefs,focus=''),now)],['a'])

    def test_focus_takes_most_of_the_search_budget(self):
        service=MagicMock()
        service.videos.return_value.list.return_value.execute.return_value={'items':[]}
        service.search.return_value.list.return_value.execute.return_value={'items':[]}
        modules={'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}
        with tempfile.TemporaryDirectory() as td, patch.object(p,'ROOT',Path(td)), patch.object(p,'DATA',Path(td)/'data'), \
             patch.object(s,'preferences',return_value=dict(s.DEFAULTS,categories=[])), patch.object(p,'credentials',return_value=None), \
             patch.dict('sys.modules',modules):
            p.write(Path(td)/'config'/'discovery.json',dict(searches_per_scan=4,regions=['US'],topics=[dict(name='Other',query='other')]))
            first=s.discover_broad(); second=s.discover_broad()
            self.assertEqual(first['searched_topics'][:3],[policy.FOCUS['name']]*3)
            self.assertEqual(len(first['searched_topics']),4)
            queries=[c.kwargs['q'] for c in service.search.return_value.list.call_args_list if 'GTA' in c.kwargs['q']]
            self.assertEqual(len(set(queries)),6)  # the focus queries rotate between scans
            self.assertTrue(all('GTA 6' in q for q in queries))


class ScheduleTests(unittest.TestCase):
    def test_due_count_follows_slots(self):
        cfg=dict(ap.DEFAULTS)
        at=lambda h: dt.datetime(2026,11,22,h,30)
        self.assertEqual([ap.due_by(at(h),cfg) for h in (8,11,15,16,20,23)],[0,1,1,2,3,3])
        self.assertEqual(ap.due_by(at(21),dict(cfg,daily_target=5)),5)

    def test_plist_runs_hourly_and_keeps_the_mac_awake(self):
        spec=ap.plist('/Users/x/vmc','/Users/x/vmc/.venv/bin/python')
        self.assertEqual(spec['ProgramArguments'][:2],['/usr/bin/caffeinate','-i'])
        self.assertEqual(spec['ProgramArguments'][-1],'autopilot-tick')
        self.assertEqual(spec['StartCalendarInterval'],[{'Minute':7}])


class RunTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); root=Path(self.td.name)
        self.patches=[patch.object(p,'DATA',root/'data'),patch.object(ap,'SETTINGS',root/'data'/'autopilot-settings.json'),
                      patch.object(ap,'STATE',root/'data'/'autopilot.json'),patch.object(ap,'QUEUE',root/'data'/'autopilot-queue.json'),
                      patch.object(p,'reconcile_receipts',return_value=0),
                      patch.object(studio,'preferences',return_value=dict(studio.DEFAULTS,timezone='UTC'))]
        for x in self.patches: x.start()
        self.uploaded=[]

    def tearDown(self):
        for x in self.patches: x.stop()
        self.td.cleanup()

    def clip(self, ident, queued=True):
        dest=p.DATA/'exports'/ident
        p.write(dest/'job.json',dict(id=ident,title='GTA 6 moment',input=str(p.DATA/'imports'/'v'/'source.mp4'),source_url='u'))
        (dest/'clip.mp4').write_bytes(b'x')
        if queued: ap.enqueue([dict(id=ident)])

    def fake_publish(self, ident):
        p.write(p.DATA/'exports'/ident/'upload.json',dict(state='uploaded',uploaded_at=dt.datetime.now(dt.timezone.utc).isoformat(),video_id='vid'+ident))
        self.uploaded.append(ident); return 'vid'+ident

    def test_publishes_only_due_autopilot_clips(self):
        self.clip('one'); self.clip('two'); self.clip('three'); self.clip('manual',queued=False)
        noon=dt.datetime.now(dt.timezone.utc).replace(hour=17,minute=0)
        with patch.object(ap,'publish',side_effect=self.fake_publish), patch.object(ap,'local_now',return_value=noon), \
             patch.object(ap,'prepare_round',return_value=([],[])) as prepare:
            ap.save_settings(dict(post_extra=False))
            result=ap.run()
        self.assertEqual(self.uploaded,['one','two'])
        self.assertEqual(result['published_today'],2)
        prepare.assert_not_called()  # one clip is still ready for the evening slot

    def test_surplus_clips_go_out_one_extra_per_tick(self):
        for name in ('one','two','three','four'): self.clip(name)
        afternoon=dt.datetime.now(dt.timezone.utc).replace(hour=17,minute=0)
        with patch.object(ap,'publish',side_effect=self.fake_publish), patch.object(ap,'local_now',return_value=afternoon), \
             patch.object(ap,'prepare_round',return_value=([],[])):
            ap.run()
            self.assertEqual(self.uploaded,['one','two','three'])  # 2 due + 1 extra
            ap.run()
            self.assertEqual(self.uploaded,['one','two','three','four'])  # next tick: another extra
        night=afternoon.replace(hour=3)
        self.clip('five')
        with patch.object(ap,'publish',side_effect=self.fake_publish), patch.object(ap,'local_now',return_value=night), \
             patch.object(ap,'prepare_round',return_value=([],[])):
            ap.run()
        self.assertNotIn('five',self.uploaded)  # no extras overnight

    def test_short_queue_prepares_more_and_failed_clip_is_skipped(self):
        self.clip('dup')
        evening=dt.datetime.now(dt.timezone.utc).replace(hour=21,minute=0)
        def publish(ident):
            if ident=='dup': raise ValueError('Duplicate upload blocked')
            return self.fake_publish(ident)
        def prepare(cfg,stage):
            n=len(list((p.DATA/'exports').glob('new*')))
            jobs=[]
            for k in range(2):
                self.clip(f'new{n+k}',queued=False); jobs.append(dict(id=f'new{n+k}'))
            ap.enqueue(jobs); return jobs,[]
        with patch.object(ap,'publish',side_effect=publish), patch.object(ap,'local_now',return_value=evening), \
             patch.object(ap,'prepare_round',side_effect=prepare):
            result=ap.run()
        self.assertEqual(result['published_today'],3)
        self.assertIn('dup',ap.queue()['skipped'])

    def test_daily_cap_keeps_the_clip_for_later(self):
        self.clip('one')
        evening=dt.datetime.now(dt.timezone.utc).replace(hour=21,minute=0)
        with patch.object(ap,'publish',side_effect=ValueError('Daily upload cap reached (UTC)')), \
             patch.object(ap,'local_now',return_value=evening), patch.object(ap,'prepare_round',return_value=([],['none'])):
            with self.assertRaises(RuntimeError): ap.run()
        self.assertEqual(ap.ready(),['one'])
        self.assertTrue(ap.status()['errors'])

    def test_youtube_quota_error_keeps_the_clip(self):
        self.clip('one')
        evening=dt.datetime.now(dt.timezone.utc).replace(hour=21,minute=0)
        error=RuntimeError('<HttpError 403 "The request cannot be completed because you have exceeded your quota." reason quotaExceeded>')
        with patch.object(ap,'publish',side_effect=error), patch.object(ap,'local_now',return_value=evening), \
             patch.object(ap,'prepare_round',return_value=([],[])):
            with self.assertRaises(RuntimeError): ap.run()
        self.assertEqual(ap.ready(),['one'])
        self.assertEqual(ap.queue()['skipped'],{})

    def test_upload_quota_refusal_releases_the_receipt(self):
        import pipeline
        dest=p.DATA/'exports'/'q'
        job=dict(id='q',title='GTA 6 moment',start=0,end=20,source_url='u',made_for_kids=False,privacy='public')
        p.write(dest/'job.json',job)
        request=MagicMock(); request.next_chunk.side_effect=RuntimeError('HttpError 403 quotaExceeded')
        service=MagicMock(); service.videos.return_value.insert.return_value=request
        modules={'googleapiclient':types.ModuleType('googleapiclient'),
                 'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service),
                 'googleapiclient.http':types.SimpleNamespace(MediaFileUpload=lambda *a,**k:None)}
        with tempfile.TemporaryDirectory() as td, patch.object(p,'ROOT',Path(td)), patch.dict('sys.modules',modules), \
             patch.object(p,'check_approval'), patch.object(p,'upload_conflicts',return_value=[]), \
             patch.object(p,'credentials'), patch.object(p,'verify_channel'):
            p.write(Path(td)/'config'/'settings.json',dict(max_uploads_per_day=20,expected_channel_id='x'))
            with self.assertRaisesRegex(RuntimeError,'quota'): pipeline.upload(job)
        self.assertFalse((dest/'upload.json').exists())

    def test_off_does_nothing(self):
        ap.save_settings(dict(enabled=False))
        self.assertEqual(ap.run(),dict(status='off'))

    def test_credit_names_creator_and_tags_gta(self):
        source=p.DATA/'imports'/'v'/'source.json'
        p.write(source,dict(title='GTA 6 first hour',creator='SomeGamer',description=''))
        description,gta=ap.credit(dict(input=str(source.parent/'source.mp4'),title='Wild chase'))
        self.assertTrue(gta)
        self.assertIn('SomeGamer',description)
        self.assertIn('#GTA6',description)


class UploadCategoryTests(unittest.TestCase):
    def test_upload_uses_job_category(self):
        import inspect
        self.assertIn("job.get('category_id') or '24'",inspect.getsource(p.upload))


if __name__=='__main__':
    unittest.main()
