import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app_runtime as r
import pipeline as p


class DuplicateUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        patcher=patch.object(p,'DATA',Path(self.temp.name)/'data'); patcher.start(); self.addCleanup(patcher.stop)
        self.job=dict(id='story-v3-new',source_url='https://www.youtube.com/watch?v=LRm3E-2xF-0',start=823.78,end=865.07,
                      title='LeBron Tours the Mansion')

    def published(self, ident, receipt, **job):
        dest=p.DATA/'exports'/ident
        p.write(dest/'job.json',dict(self.job,id=ident,title='Earlier upload',**job))
        p.write(dest/'upload.json',receipt)
        return dest

    def test_regenerated_batch_cannot_repeat_published_moment(self):
        self.published('story-v1-old',dict(state='uploaded',video_id='Sl2NB9sRW5I'),start=830,end=870)
        conflicts=p.upload_conflicts(self.job)
        self.assertEqual([x['video_id'] for x in conflicts],['Sl2NB9sRW5I'])
        self.assertIn('youtu.be/Sl2NB9sRW5I',p.describe_conflicts(conflicts))

    def test_uncertain_attempts_also_block(self):
        self.published('story-v1-old',dict(state='uploading',day='2026-10-23'))
        conflicts=p.upload_conflicts(self.job)
        self.assertIn('uncertain',p.describe_conflicts(conflicts))

    def test_distinct_moments_and_other_sources_are_allowed(self):
        self.published('adjacent',dict(state='uploaded',video_id='a'),start=860,end=900)
        self.published('other-source',dict(state='uploaded',video_id='b'),source_url='https://www.youtube.com/watch?v=other')
        p.write(p.DATA/'exports'/'draft-unpublished'/'job.json',self.job)
        self.assertEqual(p.upload_conflicts(self.job),[])
        self.assertAlmostEqual(p.overlap_ratio(dict(start=0,end=10),dict(start=5,end=40)),.5)

    def test_identical_video_bytes_block_even_with_new_metadata(self):
        dest=self.published('copy',dict(state='uploaded',video_id='c'),source_url='Local file: other.mp4')
        own=p.output(self.job); own.mkdir(parents=True)
        (own/'clip.mp4').write_bytes(b'same video')
        p.write(dest/'approval.json',dict(video_sha=p.digest(own/'clip.mp4')))
        self.assertEqual(p.upload_conflicts(self.job)[0]['reason'],'identical video')
        self.assertEqual(p.upload_conflicts(self.job,check_video=False),[])

    def test_receipt_without_job_file_still_counts(self):
        dest=p.DATA/'exports'/'receipt-only'
        p.write(dest/'upload.json',dict(state='uploaded',video_id='d',source_url=self.job['source_url'],start=823.78,end=865.07))
        self.assertEqual(len(p.upload_conflicts(self.job)),1)

    def test_upload_refuses_before_any_network_or_receipt(self):
        self.published('story-v1-old',dict(state='uploaded',video_id='x'))
        import types
        modules={'googleapiclient':types.ModuleType('googleapiclient'),
                 'googleapiclient.discovery':types.SimpleNamespace(build=None),
                 'googleapiclient.http':types.SimpleNamespace(MediaFileUpload=None)}
        with patch.object(p,'check_approval'),patch.object(p,'credentials') as credentials,patch.dict('sys.modules',modules):
            with self.assertRaisesRegex(ValueError,'Duplicate upload blocked'): p.upload(self.job)
        credentials.assert_not_called()
        self.assertFalse((p.output(self.job)/'upload.json').exists())


class BatchPublishTests(unittest.TestCase):
    def test_one_blocked_clip_does_not_stop_the_rest(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(p,'DATA',Path(folder)),patch.object(r,'STATE',Path(folder)/'state.json'):
            for ident in ('a','b'): p.write(p.DATA/'exports'/ident/'job.json',dict(id=ident))
            p.write(r.STATE,dict(status='running',pid=os.getpid()))
            request=Path(folder)/'request.json'; p.write(request,dict(action='publish',payload=dict(ids=['a','b'])))
            def upload(job):
                if job['id']=='a': raise ValueError('Duplicate upload blocked')
            with patch.object(p,'upload',side_effect=upload) as mock,patch.object(r.traceback,'print_exc'),patch('builtins.print'):
                r.execute(request)
            self.assertEqual([c.args[0]['id'] for c in mock.call_args_list],['a','b'])
            state=p.read(r.STATE)
            self.assertEqual(state['status'],'failed')
            self.assertIn('1 of 2',state['error'])


if __name__=='__main__': unittest.main()
