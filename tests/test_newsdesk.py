import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import autopilot as ap
import newsdesk as nd
import pipeline as p

NOW=dt.datetime(2026,11,22,18,0,tzinfo=dt.timezone.utc)
GOOGLE_NEWS=b'''<?xml version="1.0"?><rss><channel>
<item><title>Iran seizes two tankers in Strait of Hormuz in retaliation - Reuters</title>
<link>https://news.google.com/a1</link><pubDate>Sun, 22 Nov 2026 15:00:00 GMT</pubDate>
<description>&lt;ol&gt;&lt;li&gt;&lt;a href="x"&gt;Iran seizes tankers&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Reuters&lt;/font&gt;&lt;/li&gt;&lt;li&gt;&lt;a href="y"&gt;Tankers seized&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;BBC&lt;/font&gt;&lt;/li&gt;&lt;/ol&gt;</description>
<source url="https://www.reuters.com">Reuters</source></item>
<item><title>Swimmer breaks 200m freestyle world record in Budapest - Small Blog</title>
<link>https://news.google.com/a2</link><pubDate>Sun, 22 Nov 2026 12:00:00 GMT</pubDate>
<description>record</description><source url="https://blog.example">Small Blog</source></item>
</channel></rss>'''


def report(title, source, hours=2, category='World', summary=''):
    return dict(title=title,link='https://example.com/'+str(abs(hash(title))),source=source,summary=summary,
                category=category,published=NOW-dt.timedelta(hours=hours),related=[])


class FeedTests(unittest.TestCase):
    def test_google_news_items_strip_outlet_and_collect_related_outlets(self):
        items=nd.parse_feed(GOOGLE_NEWS,'World')
        self.assertEqual(items[0]['title'],'Iran seizes two tankers in Strait of Hormuz in retaliation')
        self.assertEqual(items[0]['source'],'Reuters')
        self.assertEqual(items[0]['related'],['Reuters','BBC'])
        self.assertEqual(items[0]['published'].hour,15)

    def test_traffic_weight(self):
        self.assertEqual(nd.traffic_weight('2M+'),5)
        self.assertEqual(nd.traffic_weight('50K+'),2)
        self.assertEqual(nd.traffic_weight(''),1)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.cfg=dict(nd.DEFAULTS)

    def test_story_needs_two_outlets_or_one_major_outlet(self):
        items=[report('Swimmer breaks 200m freestyle world record in Budapest','Small Blog'),
               report('Local mayor opens new bridge over river downtown','Tiny Paper'),
               report('Local mayor opens new river bridge downtown today','Other Paper'),
               report('Iran seizes two tankers in Strait of Hormuz','Reuters')]
        titles=[s['title'] for s in nd.rank(items,[],self.cfg,NOW)]
        self.assertNotIn('Swimmer breaks 200m freestyle world record in Budapest',titles)
        self.assertEqual(len(titles),2)
        self.assertTrue(any('Iran' in t for t in titles))

    def test_buzz_boosts_but_never_qualifies_a_story(self):
        items=[report('Iran seizes two tankers in Strait of Hormuz','Reuters'),
               report('Pop star announces surprise world tour dates','CNN',category='Entertainment')]
        terms=[dict(term='Strait of Hormuz tankers',source='X',weight=3,context=[]),
               dict(term='Celebrity rumour nobody reported',source='Reddit r/popculturechat',weight=5,context=[])]
        stories=nd.rank(items,terms,self.cfg,NOW)
        self.assertIn('Iran',stories[0]['title'])
        self.assertEqual(stories[0]['buzz'],['X'])
        self.assertEqual(len(stories),2)

    def test_sensitive_and_old_stories_are_dropped(self):
        items=[report('Police investigate suicide of local teacher','Reuters'),
               report('Old election result confirmed by court','Reuters',hours=80)]
        self.assertEqual(nd.rank(items,[],self.cfg,NOW),[])

    def test_same_event_from_several_outlets_is_one_story(self):
        items=[report('Iran seizes two tankers in Strait of Hormuz','Reuters'),
               report('Iran seizes two oil tankers near Strait of Hormuz','BBC'),
               report('Two tankers seized by Iran in the Strait of Hormuz','CNN')]
        stories=nd.rank(items,[],self.cfg,NOW)
        self.assertEqual(len(stories),1)
        self.assertEqual(len(stories[0]['outlets']),3)

    def test_pick_mixes_categories(self):
        stories=[dict(key=str(n),title=f'story {n}',category='World',words=[f'w{n}a',f'w{n}b',f'w{n}c'],score=10-n) for n in range(4)]
        stories.append(dict(key='s',title='sport',category='Sports',words=['goal','final','cup'],score=1))
        self.assertEqual([s['category'] for s in nd.pick(stories,3)],['World','World','Sports'])


STORY=dict(key='abc123',title='Iran seizes two tankers in Strait of Hormuz',link='https://news.google.com/a1',source='Reuters',
           category='World',outlets=['BBC','Reuters'],major=True,score=50,words=['iran','seizes','tankers','strait','hormuz'],
           reports=[dict(title='Iran seizes two tankers in Strait of Hormuz',source='Reuters',link='x',
                         summary='Iran says it will do everything necessary to lift the blockade.')])


