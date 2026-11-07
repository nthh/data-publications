import { createHash } from 'node:crypto';

export const ORDINARY_RANGE_LIMIT = 16 * 1024 * 1024;
export const FOOTER_PREFIX_LIMIT = 32 * 1024 * 1024;
export const FROZEN_FOOTER_PROOF_SHA256 = '976d339c8484c913485b4d846c52fa60ddccb14620b9bfe2eab8ace038e757c3';
const TAIL_BYTES = 512 * 1024;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
const REQUIRED = [
  'schema_version', 'kind', 'collection_id', 'max_requests_per_collection',
  'browser_criteria_sha256', 'source_plan_sha256', 'pages_plan_sha256',
  'object_url', 'object_sha256', 'object_size_bytes', 'footer_metadata_bytes',
  'footer_metadata_start', 'footer_proof_sha256', 'range', 'range_sha256',
];
const DOCUMENTARY = ['recorded_at_utc', 'reason', 'failed_report', 'failed_report_sha256'];

function requireThat(ok, message) {
  if (!ok) throw new Error(message);
}

function parseRange(range, objectSize) {
  const match = /^bytes=(\d+)-(\d+)$/.exec(range || '');
  requireThat(match, 'Footer policy requires one closed byte range');
  const start = Number(match[1]), end = Number(match[2]);
  requireThat(Number.isSafeInteger(start) && Number.isSafeInteger(end) && start >= 0 &&
    end >= start && end < objectSize, 'Footer policy range is outside the planned object');
  return { start, end, length: end - start + 1 };
}

function sourceUrlIsSafe(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.host === 'data.source.coop' && !url.username &&
      !url.password && !url.search && !url.hash &&
      url.pathname.startsWith('/nthh/grwl-raw/releases/') && url.pathname.endsWith('.parquet') &&
      url.href === value;
  } catch { return false; }
}

export function validatePortolanFooterPolicy(policy, context) {
  requireThat(policy && typeof policy === 'object' && !Array.isArray(policy), 'Footer policy must be an object');
  requireThat(REQUIRED.every(key => Object.hasOwn(policy, key)) &&
    Object.keys(policy).every(key => REQUIRED.includes(key) || DOCUMENTARY.includes(key)),
  'Footer policy fields differ from the frozen schema');
  requireThat(policy.schema_version === 1 && policy.kind === 'official_browser_grwl_footer_prefix' &&
    policy.collection_id === 'grwl-raw' && policy.max_requests_per_collection === 1,
  'Footer policy schema, collection, or count differs');
  requireThat(context.ordinaryRangeMax === ORDINARY_RANGE_LIMIT, 'Ordinary Browser range ceiling changed');
  for (const [key, expected] of [
    ['browser_criteria_sha256', context.criteriaSha], ['source_plan_sha256', context.sourcePlanSha],
    ['pages_plan_sha256', context.pagesPlanSha],
  ]) {
    requireThat(HEX_SHA256.test(expected || '') && policy[key] === expected, `Footer policy ${key} pin differs`);
  }
  requireThat(policy.footer_proof_sha256 === FROZEN_FOOTER_PROOF_SHA256 &&
    context.footerProofSha === FROZEN_FOOTER_PROOF_SHA256, 'Footer policy structural proof pin differs');
  requireThat(sourceUrlIsSafe(policy.object_url) && HEX_SHA256.test(policy.object_sha256 || '') &&
    HEX_SHA256.test(policy.range_sha256 || ''), 'Footer policy object URL or digest is invalid');
  const object = context.objects instanceof Map ? context.objects.get(policy.object_url) : null;
  requireThat(object?.dataset_id === 'grwl-raw' &&
    object.content_type?.split(';')[0].trim().toLowerCase() === 'application/vnd.apache.parquet' &&
    object.sha256 === policy.object_sha256 && object.size_bytes === policy.object_size_bytes,
  'Footer policy object identity or MIME differs from immutable Source plan');
  requireThat(Number.isSafeInteger(policy.object_size_bytes) && policy.object_size_bytes > TAIL_BYTES + 8 &&
    Number.isSafeInteger(policy.footer_metadata_bytes) && policy.footer_metadata_bytes > 0 &&
    Number.isSafeInteger(policy.footer_metadata_start) && policy.footer_metadata_start >= 4 &&
    policy.footer_metadata_start === policy.object_size_bytes - 8 - policy.footer_metadata_bytes,
  'Footer policy Parquet footer boundary is invalid');
  const proof = context.footerProof;
  requireThat(proof?.schema_version === 1 && proof.status === 'local_structure_proof_not_browser_acceptance' &&
    proof.object_url === policy.object_url && proof.object_sha256 === policy.object_sha256 &&
    proof.remote_full_sha256 === policy.object_sha256 && proof.object_size_bytes === policy.object_size_bytes &&
    proof.metadata_start === policy.footer_metadata_start &&
    proof.footer_metadata_bytes === policy.footer_metadata_bytes && HEX_SHA256.test(proof.trailer_sha256 || '') &&
    proof.metadata_candidates_not_yet_allowed?.some(candidate =>
      candidate.range === `bytes=${policy.footer_metadata_start}-${policy.object_size_bytes - 9}` &&
      candidate.length === policy.footer_metadata_bytes && HEX_SHA256.test(candidate.sha256 || '')),
  'Footer policy differs from independently frozen structural proof');
  const range = parseRange(policy.range, object.size_bytes);
  requireThat(range.start === policy.footer_metadata_start &&
    range.end === policy.object_size_bytes - TAIL_BYTES - 1 &&
    range.length > ORDINARY_RANGE_LIMIT && range.length <= FOOTER_PREFIX_LIMIT,
  'Footer policy is not the exact metadata-only prefix or exceeds 32 MiB');
  return policy;
}

