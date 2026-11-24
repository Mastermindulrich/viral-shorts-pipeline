import datetime as dt
import os
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import autopilot as ap
import content_policy as policy
import health
import learning
import pipeline as p
import scouting
import studio
import troubleshooting


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for target in [patch.object(p,'DATA',self.root/'data'),patch.object(p,'ROOT',self.root)]:
            target.start(); self.addCleanup(target.stop)


class DiagnoseTests(Sandbox):
    def test_real_failures_from_the_owners_mac_get_a_cause_and_strategy(self):
        cases={"('invalid_grant: Token has been expired or revoked.', {})":('youtube_signin',health.OWNER),
               '<HttpError 403 "you have exceeded your quota." reason quotaExceeded>':('youtube_quota',health.KEEP),
               'Daily upload cap reached (UTC)':('app_daily_cap',health.KEEP),
               '[Errno 32] Broken pipe':('upload_dropped',health.LATER),
               'No complete scenes passed the final context review. Try another source':('no_complete_scene',health.RETRY_BETTER),
               'English dialogue required for automatic editing.':('not_english',health.NEXT),
               'ERROR: [youtube] abc: Unable to extract nsig function':('downloader_outdated',health.RETRY_BETTER),
               'Use a finished video no longer than 20 minutes so the local workflow stays light':('source_refused',health.NEXT),
               'OSError: [Errno 28] No space left on device':('disk_full',health.RETRY_BETTER),
               'Ollama is not reachable at http://127.0.0.1:11434':('editor_down',health.RETRY_BETTER),
               'No "create post" box on the Posts tab':('posts_tab',health.OWNER),
               'Duplicate upload blocked: this clip repeats':('duplicate',health.SKIP),
               'Official rights-holder channel (HBO): skipped to avoid copyright claims':('copyright',health.NEXT),
               'something nobody has seen':('unknown',health.LATER)}
        for text,(cause,strategy) in cases.items():
            with self.subTest(text=text):
                found=health.diagnose(RuntimeError(text))
                self.assertEqual((found['id'],found['strategy']),(cause,strategy))
                self.assertTrue(found['cause'] and found['fix'])

    def test_record_counts_and_report_separates_what_needs_the_owner(self):
        health.record('publishing',RuntimeError('invalid_grant: Token has been expired'))
        health.record('clip-making',ValueError('No complete scenes passed the final context review'),dict(title='Video A',url='u'))
        health.record('clip-making',ValueError('No complete scenes passed the final context review'))
        report=health.report()
        self.assertEqual(report['status'],'needs_you')
        self.assertEqual([x['cause'] for x in report['needs_you']],['youtube_signin'])
        self.assertIn('pipeline.py auth',report['needs_you'][0]['owner'])
        self.assertEqual(report['handled'][0]['times'],2)
        health.resolved('youtube_signin')
        self.assertEqual(health.report()['status'],'fixed')
        self.assertIn('NEEDS YOU',health.report_text() if health.report()['needs_you'] else 'NEEDS YOU')

    def test_repeating_unknown_problem_is_raised_to_the_owner(self):
        for n in range(3): health.record('x',RuntimeError(f'weird thing {n} happened at 0xdeadbeef00'))
        self.assertEqual(health.report()['needs_you'][0]['cause'],'unknown')

    def test_tokens_are_redacted_in_incidents(self):
        health.record('x',RuntimeError('bad ya29.secretTOKEN123 here'))
        self.assertNotIn('ya29.secret',(p.DATA/'health'/'incidents.json').read_text())

    def test_troubleshooting_uses_the_diagnosis_for_otherwise_unknown_errors(self):
        answer=troubleshooting.explain(RuntimeError('[Errno 32] Broken pipe'))
        self.assertIn('connection dropped',answer['title'])


