"""Offline regression tests. No credentials, live posts, or external writes."""
import base64
import copy
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
import yaml

import threads_post as app
import publishing
from queue_store import GitHubQueue, QueueConflict

CURRENT = app.parse_local('2026-10-20 22:05')
HEADERS = ['id', 'огноо_цаг', 'бичвэр', 'зургийн_холбоос', 'төлөв']


def post(item_id=1, **fields):
    value = dict(id=item_id, scheduled_at='2026-10-20 22:00', text='Шинэ бичвэр',
                 image_url=None, status='pending', synced_at=CURRENT.isoformat())
    value.update(fields)
    return value


def row(**fields):
    value = dict(zip(HEADERS, ['1', '2026-10-20 22:00', 'Бичвэр', '', 'pending']))
    value.update(fields)
    return value


class SheetTests(unittest.TestCase):
    def test_dates_and_integral_sheet_ids(self):
        result = app.parse_sheet_rows(HEADERS, [row(id='1.0', огноо_цаг='10/20/2026 10:00 PM')])
        self.assertEqual(result[0]['id'], 1)
        self.assertEqual(result[0]['scheduled_at'], '2026-10-20 22:00')

    def test_invalid_rows_reject_whole_snapshot(self):
        for bad in [row(id='1.5'), row(id='NaN'), row(id='0'), row(төлөв='pendng'),
                    row(төлөв=''), row(огноо_цаг='2026-02-30 22:00'), row(бичвэр=''),
                    row(бичвэр='а'*501), row(зургийн_холбоос='http://example.test/a.png')]:
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                app.parse_sheet_rows(HEADERS, [row(id='99'), bad])

    def test_duplicate_ids_and_headers_are_rejected(self):
        with self.assertRaises(RuntimeError):
            app.parse_sheet_rows(HEADERS, [row(), row(id='1.0')])
        with self.assertRaises(RuntimeError):
            app.parse_sheet_rows(HEADERS + ['status'], [row()])
        with self.assertRaises(RuntimeError):
            app.parse_sheet_rows(HEADERS[:-1], [row()])
        with self.assertRaises(RuntimeError):
            app.parse_sheet_rows(HEADERS, [])

    def test_bad_gid_never_falls_back(self):
        metadata = {'sheets':[{'properties':{'sheetId':42, 'title':'Posts', 'index':0}}]}
        with patch.dict(os.environ, {'THREADS_SHEET_GID':'123'}), patch.object(app, 'google_json', return_value=metadata):
            with self.assertRaises(RuntimeError):
                app.selected_sheet(object(), 'https://example.test')

    def test_authenticated_read_uses_selected_tab(self):
        data = {'valueRanges':[{'values':[HEADERS, list(row().values())]}]}
        with patch.object(app, 'google_sheet_session', return_value=object()), \
             patch.object(app, 'selected_sheet', return_value={'title':"Posts' tab"}), \
             patch.object(app, 'google_json', return_value=data) as google, \
             patch.dict(os.environ, {'THREADS_SHEET_ID':'sheet'}), \
             patch.object(app.requests, 'get', side_effect=AssertionError('CSV fallback forbidden')):
            self.assertEqual(app.fetch_sheet_rows()[0]['text'], 'Бичвэр')
            self.assertEqual(google.call_args.kwargs['params']['ranges'], "'Posts'' tab'!A1:Z10001")

    def test_failed_sync_does_not_write_local_or_remote(self):
        with patch.object(app, 'load_dotenv'), patch.object(app, 'fetch_sheet_rows', side_effect=RuntimeError('invalid')), \
             patch.object(app, 'save_json') as save, patch.object(app, 'remote_store') as store:
            with self.assertRaises(RuntimeError):
                app.cmd_sync(None)
            save.assert_not_called()
            store.assert_not_called()

    def test_merge_preserves_locked_and_failure_states(self):
        states = ['posted', 'processing', 'needs_review', 'failed', 'skipped']
        old = [post(i, status=s, text='original') for i,s in enumerate(states, 1)]
        rows = [post(i, text='edited') for i in range(1,6)]
        merged = publishing.merge_snapshot(old, rows, CURRENT.isoformat())
        self.assertEqual([p['status'] for p in merged], states)
        self.assertEqual([p['text'] for p in merged[:3]], ['original']*3)
        self.assertEqual(merged[3]['text'], 'edited')
        self.assertEqual(old[3]['text'], 'original')  # Pure merge, no caller mutation.

    def test_omitted_pending_becomes_hold_instead_of_disappearing(self):
        merged = publishing.merge_snapshot([post(), post(2,status='posted')], [post(3)], CURRENT.isoformat())
        states = {p['id']:p['status'] for p in merged}
        self.assertEqual(states, {1:'hold', 2:'posted', 3:'pending'})


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = GitHubQueue('owner/repo', 'test-only-token', session=Mock(headers={}))

    def blob(self, queue):
        return {'encoding':'base64', 'content':base64.b64encode(json.dumps(queue).encode()).decode()}

    def test_large_contents_fetches_exact_blob(self):
        # GitHub omits inline content for the production queue (>1 MB).
        with patch.object(self.queue, 'request', side_effect=[
            {'type':'file','sha':'immutable-sha','encoding':'none','content':''},
            self.blob([post()]),
        ]) as request:
            queue, sha = self.queue.read()
            self.assertEqual(sha, 'immutable-sha')
            self.assertEqual(queue, [post()])
            self.assertEqual(request.call_args.args, ('GET', '/git/blobs/immutable-sha'))

    def test_malformed_queue_ids_are_rejected(self):
        for value in [[post(),post()], [{'id':1.5}], [{'id':True}], [None]]:
            metadata = {'type':'file','sha':'s', **self.blob(value)}
            with self.subTest(value=value), patch.object(self.queue, 'request', return_value=metadata), self.assertRaises(RuntimeError):
                self.queue.read()

    def test_conflicting_claim_reloads_and_does_not_steal(self):
        def claim(queue):
            selected=[]
            for p in queue:
                if p['status']=='pending':
                    p['status']='processing'
                    selected.append(p['id'])
            return selected
        with patch.object(self.queue, 'read', side_effect=[([post()], 's1'), ([post(status='processing')], 's2')]), \
             patch.object(self.queue, 'request', side_effect=QueueConflict('race')) as request:
            selected, saved = self.queue.update(claim, 'claim')
            self.assertEqual(selected, [])
            self.assertEqual(saved[0]['status'], 'processing')
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.kwargs['json']['sha'], 's1')

    def test_failed_write_never_returns_claim(self):
        with patch.object(self.queue, 'read', return_value=([post()], 's1')), \
             patch.object(self.queue, 'request', side_effect=RuntimeError('offline')) as request:
            with self.assertRaises(RuntimeError):
                self.queue.update(lambda q:q[0].update(status='processing'), 'claim')
            self.assertEqual(request.call_count, 1)

    def test_noop_does_not_commit(self):
        with patch.object(self.queue, 'read', return_value=([post()], 's1')), patch.object(self.queue, 'request') as request:
            self.queue.update(lambda q:None, 'noop')
            request.assert_not_called()

    def test_network_error_does_not_leak_request(self):
        self.queue.session.request.side_effect = requests.ConnectionError('secret-token')
        with self.assertRaises(RuntimeError) as caught:
            self.queue.request('GET', '/contents/queue.json')
        self.assertNotIn('secret-token', str(caught.exception))


