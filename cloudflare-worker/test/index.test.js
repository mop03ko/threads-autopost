import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { dispatchScheduled } from '../src/index.js';

const env = { GITHUB_TOKEN: 'test-only-token' };

test('cron only dispatches Actions, without a forced ID or Threads call', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({url, init});
    return new Response(null, { status: 204 });
  });
  assert.deepEqual(await dispatchScheduled(env), {status: 'dispatched'});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.github.com/repos/mop03ko/threads-autopost/actions/workflows/threads-post.yml/dispatches');
  assert.deepEqual(JSON.parse(calls[0].init.body), {ref: 'main'});
  assert.equal(calls[0].init.method, 'POST');
});

test('disabled scheduler and missing token perform no HTTP calls', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('unexpected HTTP'));
  assert.deepEqual(await dispatchScheduled({DISPATCH_ENABLED: 'false'}), {status: 'disabled'});
  await assert.rejects(dispatchScheduled({}), /GITHUB_TOKEN/);
  assert.equal(fetch.mock.callCount(), 0);
});

test('dispatch HTTP error does not expose the response body', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('secret body', {status: 403}));
  await assert.rejects(dispatchScheduled(env), {message: 'GitHub workflow dispatch HTTP 403'});
});

test('network exception is sanitized and cron failure propagates', async t => {
  t.mock.method(globalThis, 'fetch', async () => {throw new Error('secret URL');});
  t.mock.method(console, 'error', () => {});
  let task;
  await worker.scheduled({}, env, {waitUntil(promise) {task = promise;}});
  await assert.rejects(task, {message: 'GitHub workflow dispatch сүлжээний алдаа'});
});

test('health reports configuration only and is read-only', async t => {
  t.mock.method(globalThis, 'fetch', () => assert.fail('health must not dispatch'));
  const response = await worker.fetch(new Request('https://example.test/health'), env);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {service:'threads-autopost-dispatch', enabled:true, configured:true});
  assert.equal((await worker.fetch(new Request('https://example.test/health'), {})).status, 503);
  assert.equal((await worker.fetch(new Request('https://example.test/post'), env)).status, 404);
});
