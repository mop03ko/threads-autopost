import copy
import hashlib
import io
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from PIL import Image

import deploy_movie_posters as deployment
import editorial_images
import magnific_generate_batch
import movie_posters
import prepare_image_urls
from test_reliability import post

NOW = datetime(2026, 10, 21, tzinfo=ZoneInfo('Asia/Ulaanbaatar'))


class MoviePosterTests(unittest.TestCase):
    def test_title_matching_keeps_internal_colons_and_disambiguates_sequels(self):
        cases = {
            'Se7en: олон материалыг нэг өнгө аяст оруулах нь': 'se7en-1995',
            'Киноны график дизайн: Mad Max: Fury Road — Composition': 'mad-max-fury-road-2015',
            'Киноны график дизайн: 2001: A Space Odyssey — Type': '2001-a-space-odyssey-1968',
            'Киноны график дизайн: Blade Runner 2049 — Type': 'blade-runner-2049-2017',
            'Киноны график дизайн: Harry Potter — Мараудерын газрын зураг': 'harry-potter-and-the-prisoner-of-azkaban-2004',
            'Avatar icons for a website': None,
        }
        for title, key in cases.items():
            with self.subTest(title=title):
                self.assertEqual(movie_posters.movie_key(post(text=title)), key)

    def test_all_automatic_generic_image_paths_skip_known_and_unknown_films(self):
        for title in ['Se7en: notes', 'Киноны график дизайн: Unknown film — notes']:
            p = post(871, text=title, scheduled_at='2026-10-21 22:00')
            q = [copy.deepcopy(p)]
            self.assertEqual(prepare_image_urls.assign_images(q, 'https://example.test', True), (0, 0))
            self.assertEqual(q, [p])
            self.assertEqual(magnific_generate_batch.select_targets(q, 'all', 10, NOW), [])
            brief = dict(scheduled_at=p['scheduled_at'], text_sha256=editorial_images.text_hash(p['text']))
            self.assertFalse(editorial_images.eligible(p, brief, NOW))

    def test_publisher_rejects_missing_wrong_movie_or_unreviewed_posters(self):
        film = next(f for f in movie_posters.catalog()['films'] if f['key'] == 'se7en-1995')
        valid = 'https://example.test' + movie_posters.poster_path(film)
        movie_posters.validate_movie_poster(post(text='Se7en: notes', image_url=valid))
        for title, url in [('Se7en: notes', None), ('Se7en: notes', 'https://example.test/editorial/871.jpg'),
                           ('The Matrix: notes', valid), ('Киноны график дизайн: Unknown', valid)]:
            with self.subTest(title=title, url=url), self.assertRaises(RuntimeError):
                movie_posters.validate_movie_poster(post(text=title, image_url=url))

    def test_deployment_rejects_text_schedule_or_status_changes(self):
        p = post(871, text='Se7en: notes', scheduled_at='2026-10-21 22:00')
        binding = dict(film='se7en-1995', scheduled_at=p['scheduled_at'],
                       text_sha256=hashlib.sha256(p['text'].encode()).hexdigest())
        self.assertTrue(deployment.eligible(p, binding, NOW))
        for changes in ({'text':'Se7en: changed'}, {'status':'posted'}, {'status':'processing'},
                        {'status':'needs_review'}, {'scheduled_at':'2026-10-20 22:00'}):
            self.assertFalse(deployment.eligible(dict(p, **changes), binding, NOW))

    def test_poster_bytes_and_original_aspect_are_preserved(self):
        stream = io.BytesIO()
        Image.new('RGB', (400, 700), 'red').save(stream, 'JPEG')
        data = stream.getvalue()
        film = dict(key='test', source_url='https://example.test/poster.jpg',
                    source_sha256=hashlib.sha256(data).hexdigest(), dimensions=[400, 700])
        with patch.object(deployment.requests, 'get', return_value=Mock(content=data)):
            self.assertEqual(deployment.verified_poster(film), data)
            with self.assertRaisesRegex(RuntimeError, 'source changed'):
                deployment.verified_poster(dict(film, source_sha256='changed'))
