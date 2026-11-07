import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { PortolanFooterCdpCapture, CAPTURE_RESOURCE_BYTES, CAPTURE_TOTAL_BYTES } from '../portolan-cdp-capture.mjs';

const bytes = Buffer.from('PAR1\0approved browser footer prefix\0PAR1');
const sha = data => createHash('sha256').update(data).digest('hex');
const url = 'https://data.source.coop/nthh/grwl-raw/releases/r1/assets/rows.parquet';
const range = `bytes=100-${100 + bytes.length - 1}`;
const policy = { object_url: url, object_size_bytes: 1000, range, range_sha256: sha(bytes) };
const expectedContentRange = `bytes 100-${100 + bytes.length - 1}/1000`;

class FakeSession extends EventEmitter {
  constructor(body = bytes) {
    super(); this.calls = []; this.body = body; this.bodyError = null;
  }
  async send(method, params) {
    this.calls.push({ method, params });
    if (method === 'Network.enable') return {};
    if (method === 'Network.getResponseBody') {
      if (this.bodyError) throw this.bodyError;
      return { body: this.body.toString('base64'), base64Encoded: true };
    }
    throw new Error(`Unexpected CDP command ${method}`);
  }
}

function emitResponse(session, { id = 'request-1', requestUrl = url, requestRange = range,
  status = 206, responseRange = expectedContentRange, length = bytes.length, earlyExtra = false } = {}) {
  if (earlyExtra) session.emit('Network.requestWillBeSentExtraInfo', { requestId: id,
    headers: { Range: requestRange } });
  session.emit('Network.requestWillBeSent', { requestId: id,
    request: { url: requestUrl, method: 'GET', headers: earlyExtra ? {} : { Range: requestRange } } });
  session.emit('Network.responseReceived', { requestId: id, response: { url: requestUrl,
    status, headers: { 'Content-Range': responseRange, 'Content-Length': String(length) } } });
  session.emit('Network.loadingFinished', { requestId: id });
}

test('separate bounded Network session captures the exact browser request body', async () => {
  const session = new FakeSession();
  const capture = new PortolanFooterCdpCapture(session, policy);
  await capture.start();
  assert.deepEqual(session.calls[0], { method: 'Network.enable', params: {
    maxResourceBufferSize: CAPTURE_RESOURCE_BYTES, maxTotalBufferSize: CAPTURE_TOTAL_BYTES } });
  emitResponse(session, { earlyExtra: true });
  const result = await capture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 100 });
  assert.deepEqual(result.body, bytes);
  assert.equal(result.evidence.request_id, 'request-1');
  assert.equal(result.evidence.request_range, range);
  assert.equal(result.evidence.response_status, 206);
  assert.equal(result.evidence.body_sha256, policy.range_sha256);
  assert.equal(session.calls.filter(item => item.method === 'Network.getResponseBody').length, 1);
});

test('no Node refetch or fulfillment is issued; only Network.enable and getResponseBody', async () => {
  const session = new FakeSession();
  const capture = new PortolanFooterCdpCapture(session, policy);
  await capture.start(); emitResponse(session);
  await capture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 100 });
  assert.deepEqual(session.calls.map(item => item.method), ['Network.enable', 'Network.getResponseBody']);
});

test('missing, wrong-range, and ambiguous request identities fail', async () => {
  const missing = new PortolanFooterCdpCapture(new FakeSession(), policy);
  await missing.start();
  await assert.rejects(missing.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 5 }), /not captured/);
  const wrong = new FakeSession(); const wrongCapture = new PortolanFooterCdpCapture(wrong, policy);
  await wrongCapture.start(); emitResponse(wrong, { requestRange: 'bytes=0-31' });
  await assert.rejects(wrongCapture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 5 }), /not captured/);
  const duplicate = new FakeSession(); const duplicateCapture = new PortolanFooterCdpCapture(duplicate, policy);
  await duplicateCapture.start();
  emitResponse(duplicate, { id: 'one' }); emitResponse(duplicate, { id: 'two' });
  await assert.rejects(duplicateCapture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 100 }), /Ambiguous/);
});

test('wrong collection, URL, and range cannot retrieve a captured body', async () => {
  const session = new FakeSession(); const capture = new PortolanFooterCdpCapture(session, policy);
  await capture.start(); emitResponse(session);
  for (const change of [{ collectionId: 'lakeatlas' }, { url: url.replace('rows', 'other') },
    { range: 'bytes=0-31' }]) {
    await assert.rejects(capture.bodyFor({ collectionId: 'grwl-raw', url, range, ...change }), /wrong collection/);
  }
});

test('wrong CDP status, Content-Range, and Content-Length fail before body acceptance', async () => {
  for (const change of [{ status: 200 }, { responseRange: 'bytes 0-31/1000' }, { length: bytes.length + 1 }]) {
    const session = new FakeSession(); const capture = new PortolanFooterCdpCapture(session, policy);
    await capture.start(); emitResponse(session, change);
    await assert.rejects(capture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 100 }), /identity differs/);
    assert.equal(session.calls.filter(item => item.method === 'Network.getResponseBody').length, 0);
  }
});

test('evicted body, mismatched body hash, and mismatched body size fail closed', async () => {
  for (const [body, error] of [[bytes, new Error('Request content evicted')],
    [Buffer.from('different'), null], [bytes.subarray(1), null]]) {
    const session = new FakeSession(body); session.bodyError = error;
    const capture = new PortolanFooterCdpCapture(session, policy);
    await capture.start(); emitResponse(session);
    await assert.rejects(capture.bodyFor({ collectionId: 'grwl-raw', url, range, timeoutMs: 100 }),
      /unavailable or invalid/);
  }
});