class BreakerTests(Sandbox):
    def test_optional_extra_pauses_after_three_failures_and_resets_on_success(self):
        for _ in range(2): health.failure('illustration','HTTP 400')
        self.assertTrue(health.allowed('illustration'))
        health.failure('illustration','HTTP 400')
        self.assertFalse(health.allowed('illustration'))
        self.assertTrue(health.allowed('illustration',now=dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=25)))
        health.success('illustration'); self.assertTrue(health.allowed('illustration'))

    def test_repairs_are_rate_limited(self):
        self.assertTrue(health._cooldown_ok('restart_editor',10))
        self.assertFalse(health._cooldown_ok('restart_editor',10))


class DiskTests(Sandbox):
    def test_free_space_deletes_only_sources_no_unposted_clip_needs(self):
        old=time.time()-86400
        for name in ('posted','waiting'):
            source=p.DATA/'imports'/name/'source.mp4'; source.parent.mkdir(parents=True); source.write_bytes(b'x'*1000)
            os.utime(source,(old,old))
            p.write(p.DATA/'jobs'/(name+'.json'),dict(id=name,input=str(source)))
        p.write(p.DATA/'exports'/'posted'/'upload.json',dict(state='uploaded'))
        with patch.object(health,'free_gb',return_value=1.0):
            health.free_space(target_gb=8)
        self.assertFalse((p.DATA/'imports'/'posted'/'source.mp4').exists())
        self.assertTrue((p.DATA/'imports'/'waiting'/'source.mp4').exists())
        self.assertTrue((p.DATA/'exports'/'posted'/'upload.json').exists())


class LearningTests(Sandbox):
    def test_channel_that_keeps_failing_is_paused_then_forgiven(self):
        item=dict(source='Montage Land',channel_id='UCm')
        for _ in range(2): learning.record_source(item,False,'No complete scene')
        self.assertEqual(learning.source_penalty(item),16)
        learning.record_source(item,False,'No complete scene')
        self.assertIsNone(learning.source_penalty(item))
        later=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=15)
        self.assertEqual(learning.source_penalty(item,later),24)
        learning.record_source(dict(channel_id='UCgood'),True)
        self.assertEqual(learning.source_penalty(dict(channel_id='UCgood')),0)

    def test_niche_performance_boosts_what_viewers_watch(self):
        for n,(title,views) in enumerate([('Messi goal reaction',9000),('Ronaldo football record',8000),('Champions League chaos',7000),
                                          ('GTA 6 gameplay chase',500),('GTA 6 gameplay glitch',400),('GTA 6 gameplay fail',300)]):
            p.write(p.DATA/'exports'/str(n)/'upload.json',dict(state='uploaded',video_id=f'v{n}'))
            p.write(p.DATA/'exports'/str(n)/'job.json',dict(title=title,input=str(p.DATA/'imports'/'x'/'source.mp4')))
            setattr(self,f'v{n}',views)
        service=MagicMock()
        service.videos().list().execute.return_value=dict(items=[dict(id=f'v{n}',statistics=dict(viewCount=str(getattr(self,f'v{n}')))) for n in range(6)])
        result=learning.refresh_niches(service,force=True)
        self.assertGreater(result['boost']['Football'],0)
        self.assertLess(result['boost']['GTA 6 and gaming'],0)
        self.assertGreater(learning.niche_boost('Football'),0)
        self.assertTrue(any('Football' in line for line in learning.summary()))


