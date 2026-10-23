from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import pipeline as p

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patcher = patch.object(p, 'DATA', self.root/'data')
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.job = dict(id='sample', input=str(self.root/'input.mp4'), source_url='test:generated',
                        start=0, end=1, title='Test clip', made_for_kids=False, privacy='private')
    def test_invalid_jobs(self):
        for key, value in [('id','../oops'), ('end',181), ('start',float('nan')),
                           ('made_for_kids',None), ('privacy','typo'), ('title','')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate(dict(self.job, **{key:value}))
    def test_captions_offset(self):
        result = p.subtitles([dict(start=9,end=12,text='Hello'),dict(start=20,end=21,text='Out')],10,15)
        self.assertIn('00:00:00,000 --> 00:00:02,000', result)
        self.assertNotIn('Out', result)
    def test_real_render_and_approval(self):
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2',
                        '-c:v','libx264','-c:a','aac',self.job['input']], check=True)
        transcript = self.root/'transcript.json'
        p.write(transcript,[dict(start=0,end=1,text='Test caption')])
        self.job['transcript'] = str(transcript)
        p.render(self.job)
        dest = p.output(self.job)
        meta = p.probe(dest/'clip.mp4')
        v = next(x for x in meta['streams'] if x['codec_type']=='video')
        self.assertEqual((v['width'],v['height']),(1080,1920))
        self.assertTrue(any(x['codec_type']=='audio' for x in meta['streams']))
        self.assertAlmostEqual(float(meta['format']['duration']),1,delta=.15)
        self.assertTrue((dest/'cover.jpg').exists())
        p.approve(self.job,'owner:123')
        p.check_approval(self.job)
        with self.assertRaises(ValueError):
            p.check_approval(dict(self.job,title='Changed'))
        with (dest/'clip.mp4').open('ab') as f: f.write(b'changed')
        with self.assertRaises(ValueError): p.check_approval(self.job)
    def test_channel_guard(self):
        service = MagicMock()
        service.channels.return_value.list.return_value.execute.return_value = {
            'items':[{'id':'wrong', 'snippet':{'title':'Late Night'}}]}
        with self.assertRaisesRegex(ValueError, 'Upload blocked'):
            p.verify_channel(service,'expected')
        service.channels.return_value.list.return_value.execute.return_value = {
            'items':[{'id':'expected', 'snippet':{'title':'Viral Moment Clips'}}]}
        self.assertEqual(p.verify_channel(service,'expected')['name'],'Viral Moment Clips')
        service.channels.return_value.list.return_value.execute.return_value = {'items':[]}
        with self.assertRaises(ValueError): p.verify_channel(service,'expected')
        with self.assertRaises(ValueError): p.verify_channel(service,'')

    def test_lock_rejects_concurrent_worker(self):
        with p.lock():
            with self.assertRaises(RuntimeError):
                with p.lock(): pass
        # Advisory locks retain the inode and release automatically.
        with p.lock(): pass

if __name__ == '__main__': unittest.main()
