import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import {
  ORDINARY_RANGE_LIMIT, FOOTER_PREFIX_LIMIT, FROZEN_FOOTER_PROOF_SHA256,
  createPortolanFooterGuard, validatePortolanFooterPolicy,
} from '../portolan-footer-policy.mjs';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const url = 'https://data.source.coop/nthh/grwl-raw/releases/r1/assets/rows.parquet';
const objectSha = 'a'.repeat(64);
const criteriaSha = 'b'.repeat(64);
const sourcePlanSha = 'c'.repeat(64);
const pagesPlanSha = 'd'.repeat(64);
const tail = 512 * 1024;
const footerStart = 4096;
const footerBytes = ORDINARY_RANGE_LIMIT + tail + 37;
const objectSize = footerStart + footerBytes + 8;
const prefixRange = `bytes=${footerStart}-${objectSize - tail - 1}`;
const prefixLength = objectSize - tail - footerStart;
const body = Buffer.alloc(prefixLength, 0x37);
const object = { url, dataset_id: 'grwl-raw', sha256: objectSha, size_bytes: objectSize,
  content_type: 'application/vnd.apache.parquet' };
const objects = new Map([[url, object]]);
const footerProof = { schema_version: 1, status: 'local_structure_proof_not_browser_acceptance',
  object_url: url, object_sha256: objectSha, remote_full_sha256: objectSha,
  object_size_bytes: objectSize, metadata_start: footerStart, footer_metadata_bytes: footerBytes,
  trailer_sha256: 'e'.repeat(64), metadata_candidates_not_yet_allowed: [
    { range: `bytes=${footerStart}-${objectSize - 9}`, length: footerBytes, sha256: 'f'.repeat(64) },
  ] };
const context = { criteriaSha, sourcePlanSha, pagesPlanSha, objects, footerProof,
  footerProofSha: FROZEN_FOOTER_PROOF_SHA256, ordinaryRangeMax: ORDINARY_RANGE_LIMIT };

function policy(overrides = {}) {
  return { schema_version: 1, kind: 'official_browser_grwl_footer_prefix',
    collection_id: 'grwl-raw', max_requests_per_collection: 1,
    browser_criteria_sha256: criteriaSha, source_plan_sha256: sourcePlanSha,
    pages_plan_sha256: pagesPlanSha, object_url: url, object_sha256: objectSha,
    object_size_bytes: objectSize, footer_metadata_bytes: footerBytes,
    footer_metadata_start: footerStart, footer_proof_sha256: FROZEN_FOOTER_PROOF_SHA256,
    range: prefixRange, range_sha256: sha(body), ...overrides };
}

test('exact metadata prefix is SHA checked and counted once', () => {
  const approved = validatePortolanFooterPolicy(policy(), context);
  const guard = createPortolanFooterGuard(approved);
  const request = guard.authorize({ collectionId: 'grwl-raw', url, range: prefixRange, object });
  assert.equal(request.length, prefixLength);
  assert.deepEqual(guard.counts(), { requested: 1, verified: 0 });
  assert.deepEqual(guard.verify({ collectionId: 'grwl-raw', url, range: prefixRange,
    object, body, exception: request.exception }),
  { kind: 'parquet_footer_prefix', range_sha256: sha(body) });
  assert.deepEqual(guard.counts(), { requested: 1, verified: 1 });
});

test('policy pins original criteria, Source plan, Pages plan, and structural proof', () => {
  for (const key of ['browser_criteria_sha256', 'source_plan_sha256', 'pages_plan_sha256', 'footer_proof_sha256']) {
    assert.throws(() => validatePortolanFooterPolicy(policy({ [key]: '0'.repeat(64) }), context), /pin differs/);
  }
  assert.throws(() => validatePortolanFooterPolicy(policy(), { ...context, footerProofSha: '0'.repeat(64) }), /pin differs/);
  assert.throws(() => validatePortolanFooterPolicy(policy(), { ...context, footerProof: { ...footerProof, metadata_start: 5 } }),
    /structural proof/);
  assert.throws(() => validatePortolanFooterPolicy(policy(), { ...context, ordinaryRangeMax: ORDINARY_RANGE_LIMIT + 1 }),
    /Ordinary Browser range ceiling changed/);
});

test('policy rejects wrong object, MIME, collection, count, and unrecognized fields', () => {
  assert.throws(() => validatePortolanFooterPolicy(policy({ object_url: url.replace('rows', 'other') }), context), /identity or MIME/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ object_sha256: '0'.repeat(64) }), context), /identity or MIME/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ object_size_bytes: objectSize + 1 }), context), /identity or MIME/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ collection_id: 'lakeatlas' }), context), /collection/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ max_requests_per_collection: 2 }), context), /count/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ max_requests_per_collection: true }), context), /count/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ bypass: true }), context), /fields differ/);
  const wrongMime = new Map([[url, { ...object, content_type: 'application/octet-stream' }]]);
  assert.throws(() => validatePortolanFooterPolicy(policy(), { ...context, objects: wrongMime }), /identity or MIME/);
});

