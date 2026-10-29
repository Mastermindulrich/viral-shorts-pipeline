import copy
import datetime as dt
import unittest
from unittest.mock import patch
import editorial as e
import scouting as s

class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.segments=[dict(start=0,end=10,text='Kai asks how much the business earns each year.'),
                       dict(start=10,end=25,text='LeBron says the business earns 100 million in revenue.'),
                       dict(start=25,end=40,text='They explain that revenue is different from personal cash.')]
        self.scene=dict(spoken_language='en',first_segment=0,last_segment=2,topic='Business revenue versus cash',
                        setup='Kai asks about business earnings',payoff='Revenue does not equal personal cash',
                        why_this_cut='Keeps the question, figure and qualification together',
                        title='Kai Asks LeBron About His Business Revenue',alternative_titles=['LeBron Explains What Revenue REALLY Means'],
                        evidence_quote='LeBron says the business earns 100 million in revenue.',
                        scores=dict(hook=8,coherence=9,payoff=8,specificity=9))
    def test_supported_scene(self):
        result=e.validate_scene(self.scene,self.segments)
        self.assertEqual(result['end'],40)
        self.assertTrue(result['visual_review_required'])
    def test_rejects_outside_evidence_numbers_and_bad_boundaries(self):
        for changes in [dict(evidence_quote='He keeps a billion dollars in a bank account'),
                        dict(title='LeBron Has 999 Million In Cash'),dict(last_segment=5),dict(first_segment=True),
                        dict(scores=dict(hook=8,coherence=2,payoff=8,specificity=9))]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                e.validate_scene(dict(self.scene,**changes),self.segments)
    def test_semantic_pipeline_uses_topic_map_and_title(self):
        with patch.object(e,'ask',side_effect=[{'summary':'Revenue versus cash','scenes':[self.scene]}, {'ranked_ids':[0]},
                {'scenes':[dict(self.scene,candidate_id=0)]}]) as ask:
            result=e.select_scenes(self.segments,3)
            self.assertEqual(result['scenes'][0]['title'],self.scene['title'])
            self.assertIn('Revenue versus cash',ask.call_args_list[1].args[0])
            self.assertIn('Revenue is different',ask.call_args.args[0].replace('revenue is different','Revenue is different'))
            self.assertTrue(result['scenes'][0]['context_audited'])
    def test_no_silent_fallback(self):
        with patch.object(e,'ask',return_value={'summary':'Nothing complete','scenes':[]}):
            with self.assertRaisesRegex(ValueError,'No valid complete scenes'): e.select_scenes(self.segments)
    def test_cloud_model_rejected_before_network(self):
        with self.assertRaises(ValueError): e.ask('test','example-cloud')
    def test_chunks_cover_all_segments(self):
        segments=[dict(text='word '*100) for _ in range(120)]
        chunks=list(e.chunks(segments,size=2000))
        self.assertEqual(set(range(120)),set(i for a,b in chunks for i in range(a,b)))

class ScoutingTests(unittest.TestCase):
    def test_velocity_and_duration(self):
        now=dt.datetime(2026,10,23,tzinfo=dt.timezone.utc)
        items=[dict(id='a',source='Creator',published=(now-dt.timedelta(hours=2)).isoformat(),views=200,duration_seconds=600)]
        old={'a':dict(views=150,observed_at=(now-dt.timedelta(hours=.5)).isoformat())}
        ranked=s.rank(items,old,now)
        self.assertEqual(ranked[0]['measured_views_per_hour'],100)
        self.assertTrue(ranked[0]['eligible_long_source'])
        self.assertEqual(s.duration_seconds('PT1H2M3S'),3723)
    def test_first_scan_does_not_claim_measured_growth(self):
        now=dt.datetime.now(dt.timezone.utc)
        items=[dict(id='a',source='Creator',published=(now-dt.timedelta(hours=2)).isoformat(),views=200,duration_seconds=30)]
        item=s.rank(items,{},now)[0]
        self.assertIsNone(item['measured_views_per_hour'])
        self.assertFalse(item['eligible_long_source'])


class BroadDiscoveryTests(unittest.TestCase):
    def test_rotating_queries_merge_and_deduplicate(self):
        import tempfile
        import types
        from pathlib import Path
        from unittest.mock import MagicMock
        import pipeline as p
        service=MagicMock()
        service.videos.return_value.list.return_value.execute.return_value={'items':[]}
        service.search.return_value.list.return_value.execute.return_value={'items':[
            {'id':{'videoId':'abcdefghijk'},'snippet':{'title':'Example','publishedAt':dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z'),'channelTitle':'Example creator'}}]}
        with tempfile.TemporaryDirectory() as td, patch.object(p,'ROOT',Path(td)), patch.object(p,'DATA',Path(td)/'data'), patch.object(s,'preferences',return_value=dict(s.DEFAULTS,categories=[])), patch.object(p,'credentials',return_value=None), patch.dict('sys.modules',{'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}):
            p.write(Path(td)/'config'/'discovery.json',dict(searches_per_scan=2,regions=['US'],topics=[dict(name=str(i),query='query'+str(i)) for i in range(4)]))
            first=s.discover_broad()
            second=s.discover_broad()
            self.assertEqual(first['searched_topics'],['0','1'])
            self.assertEqual(second['searched_topics'],['2','3'])
            self.assertEqual(len(p.read(p.DATA/'candidates.json')),1)
            self.assertEqual(service.search.return_value.list.call_count,4)
            for call in service.search.return_value.list.call_args_list:
                self.assertEqual(call.kwargs['relevanceLanguage'],'en')
