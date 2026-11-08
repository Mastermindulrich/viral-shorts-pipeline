"""Step 1 never offers, and the download step never fetches, live, unfinished, too-long or restricted videos."""
import datetime as dt
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import app_runtime as r
import content_policy as policy
import pipeline as p
import preparation as prep
import scouting


class SourceProblemTests(unittest.TestCase):
    def test_policy_rejects_unprocessable_sources(self):
        ok=dict(duration_seconds=600,live_status='none',privacy='public',upload_status='processed')
        self.assertEqual(policy.source_problem(ok),'')
        self.assertEqual(policy.source_problem(dict(ok,live_started='x',live_ended='y')),'')
        for change,word in [(dict(live_status='live'),'live'),(dict(live_status='upcoming'),'live'),
                            (dict(live_started='2026-11-08T10:00:00Z',live_ended=''),'live'),
                            (dict(duration_seconds=policy.MAX_SOURCE_SECONDS+1),'20 minutes'),
                            (dict(duration_seconds=10),'Shorter'),(dict(age_restricted=True),'Age'),
                            (dict(privacy='unlisted'),'public'),(dict(upload_status='uploaded'),'processing'),
                            (dict(region_blocked=True),'region'),(dict(unsupported='Sign in'),'downloaded')]:
            with self.subTest(change=change):
                self.assertIn(word,policy.source_problem(dict(ok,**change)))

    def test_saved_long_results_disappear_from_the_shortlist(self):
        now=dt.datetime(2026,11,8,12,tzinfo=dt.timezone.utc)
        item=dict(id='v',title='Champions League goal reaction',source='Fans',published=(now-dt.timedelta(hours=2)).isoformat(),
                  views=20000,average_views_per_hour=10000,measured_views_per_hour=None,priority_score=90,duration_seconds=600)
        prefs=dict(scouting.DEFAULTS)
        self.assertEqual(len(scouting.filter_ranked([item],prefs,now)),1)
        self.assertEqual(scouting.filter_ranked([dict(item,duration_seconds=25*60)],prefs,now),[])
        self.assertEqual(scouting.filter_ranked([dict(item,live_status='live')],prefs,now),[])

    def test_refresh_drops_live_unfinished_and_long_videos_with_reasons(self):
        service=MagicMock()
        snippet=dict(publishedAt='2026-11-08T00:00:00Z',channelTitle='Creator',defaultAudioLanguage='en',liveBroadcastContent='none')
        service.videos.return_value.list.return_value.execute.return_value={'items':[
            dict(id='good',snippet=dict(snippet,title='Interview moment'),statistics={'viewCount':'100'},contentDetails={'duration':'PT8M'},status={'privacyStatus':'public','uploadStatus':'processed'}),
            dict(id='live',snippet=dict(snippet,title='Live now',liveBroadcastContent='live'),statistics={},contentDetails={'duration':'P0D'}),
            dict(id='ended',snippet=dict(snippet,title='Stream still processing'),statistics={},contentDetails={'duration':'PT9M'},liveStreamingDetails={'actualStartTime':'2026-11-08T00:00:00Z'}),
            dict(id='long',snippet=dict(snippet,title='Full podcast'),statistics={},contentDetails={'duration':'PT1H10M'}),
            dict(id='age',snippet=dict(snippet,title='Restricted'),statistics={},contentDetails={'duration':'PT5M','contentRating':{'ytRating':'ytAgeRestricted'}}),
            dict(id='region',snippet=dict(snippet,title='Blocked'),statistics={},contentDetails={'duration':'PT5M','regionRestriction':{'blocked':['CA']}})]}
        modules={'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}
        ids=['good','live','ended','long','age','region']
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.object(p,'credentials',return_value=None),patch.dict('sys.modules',modules):
            p.write(p.DATA/'candidates.json',[dict(id=x,title=x,source='Creator',url='https://www.youtube.com/watch?v='+x) for x in ids])
            result=scouting.refresh()
            self.assertEqual([x['id'] for x in result],['good'])
            self.assertEqual(result[0]['duration_seconds'],480)
            reasons={x['id']:x['reason'] for x in p.read(p.DATA/'scouting-exclusions.json')}
        self.assertEqual(set(reasons),set(ids)-{'good'})
        self.assertIn('20 minutes',reasons['long'])
        self.assertIn('live',reasons['ended'])
        part=service.videos.return_value.list.call_args.kwargs['part']
        self.assertIn('liveStreamingDetails',part)

    def test_unsupported_video_is_remembered_and_hidden_from_scans(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.object(r,'STATE',Path(td)/'state.json'):
            with patch.object(prep,'import_video',side_effect=ValueError('This video is age-restricted')):
                with self.assertRaises(ValueError): r.import_source('https://youtu.be/LRm3E-2xF-0',title='Restricted clip')
            self.assertIn('LRm3E-2xF-0',scouting.unsupported_videos())
            item=dict(id='LRm3E-2xF-0',policy_version=policy.VERSION,title='Restricted clip')
            self.assertEqual(scouting.visible_ranked([item]),[])


class FakeYDL:
    downloads=[]
    def __init__(self,info): self.info=info
    def __call__(self,opts): return self
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def extract_info(self,url,download=False): return dict(self.info)
    def process_ie_result(self,info,download=True): FakeYDL.downloads.append(info); return info


class ImportScreeningTests(unittest.TestCase):
    def run_import(self,info):
        FakeYDL.downloads=[]
        class DownloadError(Exception): pass
        modules={'yt_dlp':types.SimpleNamespace(YoutubeDL=FakeYDL(info)),'yt_dlp.utils':types.SimpleNamespace(DownloadError=DownloadError)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.dict('sys.modules',modules):
            try: prep.import_video('https://youtu.be/LRm3E-2xF-0')
            finally: folder_created=(Path(td)/'imports'/'LRm3E-2xF-0').exists()
        return folder_created

    def test_live_long_and_restricted_videos_stop_before_download(self):
        base=dict(title='Interview',duration=600,live_status='not_live',availability='public',age_limit=0)
        for change in [dict(is_live=True),dict(live_status='post_live'),dict(live_status='is_upcoming'),
                       dict(duration=policy.MAX_SOURCE_SECONDS+60),dict(duration=None),
                       dict(availability='subscriber_only'),dict(age_limit=18)]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError): self.run_import(dict(base,**change))
                self.assertEqual(FakeYDL.downloads,[])

    def test_refused_download_messages_are_not_retried(self):
        self.assertTrue(prep.download_refused(Exception('ERROR: Sign in to confirm your age')))
        self.assertTrue(prep.download_refused(Exception('Private video')))
        self.assertFalse(prep.download_refused(Exception('Read timed out')))
        self.assertFalse(r.transient(ValueError('YouTube will not provide this video for download')))


class FastRoundTests(unittest.TestCase):
    def test_auto_run_reuses_a_recent_scan(self):
        now=dt.datetime.now(dt.timezone.utc)
        item=dict(id='abcdefghijk',url='https://www.youtube.com/watch?v=abcdefghijk',title='Fresh',policy_version=policy.VERSION)
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)):
            p.write(p.DATA/'ranked-candidates.json',[item])
            p.write(p.DATA/'discovery-rotation.json',dict(last_scan=now.isoformat()))
            with patch.object(scouting,'visible_ranked',side_effect=lambda x:x):
                self.assertEqual(len(r.fresh_choices(scouting,set())),1)
                self.assertEqual(r.fresh_choices(scouting,{item['url']}),[])
                p.write(p.DATA/'discovery-rotation.json',dict(last_scan=(now-dt.timedelta(hours=1)).isoformat()))
                self.assertEqual(r.fresh_choices(scouting,set()),[])

    def test_non_english_source_stops_before_transcribing(self):
        consumed=[]
        def segments():
            consumed.append(1); yield types.SimpleNamespace(start=0,end=1,text='Bonjour',words=[])
        model=types.SimpleNamespace(transcribe=lambda *a,**k:(segments(),types.SimpleNamespace(language='fr',language_probability=.97,duration=600)))
        modules={'faster_whisper':types.SimpleNamespace(WhisperModel=lambda *a,**k:model)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)/'data'),patch.dict('sys.modules',modules):
            source=Path(td)/'source.mp4'; source.write_bytes(b'video')
            with self.assertRaisesRegex(ValueError,'English'): prep.prepare(source,'test',model='small',editor='semantic')
        self.assertEqual(consumed,[])


if __name__=='__main__': unittest.main()