class DiscoveryTests(Sandbox):
    def test_shortlist_spans_niches_before_filling_up(self):
        items=[dict(id=f'g{n}',title=f'GTA 6 gameplay moment {n}',source=f'G{n}',display_score=100-n) for n in range(8)]
        items+=[dict(id='f',title='Messi reacts to Ronaldo goal',source='F',display_score=10),
                dict(id='w',title='Iran missile strike update',source='W',display_score=5)]
        picked=[x['id'] for x in scouting.shortlist(items,limit=5)]
        self.assertEqual(picked,['g0','g1','g2','f','w'])
        self.assertEqual(len(scouting.shortlist(items)),10)

    def test_clickable_buzzing_titles_rank_higher(self):
        now=dt.datetime.now(dt.timezone.utc)
        base=dict(published=now.isoformat(),views=50000,average_views_per_hour=5000,duration_seconds=300,priority_score=50,source='S')
        dull=dict(base,id='dull',title='stream highlights part 12')
        sharp=dict(base,id='sharp',title='Kai Cenat walks off stream after IShowSpeed prank',source='T')
        prefs=dict(scouting.DEFAULTS,categories=[],focus='')
        with patch.object(scouting,'newsdesk_terms',return_value=['IShowSpeed']):
            rows=scouting.filter_ranked([dull,sharp],prefs,now)
        self.assertEqual(rows[0]['id'],'sharp'); self.assertEqual(rows[0]['buzz'],'ishowspeed')

    def test_vary_niches_never_posts_the_same_niche_twice_in_a_row_when_avoidable(self):
        items=[dict(title='GTA 6 gameplay a',display_score=9),dict(title='GTA 6 gameplay b',display_score=8),
               dict(title='Messi goal',display_score=1)]
        order=[x['title'] for x in ap.vary_niches(items,recent=['GTA 6 and gaming'])]
        self.assertEqual(order,['Messi goal','GTA 6 gameplay a','GTA 6 gameplay b'])


class SmartRetryTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.defaults=dict(studio.DEFAULTS,count='auto',clearance='')
        self.item=dict(title='Interview',url='https://youtu.be/x',source='Chan')

    def test_no_complete_scene_retries_once_asking_for_the_single_best_moment(self):
        calls=[]
        def prepare(path,url,count,*a,**k):
            calls.append(count)
            if count!=1: raise ValueError('No complete scenes passed the final context review.')
            return [dict(id='job')]
        with patch('app_runtime.import_source',return_value=dict(input='in',source_url='u')), \
             patch('preparation.prepare',side_effect=prepare), patch('app_runtime.retry',side_effect=lambda f,l:f()):
            self.assertEqual(ap.make_clips(self.item,self.defaults,lambda *a:None),[dict(id='job')])
        self.assertEqual(calls,['auto',1])

    def test_outdated_downloader_is_upgraded_then_the_same_video_retried(self):
        attempts=[]
        def download(*a):
            attempts.append(1)
            if len(attempts)==1: raise ValueError('YouTube will not provide this video for download: Unable to extract nsig')
            return dict(input='in',source_url='u')
        with patch('app_runtime.import_source',side_effect=download), patch.object(health,'upgrade_downloader',return_value=True) as up, \
             patch.dict(health.REPAIRS,upgrade_downloader=lambda:up()), \
             patch('preparation.prepare',return_value=[dict(id='j')]), patch('app_runtime.retry',side_effect=lambda f,l:f()):
            ap.make_clips(self.item,self.defaults,lambda *a:None)
        self.assertEqual(len(attempts),2); up.assert_called_once()

    def test_mac_problem_stops_the_round_without_hiding_good_videos(self):
        picks=[dict(title='A',url='a',source='s'),dict(title='B',url='b',source='s')]
        with patch.object(ap,'ensure_editor'), patch.object(ap,'candidates',return_value=picks), \
             patch.object(studio,'preferences',return_value=self.defaults), \
             patch.object(ap,'make_clips',side_effect=OSError('[Errno 28] No space left on device')) as make, \
             patch.object(scouting,'hide_video') as hide:
            jobs,errors=ap.prepare_round(dict(ap.DEFAULTS),lambda *a:None)
        self.assertEqual(jobs,[]); self.assertEqual(make.call_count,1); hide.assert_not_called()
        self.assertTrue(any('Stopped this round' in e for e in errors))

    def test_video_problem_hides_it_and_teaches_the_channel_penalty(self):
        picks=[dict(title='A',url='a',source='Mono',channel_id='UCmono'),dict(title='B',url='b',source='Good',channel_id='UCgood')]
        def make(item,*a):
            if item['url']=='a': raise ValueError('English dialogue required for automatic editing.')
            return [dict(id='fresh')]
        with patch.object(ap,'ensure_editor'), patch.object(ap,'candidates',return_value=picks), \
             patch.object(studio,'preferences',return_value=self.defaults), patch.object(ap,'make_clips',side_effect=make), \
             patch.object(ap,'enqueue'), patch.object(scouting,'hide_video') as hide:
            jobs,errors=ap.prepare_round(dict(ap.DEFAULTS),lambda *a:None)
        self.assertEqual(jobs,[dict(id='fresh')]); hide.assert_called_once_with(picks[0])
        self.assertGreater(learning.source_penalty(picks[0]),0)