class MemoryStore:
    """Transactional test double: mutator failures do not change durable state."""
    def __init__(self, queue):
        self.queue = copy.deepcopy(queue)
        self.snapshots = []

    def update(self, mutate, message):
        fresh = copy.deepcopy(self.queue)
        result = mutate(fresh)
        self.queue = fresh
        self.snapshots.append(copy.deepcopy(fresh))
        return result, copy.deepcopy(fresh)


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        tmp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(tmp)/'queue.json'
        self.store = MemoryStore([post()])
        for target, name, value in [(app,'QUEUE_FILE',self.path), (app,'now',lambda:CURRENT),
                                    (app,'load_dotenv',Mock()), (publishing,'remote_store',lambda:self.store),
                                    (app,'ensure_fresh_token',Mock(return_value={'access_token':'test-only','user_id':'u'}))]:
            self.stack.enter_context(patch.object(target,name,value))
        self.api = self.stack.enter_context(patch.object(app,'api'))
        self.args = SimpleNamespace(live=True, sync=False, id=None, force=False)
        self.stack.enter_context(patch.dict(os.environ, {'THREADS_SYNC_MAX_AGE':'1800'}))

    def run_publisher(self):
        publishing.run(self.args, app)

    def success_api(self, method, url, **kwargs):
        state = self.store.queue[0]
        self.assertEqual(state['status'], 'processing')  # Durable before any API call.
        if url.endswith('/threads_publish'):
            self.assertEqual(state['publication_phase'], 'publishing')
            self.assertEqual(state['container_id'], 'container')
            return {'id':'published'}
        if method == 'GET':
            return {'status':'FINISHED'}
        return {'id':'container'}

    def test_success_is_checkpointed_and_second_run_is_noop(self):
        self.api.side_effect = self.success_api
        self.run_publisher()
        self.assertEqual(self.store.queue[0]['status'], 'posted')
        self.assertEqual(self.store.queue[0]['threads_id'], 'published')
        self.run_publisher()
        self.assertEqual(self.api.call_count,3)

    def test_ambiguous_publish_is_never_automatically_retried(self):
        def fail_publish(method,url,**kwargs):
            if url.endswith('/threads_publish'):
                raise RuntimeError('secret in timeout URL')
            return self.success_api(method,url,**kwargs)
        self.api.side_effect = fail_publish
        with self.assertRaises(RuntimeError):
            self.run_publisher()
        self.assertEqual(self.store.queue[0]['status'], 'needs_review')
        self.assertNotIn('secret', self.store.queue[0]['error'])
        self.args.id=[1]  # Explicit ID also cannot bypass unresolved ambiguity.
        self.run_publisher()
        self.assertEqual(self.api.call_count,3)

    def test_container_failure_does_not_publish(self):
        self.api.side_effect=[{'id':'container'}, {'status':'ERROR'}]
        with self.assertRaises(RuntimeError):
            self.run_publisher()
        self.assertEqual(self.store.queue[0]['status'], 'failed')
        self.assertEqual(self.api.call_count,2)

    def test_stale_or_missing_sync_blocks_before_meta(self):
        for stamp in [None, (CURRENT-timedelta(hours=1)).isoformat(), 'invalid']:
            self.store.queue=[post(synced_at=stamp)]
            with self.subTest(stamp=stamp), self.assertRaises(RuntimeError):
                self.run_publisher()
            self.api.assert_not_called()
            self.assertEqual(self.store.queue[0]['status'], 'pending')

    def test_claim_write_failure_blocks_meta(self):
        with patch.object(self.store,'update',side_effect=RuntimeError('offline')), self.assertRaises(RuntimeError):
            self.run_publisher()
        self.api.assert_not_called()

    def test_checkpoint_outage_after_publish_leaves_durable_processing(self):
        original=self.store.update
        def update(mutate,message):
            if self.api.call_count>=3:
                raise RuntimeError('github offline')
            return original(mutate,message)
        self.api.side_effect=self.success_api
        with patch.object(self.store,'update',side_effect=update), self.assertRaises(RuntimeError):
            self.run_publisher()
        self.assertEqual(self.store.queue[0]['status'],'processing')
        self.assertEqual(self.store.queue[0]['publication_phase'],'publishing')
        self.run_publisher()
        self.assertEqual(self.api.call_count,3)

    def test_abandoned_claim_goes_to_review(self):
        self.store.queue=[post(status='processing', processing_at='2026-10-20 21:00')]
        self.run_publisher()
        self.assertEqual(self.store.queue[0]['status'],'needs_review')
        self.api.assert_not_called()

    def test_late_posts_skip_and_future_posts_wait(self):
        self.store.queue=[post(scheduled_at='2026-10-19 22:00'),post(2,scheduled_at='2026-10-21 22:00')]
        self.run_publisher()
        self.assertEqual([p['status'] for p in self.store.queue],['skipped','pending'])
        self.api.assert_not_called()

    def test_dry_run_with_sync_never_mutates_files_or_remote(self):
        self.args.live=False
        self.args.sync=True
        app.save_json(self.path,[post()])
        before=self.path.read_bytes()
        with patch.object(app,'fetch_sheet_rows',return_value=[post(text='edited')]), \
             patch.object(self.store,'update',side_effect=AssertionError('remote write')):
            self.run_publisher()
        self.assertEqual(self.path.read_bytes(),before)
        self.api.assert_not_called()
        app.ensure_fresh_token.assert_not_called()

    def test_daily_limit_counts_unresolved_attempts(self):
        queue=[post(i,status='needs_review',attempted_at='2026-10-20 21:00') for i in range(1,16)]
        queue.append(post(16))
        selected,_=publishing.select_posts(queue,CURRENT,app)
        self.assertEqual(selected,[])

    def test_manual_batch_still_respects_per_run_limit(self):
        queue=[post(i,scheduled_at='2026-10-21 22:00') for i in range(1,6)]
        selected,_=publishing.select_posts(queue,CURRENT,app,only_ids=list(range(1,6)))
        self.assertEqual([p['id'] for p in selected],[1,2,3])


class WorkflowTests(unittest.TestCase):
    def test_scheduled_publish_fails_closed(self):
        workflow=yaml.safe_load(Path('.github/workflows/threads-post.yml').read_text())
        steps=workflow['jobs']['post']['steps']
        sync=next(s for s in steps if s.get('run')=='python threads_post.py sync')
        self.assertFalse(sync.get('continue-on-error',False))
        publish=next(s['run'] for s in steps if 'run --live' in s.get('run',''))
        self.assertNotIn('--force',publish)
        self.assertNotIn('git push',str(steps))
        self.assertEqual(workflow['concurrency']['cancel-in-progress'],False)
        self.assertEqual(workflow['jobs']['post']['env']['THREADS_LATE_GRACE'],'90')


if __name__ == '__main__':
    unittest.main()
