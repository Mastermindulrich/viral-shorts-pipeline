import copy
import datetime as dt
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import content_policy as policy
import pipeline as p
import scouting
import editorial
import test_editorial

class ContentPolicyTests(unittest.TestCase):
    def test_music_release_excluded_but_reactions_trailers_dance_kept(self):
        examples=[
            ({'title':'Artist - New Song (Official Music Video)','source':'Artist'},False),
            ({'title':'New Song','source':'ArtistVEVO','categoryId':'10'},False),
            ({'title':'New Song','source':'Artist - Topic','categoryId':'10'},False),
            ({'title':'Artist - Song (Official Audio)','source':'Artist'},False),
            ({'title':'Artist - Song Official Music Video REACTION','source':'Reaction channel'},True),
            ({'title':'New Film Official Trailer','source':'Movie studio'},True),
            ({'title':'Artist - Hot Interview','source':'Artist','categoryId':'10'},True),
            ({'title':'Artist dance challenge','source':'ArtistVEVO','categoryId':'10'},True),
            ({'title':'Amapiano dance challenge','source':'Dancers','categoryId':'10','defaultAudioLanguage':'zu'},True),
            ({'title':'Hot interview','defaultAudioLanguage':'fr'},False),
            ({'title':'Gamer interview','defaultAudioLanguage':'en-GB'},True),
            ({'title':'Artist - Dance Tonight (Official Music Video)','source':'Artist'},False)]
        for item,expected in examples:
            with self.subTest(item=item): self.assertEqual(policy.screen(item)['eligible'],expected)

    def test_strict_music_screen_catches_unlabelled_and_nonofficial_releases(self):
        for item in [dict(title='A new single',source='Unknown label',categoryId='10'),
                     dict(title='Singer - Track M/V',source='Label'),
                     dict(title='Track (Visualizer)',source='Fan channel'),
                     dict(title='Singer - Reaction (Official Video)',categoryId='10'),
                     dict(title='Amapiano summer mix',categoryId='10'),
                     dict(title='Artist - Dance Tonight',categoryId='10'),
                     dict(title='Track',description='Provided to YouTube by Label')]:
            with self.subTest(item=item): self.assertFalse(policy.screen(item)['eligible'])
        for title in ['Song (Official Video) REACTION','First time hearing Song (Official Audio)',
                      'TikTok dance challenge','African urban dance battle','Singer interview']:
            with self.subTest(title=title):
                self.assertTrue(policy.screen(dict(title=title,categoryId='10'))['eligible'])

    def test_old_cache_hidden_until_metadata_checked_and_hidden_ids_persist(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)):
            old=dict(id='old',title='Unknown cached video')
            current=dict(id='current',title='Interview',policy_version=policy.VERSION,
                         published=dt.datetime.now(dt.timezone.utc).isoformat(),views=20000,
                         average_views_per_hour=1000,duration_seconds=600)
            self.assertEqual([x['id'] for x in scouting.visible_ranked([old,current])],['current'])
            scouting.hide_video(current)
            self.assertEqual(scouting.visible_ranked([current]),[])
            self.assertIn('current',p.read(p.DATA/'scouting-hidden.json'))
            scouting.restore_video('current')
            self.assertEqual(len(scouting.visible_ranked([current])),1)

    def test_hidden_video_is_not_requested_on_refresh(self):
        service=MagicMock()
        modules={'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.object(p,'credentials',return_value=None),patch.dict('sys.modules',modules):
            item=dict(id='hidden',title='Hidden release')
            p.write(p.DATA/'candidates.json',[item])
            scouting.hide_video(item)
            self.assertEqual(scouting.refresh(),[])
            service.videos.assert_not_called()

    def test_missing_language_is_not_claimed_english(self):
        self.assertEqual(policy.screen({'title':'Interview','defaultLanguage':'en'})['language_status'],'Language needs verification')

    def test_old_config_gets_topics_without_overwriting_custom_preferences(self):
        config={'searches_per_scan':2,'topics':[{'name':'Politics','query':'politics'}, {'name':'Music and concerts','query':'concert'}]}
        result=policy.discovery_config(config)
        self.assertEqual(result['searches_per_scan'],2)
        self.assertEqual(result['topics'][0],config['topics'][0])
        self.assertIn('African urban dance',[x['name'] for x in result['topics']])
        self.assertNotIn('Music and concerts',[x['name'] for x in result['topics']])
        self.assertEqual(policy.discovery_config(result),result)

    def test_saved_candidates_are_rescreened(self):
        result=policy.visible_candidates([{'title':'Artist - Song (Official Video)'},{'title':'Movie trailer'}])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['title'],'Movie trailer')

    def test_api_enrichment_filters_and_retains_exclusion_reason(self):
        service=MagicMock()
        snippet=dict(publishedAt='2026-10-23T00:00:00Z',channelTitle='Artist',categoryId='10')
        service.videos.return_value.list.return_value.execute.return_value={'items':[
            dict(id='music',snippet=dict(snippet,title='Artist - Song (Official Video)'),statistics={'viewCount':'999'},contentDetails={'duration':'PT3M'}),
            dict(id='reaction',snippet=dict(snippet,title='Song reaction',defaultAudioLanguage='en'),statistics={'viewCount':'100'},contentDetails={'duration':'PT8M'})]}
        modules={'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.discovery':types.SimpleNamespace(build=lambda *a,**k:service)}
        with tempfile.TemporaryDirectory() as td,patch.object(p,'DATA',Path(td)),patch.object(p,'credentials',return_value=None),patch.dict('sys.modules',modules):
            p.write(p.DATA/'candidates.json',[dict(id=x,title=x,source='Creator',url='https://example.com/'+x) for x in ['music','reaction']])
            result=scouting.refresh()
            self.assertEqual([x['id'] for x in result],['reaction'])
            self.assertEqual(p.read(p.DATA/'scouting-exclusions.json')[0]['id'],'music')

class DurationPolicyTests(unittest.TestCase):
    def test_sixty_is_accepted_sixty_plus_is_rejected(self):
        job=dict(id='test',start=100,end=160,title='Test',source_url='test',made_for_kids=False)
        p.validate(job)
        for duration in (60.001,75,90,180):
            with self.subTest(duration=duration),self.assertRaisesRegex(ValueError,'60'):
                p.validate(dict(job,end=100+duration))

    def test_real_media_duration_checked_not_only_job_metadata(self):
        for duration in (60.001,float('nan'),float('inf')):
            with patch.object(p,'probe',return_value={'format':{'duration':str(duration)}}),self.assertRaises(ValueError):
                p.validate_export_duration('unused')
        with patch.object(p,'probe',return_value={'format':{'duration':'60.0'}}): p.validate_export_duration('unused')

    def test_editor_rejects_long_and_non_english_scenes(self):
        fixture=test_editorial.EditorialTests(); fixture.setUp()
        segments=copy.deepcopy(fixture.segments); segments[-1]['end']=61
        with self.assertRaisesRegex(ValueError,'60'): editorial.validate_scene(fixture.scene,segments)
        with self.assertRaisesRegex(ValueError,'English'):
            editorial.validate_scene(dict(fixture.scene,spoken_language='fr'),fixture.segments)