class UploadRecoveryTests(Sandbox):
    def job(self, ident='clip', title='A title'):
        dest=p.DATA/'exports'/ident
        p.write(dest/'job.json',dict(id=ident,title=title))
        return dest

    def test_unconfirmed_upload_is_released_only_when_youtube_never_got_it(self):
        p.write(p.ROOT/'config'/'settings.json',dict(expected_channel_id='UC1',max_uploads_per_day=20))
        old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=3)).isoformat()
        lost=self.job('lost','Lost upload'); p.write(lost/'upload.json',dict(state='uploading',attempted_at=old))
        landed=self.job('landed','Landed upload'); p.write(landed/'upload.json',dict(state='uploading',attempted_at=old))
        fresh=self.job('fresh','Fresh'); p.write(fresh/'upload.json',dict(state='uploading',attempted_at=dt.datetime.now(dt.timezone.utc).isoformat()))
        with patch.object(p,'api_recent_uploads',return_value=[dict(id='v',title='Landed upload',published=dt.datetime.now(dt.timezone.utc).isoformat())]):
            self.assertEqual(p.release_unconfirmed(),['lost'])
        self.assertFalse((lost/'upload.json').exists()); self.assertTrue(list(lost.glob('upload-unconfirmed-*.json')))
        self.assertTrue((landed/'upload.json').exists()); self.assertTrue((fresh/'upload.json').exists())

    def test_api_failure_releases_nothing(self):
        p.write(p.ROOT/'config'/'settings.json',dict(expected_channel_id='UC1'))
        dest=self.job(); p.write(dest/'upload.json',dict(state='uploading',attempted_at='2020-01-01T00:00:00+00:00'))
        with patch.object(p,'api_recent_uploads',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError): p.release_unconfirmed()
        self.assertTrue((dest/'upload.json').exists())

    def test_dropped_connection_mid_upload_resumes_the_same_session(self):
        import sys
        chunks=[BrokenPipeError(32,'Broken pipe'),ConnectionResetError('reset'),(None,dict(id='vid',snippet={}))]
        request=MagicMock()
        def next_chunk(num_retries):
            value=chunks.pop(0)
            if isinstance(value,Exception): raise value
            return value
        request.next_chunk.side_effect=next_chunk
        service=MagicMock(); service.videos().insert.return_value=request
        discovery=types.ModuleType('googleapiclient.discovery'); discovery.build=lambda *a,**k:service
        http=types.ModuleType('googleapiclient.http'); http.MediaFileUpload=lambda *a,**k:None
        p.write(p.ROOT/'config'/'settings.json',dict(expected_channel_id='UC1',max_uploads_per_day=20))
        job=dict(id='clip',title='T',source_url='u',start=0,end=20,made_for_kids=False,privacy='public')
        with patch.dict(sys.modules,{'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':discovery,'googleapiclient.http':http}), \
             patch.object(p,'check_approval'), patch.object(p,'upload_conflicts',return_value=[]), patch.object(p,'credentials'), \
             patch.object(p,'verify_channel'), patch.object(p,'fingerprint',return_value='sha'), patch.object(p,'upload_sleep') as wait:
            p.output(job).mkdir(parents=True,exist_ok=True)
            p.upload(job)
        self.assertEqual(p.read(p.output(job)/'upload.json')['state'],'uploaded'); self.assertEqual(wait.call_count,2)


class CopyrightDiscoveryTests(unittest.TestCase):
    def test_topic_queries_no_longer_ask_for_official_cuts(self):
        queries=' '.join(x['query'] for x in policy.TOPICS).lower()
        self.assertNotIn('official movie trailer',queries)
        self.assertNotIn('film clip',queries)


if __name__=='__main__':
    unittest.main()
