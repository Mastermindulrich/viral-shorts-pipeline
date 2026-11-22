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
    def test_optional_caption_render(self):
        capability=p.caption_capability()
        if not capability['supported']:
            self.skipTest(capability['reason'])
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=30',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2',
                        '-c:v','libx264','-c:a','aac',self.job['input']],check=True)
        transcript=self.root/'transcript.json'
        p.write(transcript,[dict(start=0,end=1,text='Test caption')])
        self.job['transcript']=str(transcript)
        p.render(self.job)
        self.assertIn('Test caption',(p.output(self.job)/'captions.srt').read_text())
        self.assertTrue((p.output(self.job)/'clip.mp4').is_file())
        # The captioned frame must differ from the otherwise black source frame.
        pixels=subprocess.check_output(['ffmpeg','-v','error','-i',str(p.output(self.job)/'clip.mp4'),
                                        '-frames:v','1','-f','rawvideo','-pix_fmt','gray','-'])
        self.assertGreater(max(pixels),200)

    def test_caption_capability_and_early_failure(self):
        with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,
                stdout=' ... scale V->V Scale video\n ... subtitles V->V Render text\n',stderr='')):
            self.assertTrue(p.caption_capability()['supported'])
        with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,
                stdout=' ... scale V->V Scale video\n',stderr='')):
            self.assertFalse(p.caption_capability()['supported'])

    def make_source(self):
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=30',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2',
                        '-c:v','libx264','-c:a','aac',self.job['input']],check=True)

    def test_caption_problems_never_stop_a_clip(self):
        # Owner decision 2026-11-22: a caption failure drops subtitles; the clip still renders.
        self.make_source()
        transcript=self.root/'transcript.json'
        p.write(transcript,[dict(start=0,end=1,text='Test caption')])
        cases=[('missing libass',dict(transcript=str(transcript)),{'supported':False,'reason':'subtitles/libass missing'}),
               ('unreadable transcript',dict(transcript=str(self.root/'missing.json')),{'supported':True,'reason':''}),
               ('no overlapping text',dict(transcript=str(transcript),start=1.0,end=2.0),{'supported':True,'reason':''})]
        for name,extra,capability in cases:
            with self.subTest(name), patch.object(p,'caption_capability',return_value=capability):
                job=dict(self.job,**extra)
                p.render(job)
                self.assertTrue((p.output(job)/'clip.mp4').is_file())
                self.assertNotIn('transcript',job)
                self.assertIn('without burned-in subtitles',job['caption_status'])
                self.assertEqual(p.read(p.output(job)/'job.json'),job)

    def test_failed_subtitle_burn_retries_without_subtitles(self):
        self.make_source()
        transcript=self.root/'transcript.json'
        p.write(transcript,[dict(start=0,end=1,text='Test caption')])
        real=p.run
        def run(args,**kwargs):
            if any('subtitles=' in str(a) for a in args): raise subprocess.CalledProcessError(1,args)
            return real(args,**kwargs)
        job=dict(self.job,transcript=str(transcript))
        with patch.object(p,'caption_capability',return_value={'supported':True,'reason':''}), patch.object(p,'run',side_effect=run):
            p.render(job)
        self.assertTrue((p.output(job)/'clip.mp4').is_file())
        self.assertIn('could not burn',job['caption_status'])
        self.assertTrue((p.output(job)/'captions.srt').exists())

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
