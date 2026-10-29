import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import preparation as prep
import pipeline as p

class PreparationTests(unittest.TestCase):
    def test_only_single_youtube_video_urls(self):
        expected='https://www.youtube.com/watch?v=abcdefghijk'
        self.assertEqual(prep.video_url('https://youtu.be/abcdefghijk'),expected)
        self.assertEqual(prep.video_url(expected+'&list=example'),expected)
        for url in ['http://youtu.be/abcdefghijk','https://youtube.com.evil.test/watch?v=abcdefghijk',
                    'https://www.youtube.com/playlist?list=test','file:///etc/passwd',
                    'https://user:pass@youtube.com/watch?v=abcdefghijk']:
            with self.subTest(url=url),self.assertRaises(ValueError): prep.video_url(url)

    def test_non_overlapping_limited_speech_windows(self):
        segments=[dict(start=i*5,end=i*5+5,text='Here are several words in a complete sentence.') for i in range(30)]
        result=prep.windows(segments,3)
        self.assertLessEqual(len(result),3)
        self.assertEqual(len(result),3)
        for a,b in zip(result,result[1:]): self.assertLessEqual(a['end'],b['start'])
        for x in result: self.assertTrue(15<=x['end']-x['start']<=50)
        self.assertEqual(prep.windows([],3),[])

    def test_transcript_to_real_preview_and_hold(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td, patch.object(p,'DATA',Path(td)/'data'):
            source=Path(td)/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10',
                            '-f','lavfi','-i','sine=frequency=440','-t','20','-c:v','libx264',
                            '-c:a','aac',str(source)],check=True)
            key=p.digest(source)[:16]
            p.write(p.DATA/'transcripts'/(key+'.json'),[dict(start=0,end=20,text='This is a complete sentence containing enough spoken words for a test of the automatic clip preparation pipeline.')])
            with patch.object(p,'caption_capability',return_value=dict(supported=False)):
                jobs=prep.prepare(source,'test:generated',1,captions=True)
            self.assertEqual(len(jobs),1)
            self.assertTrue((p.output(jobs[0])/'clip.mp4').exists())
            self.assertTrue((p.output(jobs[0])/'captions.srt').exists())
            self.assertNotIn('transcript',jobs[0])
            with self.assertRaisesRegex(ValueError,'Review draft'):
                p.approve(jobs[0],'external:test')

if __name__=='__main__': unittest.main()
