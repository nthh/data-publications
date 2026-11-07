import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import {
  DEFAULT_RANGE_LIMIT,
  METADATA_RANGE_LIMIT,
  boundedRange,
  validateMetadataPolicy,
  verifyRangeBody,
} from '../hosted-range-policy.mjs';

const url = 'https://data.source.coop/nthh/grwl-raw/releases/r1/part-000.parquet';
const objectSha = 'a'.repeat(64);
const planSha = 'b'.repeat(64);
const controlsSha = 'c'.repeat(64);
const footerBytes = DEFAULT_RANGE_LIMIT + 37;
const objectSize = footerBytes + 8 + 4096;
const item = { sha256: objectSha, size_bytes: objectSize, content_type: 'application/vnd.apache.parquet' };
const objects = new Map([[url, item]]);
const footerStart = objectSize - 8 - footerBytes;
const metadataRange = `bytes=${footerStart}-${objectSize - 9}`;
const trailerRange = `bytes=${footerStart}-${objectSize - 1}`;
const rangeBody = length => Buffer.alloc(length, 0x5a);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function policy(range = metadataRange, extras = {}) {
  const length = range === metadataRange ? footerBytes : footerBytes + 8;
  return {
    schema_version: 1,
    kind: 'grwl_parquet_footer_range',
    dataset_id: 'grwl-raw',
    case_id: 'grwl-raw-mississippi-z7',
    max_requests_per_case: 1,
    plan_sha256: planSha,
    browser_controls_sha256: controlsSha,
    object_url: url,
    object_sha256: objectSha,
    object_size_bytes: objectSize,
    footer_metadata_bytes: footerBytes,
    range,
    range_sha256: sha(rangeBody(length)),
    ...extras,
  };
}
const pins = { planSha, controlsSha, objects };

test('validates and allows the exact metadata-only footer interval', () => {
  const exception = policy(metadataRange);
  assert.equal(validateMetadataPolicy(exception, pins), exception);
  assert.equal(boundedRange(url, metadataRange, item, exception), footerBytes);
  assert.deepEqual(verifyRangeBody(url, metadataRange, item, rangeBody(footerBytes), exception), {
    kind: 'parquet_footer', range_sha256: exception.range_sha256,
  });
});

test('validates and allows the exact metadata-plus-trailer interval', () => {
  const exception = policy(trailerRange);
  assert.equal(validateMetadataPolicy(exception, pins), exception);
  assert.equal(boundedRange(url, trailerRange, item, exception), footerBytes + 8);
  assert.deepEqual(verifyRangeBody(url, trailerRange, item, rangeBody(footerBytes + 8), exception), {
    kind: 'parquet_footer', range_sha256: exception.range_sha256,
  });
});

test('rejects one-byte range shifts that include bytes outside the footer', () => {
  for (const shifted of [`bytes=${footerStart - 1}-${objectSize - 9}`, `bytes=${footerStart + 1}-${objectSize - 9}`]) {
    assert.throws(() => validateMetadataPolicy(policy(shifted), pins), /exactly the Parquet footer/);
  }
});

test('rejects off-plan URL, object SHA, and object size', () => {
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { object_url: url.replace('part-000', 'part-001') }), pins), /absent or has the wrong MIME/);
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { object_sha256: 'd'.repeat(64) }), pins), /identity differs/);
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { object_size_bytes: objectSize + 1 }), pins), /identity differs/);
});

test('rejects changed plan and browser-control pins', () => {
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { plan_sha256: 'd'.repeat(64) }), pins), /plan pin differs/);
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { browser_controls_sha256: 'd'.repeat(64) }), pins), /controls pin differs/);
});

test('rejects malformed, open, suffix, multipart, and out-of-bounds ranges', () => {
  for (const range of ['bytes=0-', 'bytes=-32', 'bytes=0-1,4-5', 'bytes=x-y', `bytes=0-${objectSize}`]) {
    assert.throws(() => boundedRange(url, range, item), /single closed byte interval|outside the planned object/);
  }
});

test('rejects wrong body length and wrong metadata-range digest', () => {
  const exception = policy(metadataRange);
  assert.throws(() => verifyRangeBody(url, metadataRange, item, rangeBody(footerBytes - 1), exception), /body length/);
  assert.throws(() => verifyRangeBody(url, metadataRange, item, rangeBody(footerBytes), { ...exception, range_sha256: 'd'.repeat(64) }), /body SHA-256/);
});

test('rejects metadata exceptions above 32 MiB', () => {
  const largeFooterBytes = METADATA_RANGE_LIMIT + 1;
  const largeItem = { ...item, size_bytes: largeFooterBytes + 8 + 4096 };
  const largeUrl = url.replace('part-000', 'large-footer');
  const largeObjects = new Map([[largeUrl, largeItem]]);
  const start = largeItem.size_bytes - 8 - largeFooterBytes;
  const range = `bytes=${start}-${largeItem.size_bytes - 9}`;
  const exception = { ...policy(), object_url: largeUrl, object_size_bytes: largeItem.size_bytes,
    footer_metadata_bytes: largeFooterBytes, range, range_sha256: 'e'.repeat(64) };
  assert.throws(() => validateMetadataPolicy(exception, { ...pins, objects: largeObjects }), /outside the exception limit/);
});

test('rejects wrong MIME and userinfo object URLs', () => {
  const wrongMime = new Map([[url, { ...item, content_type: 'application/octet-stream' }]]);
  assert.throws(() => validateMetadataPolicy(policy(), { ...pins, objects: wrongMime }), /wrong MIME/);
  const userinfoPolicy = policy(metadataRange, { object_url: `https://alice:secret@${url.slice('https://'.length)}` });
  assert.throws(() => validateMetadataPolicy(userinfoPolicy, pins), /allowed GRWL Parquet object/);
});

test('keeps the ordinary 16 MiB range cap and accepts smaller closed ranges', () => {
  const smallRange = 'bytes=0-99';
  assert.equal(boundedRange(url, smallRange, item), 100);
  assert.equal(verifyRangeBody(url, smallRange, item, Buffer.alloc(100)), null);
  const overLimit = `bytes=0-${DEFAULT_RANGE_LIMIT}`;
  assert.throws(() => boundedRange(url, overLimit, item), /ordinary transfer limit/);
});

test('requires the designated case and one-request limit', () => {
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { case_id: 'other-case' }), pins), /case differs/);
  assert.throws(() => validateMetadataPolicy(policy(metadataRange, { max_requests_per_case: 2 }), pins), /request limit differs/);
});
