// Transport contracts only. Browser rendering and real-server auth have separate checks.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source = await readFile(new URL('../web/api.js', import.meta.url), 'utf8');
const {HealthmonApi, ApiError} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status, headers: {'Content-Type': 'application/json'}
});

test('a caller retry preserves the original request ID and text after a lost connection', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({url, method: init.method, body: init.body});
    if (calls.length === 1) throw new TypeError('Connection lost');
    return json({request_id: 'same-request-001', response: {speech: '기억하고 있어.'}});
  });
  const api = new HealthmonApi();
  const text = '나는 달리기보다 걷는 게 좋아.';
  await assert.rejects(api.chat('pet-1', text, 'same-request-001'), error =>
    error instanceof ApiError && error.status === 0);
  assert.equal(calls.length, 1, 'transport must not silently send another request');
  const response = await api.chat('pet-1', text, 'same-request-001');
  assert.equal(response.request_id, 'same-request-001');
  assert.deepEqual(calls[0], calls[1]);
  assert.deepEqual(JSON.parse(calls[1].body), {text, request_id: 'same-request-001'});
});

test('browser transport uses same-origin cookies without sending a Bearer or producer secret', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({url, init});
    return json({authenticated: true});
  });
  const api = new HealthmonApi();
  await api.session();
  await api.state('pet-1');
  for (const {init} of calls) {
    assert.equal(init.credentials, 'same-origin');
    assert.ok(init.signal instanceof AbortSignal);
    const headers = new Headers(init.headers);
    assert.equal(headers.has('Authorization'), false);
    assert.equal(headers.has('X-Producer-Token'), false);
    assert.equal(headers.has('Cookie'), false, 'HttpOnly cookie is managed by the browser');
  }
  assert.equal(calls[0].url, '/beta/session');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), {});
  assert.equal(calls[1].init.method, 'GET');
  assert.equal(calls[1].init.body, undefined);
});

test('memory correction sends the old revision and registers the returned new revision', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({url, method: init.method, body: JSON.parse(init.body)});
    return json(calls.length === 1 ? {revision: 8, state_version: 23} : {memory_id: 'new-memory'});
  });
  const api = new HealthmonApi();
  const memory = {id: 'old-memory', source_id: 'message:source/a', source_revision: 7, slot: 'preference'};
  const edited = await api.editSource('pet 1', memory, '지금은 수영을 좋아해.');
  await api.registerMemory('pet 1', memory, edited.revision);
  assert.deepEqual(calls, [
    {url: '/pets/pet%201/sources/message%3Asource%2Fa', method: 'PATCH',
      body: {expected_revision: 7, text: '지금은 수영을 좋아해.'}},
    {url: '/pets/pet%201/memories', method: 'POST',
      body: {source_id: 'message:source/a', revision: 8, slot: 'preference'}}
  ]);
  assert.equal(memory.source_revision, 7, 'transport does not mutate UI-owned state');
});

test('quest conflict remains a 409 error for the presenter to refresh authoritative state', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls += 1;
    assert.equal(url, '/pets/pet-1/quests/offer-1/decision');
    assert.deepEqual(JSON.parse(init.body), {decision: 'accept'});
    return json({detail: 'State changed; request a fresh offer'}, 409);
  });
  await assert.rejects(new HealthmonApi().decide('pet-1', 'offer-1', 'accept'), error =>
    error instanceof ApiError && error.status === 409
      && error.message === 'State changed; request a fresh offer');
  assert.equal(calls, 1, 'stale quest approval must not be silently retried');
});

test('forget uses the memory revision and history is fetched from the canonical server endpoint', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({url, method: init.method});
    return json(calls.length === 1 ? {deleted: true} : {messages: []});
  });
  const api = new HealthmonApi('http://127.0.0.1:8000/');
  await api.forget('pet-1', {id: 'memory/a', source_revision: 4});
  const history = await api.history('pet-1');
  assert.deepEqual(history, {messages: []});
  assert.deepEqual(calls, [
    {url: 'http://127.0.0.1:8000/pets/pet-1/memories/memory%2Fa?expected_revision=4', method: 'DELETE'},
    {url: 'http://127.0.0.1:8000/pets/pet-1/messages?limit=50', method: 'GET'}
  ]);
});
