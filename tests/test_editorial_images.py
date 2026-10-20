import copy
import io
import os
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from PIL import Image

import editorial_images as editorial
import magnific_generate_batch as generation
import prepare_image_urls as images
import threads_post as app
from test_reliability import HEADERS, post, row

NOW = datetime(2026,10,20,23,30,tzinfo=ZoneInfo('Asia/Ulaanbaatar'))


class EditorialImageTests(unittest.TestCase):
    def test_reviewed_image_only_matches_exact_future_pending_text_and_schedule(self):
        p=post(127,scheduled_at='2026-10-21 08:30')
        brief={'scheduled_at':p['scheduled_at'],'text_sha256':editorial.text_hash(p['text'])}
        self.assertTrue(editorial.eligible(p,brief,NOW))
        for change in ({'status':'posted'},{'status':'hold'},{'text':'edited'},
                       {'scheduled_at':'2026-10-22 08:30'}):
            with self.subTest(change=change):
                self.assertFalse(editorial.eligible(dict(p,**change),brief,NOW))
        self.assertFalse(editorial.eligible(p,brief,datetime(2026,10,22,tzinfo=NOW.tzinfo)))

    def test_generation_prioritizes_future_schedule_and_preserves_curated_images(self):
        queue=[post(99,scheduled_at='2026-10-21 08:30'),post(2,scheduled_at='2026-12-21 08:30'),
               post(3,scheduled_at='2026-10-19 08:30'),post(4,status='hold',scheduled_at='2026-10-21 08:30'),
               post(5,image_url='https://example.test/editorial/5.jpg',scheduled_at='2026-10-21 08:30'),
               post(6,text='Киноны график дизайн: Film',scheduled_at='2026-10-21 08:30')]
        self.assertEqual([p['id'] for p in generation.select_targets(queue,'pilot',1,NOW)],[99])

    def test_padding_preserves_outer_edges_of_wide_source(self):
        source=Image.new('RGB',(1200,600),'blue')
        source.paste('red',(0,0,30,600)); source.paste('lime',(1170,0,1200,600))
        data=io.BytesIO();source.save(data,'PNG')
        response=Mock(content=data.getvalue())
        with patch.object(generation.requests,'get',return_value=response):
            output,_=generation.normalized_jpeg('https://example.test/image.png')
        image=Image.open(io.BytesIO(output))
        self.assertEqual(image.size,(1080,1350))
        self.assertGreater(image.getpixel((10,675))[0],200)
        self.assertGreater(image.getpixel((1070,675))[1],200)

    def test_stale_editorial_text_cannot_receive_generated_image(self):
        original=[post(1,image_url=None)]
        latest=[post(1,text='New editorial content',image_url=None)]
        edited=[post(1,image_url='https://example.test/new.jpg')]
        self.assertEqual(images.merge_image_changes(latest,original,edited),[])

    def test_sheet_guard_rejects_edit_before_any_write(self):
        table=[HEADERS,list(row(text='Changed by editor').values())]
        with patch.object(app,'google_sheet_session',return_value=object()), \
             patch.object(app,'selected_sheet',return_value={'title':'Posts'}), \
             patch.object(app,'google_json',return_value={'valueRanges':[{'values':table}]}) as request, \
             patch.dict(os.environ,{'THREADS_SHEET_ID':'sheet'}):
            with self.assertRaisesRegex(RuntimeError,'Sheet changed'):
                images.sync_google_sheet([post(image_url='https://example.test/new.jpg')],[1],expected_posts=[post()])
            self.assertEqual(request.call_count,1)

    def test_force_assignment_cannot_overwrite_reviewed_illustration(self):
        q=[post(2,image_url='https://example.test/editorial/2.jpg'),
           post(3,image_url='https://example.test/manual-post-003.jpg')]
        before=copy.deepcopy(q)
        self.assertEqual(images.assign_images(q,'https://example.test',force=True),(0,0))
        self.assertEqual(q,before)