class CardTests(unittest.TestCase):
    def test_grounded_rejects_invented_numbers_and_names(self):
        source=nd.source_text(STORY)
        self.assertTrue(nd.grounded('BREAKING: Iran seizes two tankers in Hormuz',source))
        self.assertFalse(nd.grounded('Iran seizes 5 tankers',source))
        self.assertFalse(nd.grounded('Trump responds as Iran seizes tankers',source))

    def test_write_card_uses_editor_text_when_grounded(self):
        answer=dict(headline='Iran seizes two tankers in Hormuz',highlight='two tankers',kicker='WORLD',
                    facts=['Iran says it will do everything necessary to lift the blockade'],title='Iran seizes two tankers',
                    image_prompt='Donald Trump watching two oil tankers on a stormy sea',hashtags=['Iran','oil'],
                    search='Iran tankers Strait of Hormuz')
        source=dict(STORY,reports=STORY['reports']+[dict(title='Donald Trump reacts',source='CNN',summary='',link='y')])
        card=nd.write_card(source,'qwen2.5:7b',ask=lambda prompt,model:answer)
        self.assertEqual(card['headline'],'Iran seizes two tankers in Hormuz')
        self.assertEqual(card['written_by'],'local editor')
        self.assertEqual(card['kicker'],'WORLD')
        self.assertEqual(len(card['facts']),1)
        self.assertNotIn('Donald Trump',card['image_prompt'])
        self.assertEqual(card['hashtags'],['#iran','#oil'])
        self.assertEqual(card['search'],'Iran tankers Strait of Hormuz')

    def test_write_card_falls_back_to_outlet_headline(self):
        invented=dict(headline='Iran sinks 7 US warships',facts=['50 dead'],kicker='NOPE',title='Iran sinks 7 ships')
        card=nd.write_card(STORY,'qwen2.5:7b',ask=lambda prompt,model:invented)
        self.assertEqual(card['headline'],STORY['title'])
        self.assertEqual(card['facts'],[])
        self.assertEqual(card['title'],STORY['title'])
        def broken(prompt,model): raise RuntimeError('ollama down')
        self.assertEqual(nd.write_card(STORY,'qwen2.5:7b',ask=broken)['written_by'],'outlet headline')

    def test_compose_draws_a_4_by_5_card_without_ai_label(self):
        card=nd.fallback_card(STORY)
        card.update(highlight='tankers',facts=['Iran says it will do everything necessary to lift the blockade'])
        image=nd.compose(card,STORY,None,'Viral Moment Clips')
        self.assertEqual(image.size,(1080,1350))
        self.assertNotIn('AI',nd.caption(card,STORY).replace('#',''))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        data=Path(self.tmp.name)
        patcher=patch.object(p,'DATA',data); patcher.start(); self.addCleanup(patcher.stop)
        p.write(nd.stories_file(),dict(scanned_at=dt.datetime.now(dt.timezone.utc).isoformat(),stories=[STORY]))
        self.ask=lambda prompt,model:dict(search='Iran tankers Hormuz')

    def test_footage_adds_matching_videos_once(self):
        results=[dict(id='aaaaaaaaaaa',title='Iran seizes tankers in Hormuz: footage',url='https://www.youtube.com/watch?v=aaaaaaaaaaa',source='News'),
                 dict(id='bbbbbbbbbbb',title='My cooking vlog',url='https://www.youtube.com/watch?v=bbbbbbbbbbb',source='Cook')]
        queries=[]
        added=nd.footage(search=lambda q:(queries.append(q),results)[1],ask=self.ask,log=lambda m:None)
        self.assertEqual(added,1)
        self.assertEqual(queries,['Iran tankers Hormuz'])
        saved=p.read(p.DATA/'candidates.json')
        self.assertEqual(saved[0]['news_story'],STORY['title'])
        # The same story is not searched again.
        self.assertEqual(nd.footage(search=lambda q:results,ask=self.ask,log=lambda m:None),0)

    def test_footage_candidates_prefer_hot_stories_and_skip_used(self):
        ranked=[dict(url='u1',news_story='a',news_score=10,priority_score=5),dict(url='u2',news_story='b',news_score=40,priority_score=1),
                dict(url='u3',priority_score=99),dict(url='u4',news_story='c',news_score=50)]
        self.assertEqual([x['url'] for x in nd.footage_candidates(ranked,{'u4'})],['u2','u1'])

    def test_make_images_saves_card_and_caption_and_counts_the_day(self):
        with patch.object(nd,'ensure_image_model',return_value=False):
            saved=nd.make_images(2,ask=lambda prompt,model:dict(headline='Iran seizes two tankers in Hormuz'),stage=lambda m:None)
        self.assertEqual(len(saved),1)
        record=p.read(saved[0].with_suffix('.json'))
        self.assertIn('Reported by BBC, Reuters',record['caption'])
        self.assertFalse(record['posted'])
        self.assertEqual(nd.make_images(2,ask=self.ask,stage=lambda m:None),[])


class AutopilotNewsTests(unittest.TestCase):
    def test_news_footage_alternates_with_other_picks(self):
        news=[dict(url='n1'),dict(url='n2')]
        others=[dict(url='c1',focus=True),dict(url='c2'),dict(url='n2')]
        with patch('app_runtime.used_sources',return_value=set()), patch('app_runtime.fresh_choices',return_value=others), \
             patch.object(ap,'news_footage',return_value=news):
            picked=ap.candidates(dict(ap.DEFAULTS),lambda *a:None)
        self.assertEqual([x['url'] for x in picked],['n1','c1','n2','c2'])

    def test_focus_only_skips_news(self):
        with patch('app_runtime.used_sources',return_value=set()), patch('app_runtime.fresh_choices',return_value=[dict(url='c1',focus=True)]), \
             patch.object(ap,'news_footage',side_effect=AssertionError):
            self.assertEqual(len(ap.candidates(dict(ap.DEFAULTS,focus_only=True),lambda *a:None)),1)

    def test_news_problems_never_block(self):
        with patch('newsdesk.settings',side_effect=RuntimeError('boom')):
            self.assertEqual(ap.news_footage(lambda *a:None,set()),[])
            self.assertEqual(ap.news_images(lambda *a:None),[])


if __name__=='__main__':
    unittest.main()