export function createPortolanFooterGuard(policy = null, ordinaryRangeMax = ORDINARY_RANGE_LIMIT) {
  requireThat(ordinaryRangeMax === ORDINARY_RANGE_LIMIT, 'Ordinary Browser range ceiling changed');
  let requested = 0, verified = 0;
  function authorize({ collectionId, url, range, object }) {
    requireThat(object && Number.isSafeInteger(object.size_bytes), 'Planned Source object is missing');
    const parsed = parseRange(range, object.size_bytes);
    if (parsed.length <= ordinaryRangeMax) return { length: parsed.length, exception: null };
    requireThat(policy && parsed.length <= FOOTER_PREFIX_LIMIT && requested < 1 &&
      collectionId === 'grwl-raw' && url === policy.object_url &&
      range === policy.range && object.sha256 === policy.object_sha256 &&
      object.size_bytes === policy.object_size_bytes && object.dataset_id === 'grwl-raw',
    'Range exceeds ordinary limit without the one exact GRWL footer-prefix allowance');
    requested += 1;
    return { length: parsed.length, exception: { kind: 'parquet_footer_prefix', range_sha256: policy.range_sha256 } };
  }
  function verify({ collectionId, url, range, object, body, exception }) {
    const parsed = parseRange(range, object.size_bytes);
    requireThat(body && Number.isSafeInteger(body.byteLength) && body.byteLength === parsed.length,
      'Source range body length differs from request');
    if (!exception) {
      requireThat(parsed.length <= ordinaryRangeMax, 'Oversized Source body lacks footer-prefix authorization');
      return null;
    }
    requireThat(policy && requested === 1 && verified === 0 && collectionId === 'grwl-raw' &&
      url === policy.object_url && range === policy.range &&
      object.sha256 === policy.object_sha256 && object.size_bytes === policy.object_size_bytes &&
      exception.kind === 'parquet_footer_prefix' && exception.range_sha256 === policy.range_sha256 &&
      parsed.length > ordinaryRangeMax && parsed.length <= FOOTER_PREFIX_LIMIT,
    'Footer-prefix response identity or exception count differs');
    const digest = createHash('sha256').update(body).digest('hex');
    requireThat(digest === policy.range_sha256, 'Live footer-prefix body SHA-256 differs from frozen policy');
    verified += 1;
    return { kind: 'parquet_footer_prefix', range_sha256: digest };
  }
  return { authorize, verify, counts: () => ({ requested, verified }) };
}
