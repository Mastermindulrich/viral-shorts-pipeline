import datetime as dt
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import autopilot as ap
import community as c
import pipeline as p


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        patcher=patch.object(p,'DATA',Path(self.tmp.name)); patcher.start(); self.addCleanup(patcher.stop)
        self.day=p.DATA/'newsdesk'/'images'/dt.date.today().isoformat()
        self.day.mkdir(parents=True)
        for name in ('a','b'):
            (self.day/(name+'.jpg')).write_bytes(b'jpg')
            p.write(self.day/(name+'.json'),dict(image=name+'.jpg',caption='Caption '+name,card=dict(headline='Headline '+name),posted=False))
        old=p.DATA/'newsdesk'/'images'/'2020-01-01'; old.mkdir()
        (old/'z.jpg').write_bytes(b'jpg'); p.write(old/'z.json',dict(image='z.jpg',caption='old',card={},posted=False))
        self.page=MagicMock()
        context=MagicMock(pages=[self.page])
        patcher=patch.object(c,'browser',return_value=context); patcher.start(); self.addCleanup(patcher.stop)

        @contextmanager
        def factory(): yield MagicMock()
        self.factory=factory

    def test_pending_skips_old_and_posted(self):
        p.write(self.day/'b.json',dict(p.read(self.day/'b.json'),posted=True))
        self.assertEqual([x.name for x in c.pending()],['a.json'])

    def test_broken_fact_cards_are_never_posted(self):
        p.write(self.day/'a.json',dict(p.read(self.day/'a.json'),card=dict(headline='x',facts=['S','a'])))
        self.assertEqual([x.name for x in c.pending()],['b.json'])

    def test_success_marks_posted(self):
        with patch.object(c,'publish',return_value=True) as publish:
            posted=c.post_next(1,self.factory)
        self.assertEqual([x.name for x in posted],['a.json'])
        self.assertEqual(publish.call_args[0][2],'Caption a')
        record=p.read(self.day/'a.json')
        self.assertTrue(record['posted']); self.assertEqual(record['attempts'],1)

    def test_failures_stop_after_three_attempts(self):
        with patch.object(c,'publish',side_effect=RuntimeError('No Post button')):
            for _ in range(3): c.post_next(1,self.factory)
        record=p.read(self.day/'a.json')
        self.assertEqual(record['attempts'],3); self.assertIn('No Post button',record['last_error'])
        self.assertEqual([x.name for x in c.pending()],['b.json'])

    def test_signed_out_keeps_attempts_and_raises(self):
        with patch.object(c,'publish',side_effect=PermissionError('Not signed in')):
            with self.assertRaises(PermissionError): c.post_next(1,self.factory)
        self.assertEqual(p.read(self.day/'a.json')['attempts'],0)

    def test_autopilot_notifies_sign_in_once_a_day_and_never_raises(self):
        local=dt.datetime(2026,11,23,12,0)
        with patch('community.post_next',side_effect=PermissionError('Not signed in')), patch.object(ap,'notify') as notify, \
             patch.dict('sys.modules',{'playwright':MagicMock()}):
            self.assertEqual(ap.community_posts(local),[])
            self.assertEqual(ap.community_posts(local),[])
        self.assertEqual(notify.call_count,1)

    def test_autopilot_posts_only_in_the_day(self):
        with patch('community.post_next') as post:
            self.assertEqual(ap.community_posts(dt.datetime(2026,11,23,3,0)),[])
        post.assert_not_called()


if __name__=='__main__':
    unittest.main()
