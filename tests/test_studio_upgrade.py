import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pipeline as p
import scouting as s
import studio
import editorial as e
import preparation as prep
import test_editorial as fixtures


class DiscoveryFilterTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,29,16,tzinfo=dt.timezone.utc)
        self.item=dict(id='v',title='Champions League incredible goal fan reaction',source='Fan moments',
            published=(self.now-dt.timedelta(hours=2)).isoformat(),views=20000,likes=1000,
            average_views_per_hour=10000,measured_views_per_hour=None,duration_seconds=120,priority_score=90)
        self.prefs=copy.deepcopy(s.DEFAULTS)

    def test_old_weak_nonmatching_and_blocked_sources_excluded(self):
        cases=[(dict(self.item,published=(self.now-dt.timedelta(days=4)).isoformat()),{}),
               (dict(self.item,views=100),{}),
               (dict(self.item,measured_views_per_hour=1),{}),
               (dict(self.item,duration_seconds=10),{}),
               (self.item,dict(categories=['Engineering hacks'])),
               (self.item,dict(exclude_keywords='goal, trailer')),
               (self.item,dict(include_keywords='mbappe')),
               (self.item,dict(blocked_channels='Fan moments')),
               (dict(self.item,source='UEFA'),dict(source_preference='Exclude likely official'))]
        for item,changes in cases:
            with self.subTest(changes=changes,item=item):
                self.assertEqual(s.filter_ranked([item],dict(self.prefs,**changes),self.now),[])
        self.assertEqual(len(s.filter_ranked([self.item],self.prefs,self.now)),1)

    def test_unofficial_is_an_estimate_and_preference_not_a_prohibition(self):
        official=dict(self.item,id='official',source='UEFA')
        rows=s.filter_ranked([official,self.item],self.prefs,self.now)
        self.assertEqual(rows[0]['id'],'v')
        self.assertEqual(len(rows),2)
        self.assertIn('Unverified',rows[0]['source_type'])

    def test_measured_momentum_beats_old_lifetime_popularity(self):
        fresh=dict(self.item,id='fresh')
        stale=dict(self.item,id='stale',published=(self.now-dt.timedelta(days=20)).isoformat(),views=2000000)
        previous={'stale':dict(views=1999999,observed_at=(self.now-dt.timedelta(hours=1)).isoformat())}
        rows=s.rank([stale,fresh],previous,self.now)
        self.assertEqual(rows[0]['id'],'fresh')
        self.assertIn('not yet measured',rows[0]['signal_label'])

    def test_ten_choices_channel_diversity_and_no_duplicate_titles(self):
        items=[dict(self.item,id=str(i),source='Channel '+str(i//3),title='Goal '+str(i)) for i in range(30)]
        result=s.shortlist(items)
        self.assertEqual(len(result),10)
        self.assertTrue(all(sum(x['source']==y['source'] for x in result)<=2 for y in result))
        self.assertEqual(len(s.shortlist([self.item,dict(self.item,id='duplicate')])),1)
        self.assertEqual(s.shortlist([]),[])

    def test_saved_preferences_survive_without_changing_local_config(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)):
            s.save_preferences(dict(days=1,categories=['Engineering hacks'],event_queries='new bridge mechanism'))
            self.assertEqual(s.preferences()['days'],1)
            self.assertEqual(s.preferences()['categories'],['Engineering hacks'])
            studio.save_preferences(dict(captions=True,count=2))
            self.assertEqual(studio.preferences()['count'],2)


class HistoryTests(unittest.TestCase):
    def test_backfill_reads_youtube_dates_without_publishing_or_retrying(self):
        import types
        from unittest.mock import MagicMock
        service=MagicMock()
        service.videos.return_value.list.return_value.execute.return_value=dict(items=[
            dict(id='known',snippet=dict(publishedAt='2026-10-29T02:00:00Z'),status=dict(privacyStatus='public'))])
        modules={'googleapiclient':types.ModuleType('googleapiclient'),
                 'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.object(p,'credentials',return_value=None),patch.dict('sys.modules',modules):
            known=p.DATA/'exports'/'a'/'upload.json'; uncertain=p.DATA/'exports'/'b'/'upload.json'
            p.write(known,dict(video_id='known',day='2026-10-29',job_sha='approved-hash'))
            p.write(uncertain,dict(state='uploading',day='2026-10-29'))
            self.assertEqual(studio.sync_publication_dates(),1)
            record=p.read(known)
            self.assertEqual(studio.publication_time(record)[0],dt.date(2026,10,28))
            self.assertEqual(record['job_sha'],'approved-hash')
            self.assertNotIn('published_at',p.read(uncertain))
            service.videos.return_value.insert.assert_not_called()

    def test_toronto_midnight_dst_and_legacy_dates(self):
        day,label=studio.publication_time(dict(uploaded_at='2026-10-30T02:00:00+00:00'))
        self.assertEqual(day,dt.date(2026,10,29))
        self.assertIn('22:00 EDT',label)
        day,label=studio.publication_time(dict(uploaded_at='2026-11-03T04:30:00Z'))
        self.assertEqual(day,dt.date(2026,11,2))
        self.assertIn('EST',label)
        day,label=studio.publication_time(dict(day='2026-10-30'))
        self.assertEqual(day,dt.date(2026,10,30))
        self.assertIn('legacy UTC',label)
        self.assertEqual(studio.publication_time({})[0],None)

    def test_day_month_year_and_search_filters(self):
        days=[dt.date(2026,10,29),dt.date(2026,10,28),dt.date(2026,9,29),dt.date(2025,10,29),None]
        rows=[dict(day=day,job=dict(title='Goal reaction' if i==0 else 'Engineering')) for i,day in enumerate(days)]
        self.assertEqual(len(studio.filter_publications(rows,'Today',day=days[0])),1)
        self.assertEqual(len(studio.filter_publications(rows,'Choose a day',day=days[1])),1)
        self.assertEqual(len(studio.filter_publications(rows,'Month',year=2026,month=10)),2)
        self.assertEqual(len(studio.filter_publications(rows,'Year',year=2026)),3)
        self.assertEqual(len(studio.filter_publications(rows,query='GOAL')),1)
        self.assertEqual(len(studio.filter_publications(rows)),5)

    def test_history_reads_uploaded_and_uncertain_receipts_without_changing_them(self):
        with tempfile.TemporaryDirectory() as td:
            jobs=[]
            for ident,record in [('a',dict(video_id='youtube',uploaded_at='2026-10-29T14:00:00Z')),
                                 ('b',dict(state='uploading',day='2026-10-28'))]:
                path=Path(td)/ident/'job.json'; job=dict(id=ident,title=ident)
                p.write(path,job); p.write(path.parent/'upload.json',record); jobs.append((path,job))
            rows=studio.publication_rows(jobs)
            self.assertEqual([x['job']['id'] for x in rows],['a','b'])
            self.assertEqual(p.read(jobs[1][0].parent/'upload.json')['state'],'uploading')


class EditorialAuditTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.EditorialTests(); fixture.setUp()
        self.scene=fixture.scene; self.segments=fixture.segments

    def test_final_auditor_can_reject_a_catchy_but_contextless_cut(self):
        with patch.object(e,'ask',side_effect=[dict(summary='Cash vs revenue',scenes=[self.scene]),
            dict(ranked_ids=[0]),dict(scenes=[])]):
            with self.assertRaisesRegex(ValueError,'final context review'): e.select_scenes(self.segments)

    def test_final_auditor_cannot_hallucinate_id_or_evidence(self):
        for scene in [dict(self.scene,candidate_id=999),
                      dict(self.scene,candidate_id=0,evidence_quote='An invented statement not in the source')]:
            with self.subTest(scene=scene),patch.object(e,'ask',side_effect=[dict(summary='Cash',scenes=[self.scene]),
                dict(ranked_ids=[0]),dict(scenes=[scene])]):
                with self.assertRaises(ValueError): e.select_scenes(self.segments)

    def test_title_numbers_and_alternatives_must_be_in_scene(self):
        for changes in [dict(title='He Earns 10 Million'),dict(alternative_titles=['He Earns 999 Million'])]:
            with self.assertRaises(ValueError): e.validate_scene(dict(self.scene,**changes),self.segments)


class CaptionTests(unittest.TestCase):
    def test_visual_caption_attempt_uses_only_cut_and_preserves_global_timing(self):
        import types
        word=types.SimpleNamespace(start=0,end=1,word=' Hello')
        segment=types.SimpleNamespace(start=0,end=2,text='Hello there',words=[word])
        model=types.SimpleNamespace(transcribe=lambda *a,**k:([segment],types.SimpleNamespace(language='en',language_probability=.99)))
        modules={'faster_whisper':types.SimpleNamespace(WhisperModel=lambda *a,**k:model)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.dict('sys.modules',modules), \
             patch.object(p,'run') as run,patch.object(p,'material',return_value=Path(td)/'input.mp4'), \
             patch.object(p,'caption_capability',return_value=dict(supported=False)):
            job=prep.caption_visual(dict(id='visual',input='unused',start=100,end=130))
            transcript=p.read(job['caption_source'])
            self.assertEqual(transcript[0]['start'],100)
            self.assertEqual(transcript[0]['words'][0]['end'],101)
            self.assertIn('30',run.call_args.args[0])
            self.assertNotIn('transcript',job)

    def test_word_cues_are_short_offset_clamped_and_sanitized(self):
        words=[dict(start=10+i*.5,end=10.5+i*.5,word=' word') for i in range(16)]
        segments=[dict(start=10,end=18,text=' '.join(['word']*16),words=words)]
        result=p.subtitles(segments,11,17)
        self.assertIn('00:00:00,000',result)
        self.assertNotIn('00:00:07,',result)
        self.assertGreater(result.count(' --> '),1)
        self.assertNotIn('<',p.subtitles([dict(start=0,end=1,text='<b>Hello</b> {bad}\x01')],0,1))

    def test_automatic_caption_fallback_preserves_english_srt_and_permission(self):
        fixture=fixtures.EditorialTests(); fixture.setUp()
        scene=e.validate_scene(fixture.scene,fixture.segments)
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)/'data'):
            source=Path(td)/'source.mp4'; source.write_bytes(b'test')
            p.write(source.parent/'source.json',dict(title='English interview',audio_language='en',clearance_reference='creator:123'))
            key=p.digest(source)[:16]
            transcript=p.DATA/'transcripts'/(key+'-words-small-v3.json')
            p.write(transcript,fixture.segments)
            p.write(transcript.with_suffix('.language.json'),dict(language='en',probability=.99))
            with patch.object(e,'select_scenes',return_value=dict(scenes=[scene])),patch.object(p,'render'), \
                 patch.object(p,'caption_capability',return_value=dict(supported=False)):
                jobs=prep.prepare(source,'test',model='small',captions=True,editor='semantic')
            job=jobs[0]
            self.assertNotIn('transcript',job)
            self.assertEqual(job['caption_source'],str(transcript))
            self.assertEqual(job['clearance_reference'],'creator:123')
            self.assertIn('not burned',job['caption_status'])


if __name__=='__main__': unittest.main()
