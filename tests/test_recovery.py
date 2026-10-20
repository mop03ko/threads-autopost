import copy
import unittest

from recover_failed_posts import assert_absent, candidates


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.expected={'id':7,'text':'Reviewed caption','original_text':'Original caption',
                       'scheduled_at':'2026-09-01 22:00'}
        self.plan={'posts':[self.expected]}
        self.failed={**self.expected,'status':'failed'}

    def test_published_original_or_revised_text_blocks_recovery(self):
        for text in ('Original caption','Reviewed caption','REVIEWED: caption!'):
            with self.subTest(text=text),self.assertRaisesRegex(RuntimeError,'possible existing'):
                assert_absent([self.expected],[{'id':'real','text':text}])
        assert_absent([self.expected],[{'text':'A completely unrelated topic about typography'}])

    def test_uncertain_publication_cannot_be_replayed(self):
        for status in ('processing','needs_review','pending','hold'):
            with self.subTest(status=status),self.assertRaisesRegex(RuntimeError,'requires review'):
                candidates(self.plan,[{**self.failed,'status':status}])
        self.assertEqual(candidates(self.plan,[self.failed]),[self.expected])

    def test_already_published_recovery_is_idempotent(self):
        self.assertEqual(candidates(self.plan,[{**self.failed,'status':'posted','threads_id':'real'}]),[])
        with self.assertRaisesRegex(RuntimeError,'lacks evidence'):
            candidates(self.plan,[{**self.failed,'status':'posted'}])

    def test_edited_caption_or_date_invalidates_review(self):
        for changes in ({'text':'Someone edited this'},{'scheduled_at':'2026-12-01 22:00'}):
            with self.subTest(changes=changes),self.assertRaisesRegex(RuntimeError,'changed'):
                candidates(self.plan,[{**self.failed,**changes}])
