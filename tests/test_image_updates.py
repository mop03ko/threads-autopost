import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import threads_post as app
import prepare_image_urls as images
from test_reliability import HEADERS, MemoryStore, post, row


class ImageUpdatesTests(unittest.TestCase):
    def test_images_cannot_reset_locked_status_or_replace_new_text(self):
        for status in ('posted', 'processing', 'needs_review', 'hold', 'failed', 'skipped'):
            before = [post(status=status, image_url='https://example.test/old.jpg')]
            edited = [post(status='pending', text='stale text', image_url='https://example.test/new.jpg')]
            latest = copy.deepcopy(before)
            latest[0]['text'] = 'Latest editorial text'
            latest[0]['threads_id'] = 'preserved'
            changed = images.merge_image_changes(latest, before, edited)
            with self.subTest(status=status):
                self.assertEqual(latest[0]['status'], status)
                self.assertEqual(latest[0]['text'], 'Latest editorial text')
                self.assertEqual(latest[0]['threads_id'], 'preserved')
                self.assertEqual(changed, [] if status in ('posted','processing','needs_review') else [1])

    def test_concurrent_image_change_wins(self):
        original=[post(image_url='https://example.test/old.jpg')]
        edited=[post(image_url='https://example.test/stale-job.jpg')]
        latest=[post(image_url='https://example.test/newer.jpg')]
        self.assertEqual(images.merge_image_changes(latest,original,edited), [])
        self.assertEqual(latest[0]['image_url'],'https://example.test/newer.jpg')

    def test_remote_save_preserves_publication_that_finished_during_generation(self):
        store=MemoryStore([post(status='posted',threads_id='real-id')])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GITHUB_REPOSITORY':'o/r','GITHUB_TOKEN':'test'}), \
             patch.object(images,'remote_store',return_value=store):
            path=Path(tmp)/'queue.json'
            images._loaded_snapshots[str(path.resolve())]=[post()]
            edited=[post(image_url='https://example.test/new.jpg')]
            self.assertEqual(images.save_queue(path,edited),[])
            self.assertEqual(edited[0]['status'],'posted')
            self.assertEqual(edited[0]['threads_id'],'real-id')

    def test_sheet_sync_updates_only_target_image_cells(self):
        table=[HEADERS,list(row().values()),list(row(id='2').values())]
        with patch.object(app,'google_sheet_session',return_value=object()), \
             patch.object(app,'selected_sheet',return_value={'title':'Posts'}), \
             patch.object(app,'google_json',side_effect=[{'valueRanges':[{'values':table}]},{}]) as request, \
             patch.dict(os.environ,{'THREADS_SHEET_ID':'sheet'}):
            count=images.sync_google_sheet([post(status='posted', image_url='https://example.test/1.jpg'),
                                           post(2,image_url='https://example.test/2.jpg')],[2])
            self.assertEqual(count,1)
            self.assertEqual(request.call_args.kwargs['json']['data'],[
                {'range':"'Posts'!D3",'values':[['https://example.test/2.jpg']]}])

    def test_assign_images_keeps_hold_and_processing(self):
        queue=[post(2,status='hold'),post(3,status='processing')]
        assigned,activated=images.assign_images(queue,'https://example.test',force=True)
        self.assertEqual((assigned,activated),(1,0))
        self.assertEqual(queue[0]['status'],'hold')
        self.assertIsNone(queue[1]['image_url'])
