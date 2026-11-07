import { createHash } from 'node:crypto';

export const CAPTURE_RESOURCE_BYTES = 32 * 1024 * 1024;
export const CAPTURE_TOTAL_BYTES = 128 * 1024 * 1024;

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const header = (headers, name) => Object.entries(headers || {})
  .find(([key]) => key.toLowerCase() === name)?.[1] ?? null;

export class PortolanFooterCdpCapture {
  constructor(session, policy) {
    this.session = session;
    this.policy = policy;
    this.records = new Map();
    this.earlyRequestHeaders = new Map();
    this.waiters = [];
    this.fatal = null;
  }

  async start() {
    const session = this.session;
    session.on('Network.requestWillBeSent', event => {
      if (event.request?.url !== this.policy.object_url) return;
      if (this.records.has(event.requestId) || event.redirectResponse) {
        this.fail('CDP footer-prefix request ID was reused or redirected'); return;
      }
      const record = { request_id: event.requestId, url: event.request.url,
        method: event.request.method, request_range: header(event.request.headers, 'range'),
        extra_range: this.earlyRequestHeaders.get(event.requestId) || null,
        response: null, finished: false, body: null, capture_error: null };
      this.earlyRequestHeaders.delete(event.requestId);
      this.records.set(event.requestId, record);
      this.advance(record);
    });
    session.on('Network.requestWillBeSentExtraInfo', event => {
      const range = header(event.headers, 'range');
      const record = this.records.get(event.requestId);
      if (record) { record.extra_range = range; this.advance(record); }
      else if (range === this.policy.range) this.earlyRequestHeaders.set(event.requestId, range);
    });
    session.on('Network.responseReceived', event => {
      const record = this.records.get(event.requestId);
      if (!record) return;
      record.response = event.response;
      this.advance(record);
    });
    session.on('Network.loadingFinished', event => {
      const record = this.records.get(event.requestId);
      if (!record) return;
      record.finished = true;
      this.advance(record);
    });
    session.on('Network.loadingFailed', event => {
      const record = this.records.get(event.requestId);
      if (!record) return;
      record.capture_error = `CDP footer-prefix request failed: ${event.errorText || 'unknown'}`;
      this.advance(record);
    });
    await session.send('Network.enable', {
      maxResourceBufferSize: CAPTURE_RESOURCE_BYTES,
      maxTotalBufferSize: CAPTURE_TOTAL_BYTES,
    });
  }

  fail(message) {
    this.fatal = new Error(message);
    this.notify();
  }

  rangeFor(record) {
    if (record.request_range && record.extra_range && record.request_range !== record.extra_range) {
      this.fail('CDP request and extra-info Range headers differ');
    }
    return record.extra_range || record.request_range;
  }

  async capture(record) {
    try {
      const response = record.response;
      const range = this.rangeFor(record);
      const match = /^bytes=(\d+)-(\d+)$/.exec(this.policy.range);
      const length = Number(match[2]) - Number(match[1]) + 1;
      if (record.method !== 'GET' || range !== this.policy.range || response?.url !== this.policy.object_url ||
          response?.status !== 206 ||
          header(response.headers, 'content-range') !== `bytes ${match[1]}-${match[2]}/${this.policy.object_size_bytes}` ||
          Number(header(response.headers, 'content-length')) !== length) {
        throw new Error('CDP footer-prefix request or response identity differs from frozen policy');
      }
      const result = await this.session.send('Network.getResponseBody', { requestId: record.request_id });
      if (result?.base64Encoded !== true || typeof result.body !== 'string') {
        throw new Error('CDP did not return a binary base64 footer-prefix body');
      }
      const body = Buffer.from(result.body, 'base64');
      if (body.length !== length || body.length > CAPTURE_RESOURCE_BYTES || digest(body) !== this.policy.range_sha256) {
        throw new Error('CDP footer-prefix body length or SHA-256 differs from frozen policy');
      }
      record.body = body;
    } catch (error) {
      record.capture_error = `CDP footer-prefix body unavailable or invalid: ${error.message}`;
    }
    this.notify();
  }

  advance(record) {
    const range = this.rangeFor(record);
    if (record.capture_error) { this.notify(); return; }
    if (range === this.policy.range && record.finished && record.response && !record.body && !record.capturing) {
      record.capturing = true;
      void this.capture(record);
    }
    this.notify();
  }

  notify() {
    const waiters = this.waiters.splice(0);
    for (const wake of waiters) wake();
  }

  async bodyFor({ collectionId, url, range, timeoutMs = 30000 }) {
    if (collectionId !== 'grwl-raw' || url !== this.policy.object_url || range !== this.policy.range) {
      throw new Error('CDP capture requested for the wrong collection, URL, or range');
    }
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      if (this.fatal) throw this.fatal;
      const matches = [...this.records.values()].filter(record => this.rangeFor(record) === this.policy.range);
      if (matches.length > 1) throw new Error('Ambiguous CDP footer-prefix request identity');
      const record = matches[0];
      if (record?.capture_error) throw new Error(record.capture_error);
      if (record?.body) {
        return { body: record.body, evidence: {
          protocol: 'Chrome DevTools Network.getResponseBody', request_id: record.request_id,
          url: record.url, method: record.method, request_range: this.rangeFor(record),
          response_status: record.response.status,
          content_range: header(record.response.headers, 'content-range'),
          content_length: Number(header(record.response.headers, 'content-length')),
          body_bytes: record.body.length, body_sha256: digest(record.body), base64_encoded: true,
          max_resource_buffer_bytes: CAPTURE_RESOURCE_BYTES,
          max_total_buffer_bytes: CAPTURE_TOTAL_BYTES,
        } };
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) throw new Error('Matching CDP footer-prefix body was not captured before timeout');
      await new Promise(resolve => {
        const timer = setTimeout(() => { this.waiters = this.waiters.filter(item => item !== wake); resolve(); }, remaining);
        const wake = () => { clearTimeout(timer); resolve(); };
        this.waiters.push(wake);
      });
    }
  }
}