test('only the exact metadata prefix can exceed 16 MiB', () => {
  for (const range of [
    `bytes=${footerStart - 1}-${objectSize - tail - 1}`,
    `bytes=${footerStart + 1}-${objectSize - tail - 1}`,
    `bytes=${footerStart}-${objectSize - tail}`,
    `bytes=${footerStart}-${objectSize - 9}`,
  ]) assert.throws(() => validatePortolanFooterPolicy(policy({ range }), context), /exact metadata-only prefix/);
  assert.throws(() => validatePortolanFooterPolicy(policy({ footer_metadata_start: footerStart - 1 }), context), /footer boundary/);
  const hugeFooter = FOOTER_PREFIX_LIMIT + tail + 1;
  const hugeObject = { ...object, size_bytes: footerStart + hugeFooter + 8 };
  const hugeObjects = new Map([[url, hugeObject]]);
  const hugePolicy = policy({ object_size_bytes: hugeObject.size_bytes, footer_metadata_bytes: hugeFooter,
    range: `bytes=${footerStart}-${hugeObject.size_bytes - tail - 1}` });
  const hugeProof = { ...footerProof, object_size_bytes: hugeObject.size_bytes, footer_metadata_bytes: hugeFooter,
    metadata_candidates_not_yet_allowed: [{ range: `bytes=${footerStart}-${hugeObject.size_bytes - 9}`,
      length: hugeFooter, sha256: 'f'.repeat(64) }] };
  assert.throws(() => validatePortolanFooterPolicy(hugePolicy,
    { ...context, objects: hugeObjects, footerProof: hugeProof }), /exceeds 32 MiB/);
});

test('ordinary requests stay bounded with or without the policy', () => {
  const small = 'bytes=0-127';
  for (const approved of [null, validatePortolanFooterPolicy(policy(), context)]) {
    const guard = createPortolanFooterGuard(approved);
    const request = guard.authorize({ collectionId: 'grwl-raw', url, range: small, object });
    assert.deepEqual(request, { length: 128, exception: null });
    assert.equal(guard.verify({ collectionId: 'grwl-raw', url, range: small,
      object, body: Buffer.alloc(128), exception: null }), null);
    assert.deepEqual(guard.counts(), { requested: 0, verified: 0 });
  }
  const guard = createPortolanFooterGuard();
  assert.throws(() => guard.authorize({ collectionId: 'grwl-raw', url, range: prefixRange, object }), /ordinary limit/);
  for (const range of ['bytes=0-', 'bytes=-10', 'bytes=1-2,4-5', `bytes=0-${objectSize}`]) {
    assert.throws(() => guard.authorize({ collectionId: 'grwl-raw', url, range, object }), /closed byte range|outside/);
  }
});

test('exception refuses wrong collection, URL, range, count, body length and body SHA', () => {
  const approved = validatePortolanFooterPolicy(policy(), context);
  for (const change of [
    { collectionId: 'lakeatlas' }, { url: url.replace('rows', 'other') },
    { range: `bytes=${footerStart}-${objectSize - tail}` },
  ]) {
    const guard = createPortolanFooterGuard(approved);
    assert.throws(() => guard.authorize({ collectionId: 'grwl-raw', url, range: prefixRange, object, ...change }),
      /ordinary limit/);
  }
  const guard = createPortolanFooterGuard(approved);
  const request = guard.authorize({ collectionId: 'grwl-raw', url, range: prefixRange, object });
  assert.throws(() => guard.authorize({ collectionId: 'grwl-raw', url, range: prefixRange, object }), /ordinary limit/);
  assert.throws(() => guard.verify({ collectionId: 'grwl-raw', url, range: prefixRange,
    object, body: body.subarray(1), exception: request.exception }), /body length/);
  const changed = Buffer.from(body); changed[0] ^= 1;
  assert.throws(() => guard.verify({ collectionId: 'grwl-raw', url, range: prefixRange,
    object, body: changed, exception: request.exception }), /body SHA-256/);
  assert.deepEqual(guard.counts(), { requested: 1, verified: 0 });
  guard.verify({ collectionId: 'grwl-raw', url, range: prefixRange, object, body, exception: request.exception });
  assert.throws(() => guard.verify({ collectionId: 'grwl-raw', url, range: prefixRange,
    object, body, exception: request.exception }), /exception count/);
});
