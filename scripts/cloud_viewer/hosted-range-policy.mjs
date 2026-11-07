import { createHash } from 'node:crypto';

export const DEFAULT_RANGE_LIMIT = 16 * 1024 * 1024;
export const METADATA_RANGE_LIMIT = 32 * 1024 * 1024;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
const PARQUET_MIME = 'application/vnd.apache.parquet';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function parseRange(range, objectSize) {
  const match = /^bytes=(\d+)-(\d+)$/.exec(range || '');
  assert(match, 'Range must be a single closed byte interval');
  const start = Number(match[1]), end = Number(match[2]);
  assert(Number.isSafeInteger(start) && Number.isSafeInteger(end) && start <= end && end < objectSize,
    'Range is outside the planned object');
  return { start, end, length: end - start + 1 };
}

function isParquetObjectUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'data.source.coop' && !url.username && !url.password &&
      !url.port && !url.search && !url.hash && url.pathname.startsWith('/nthh/grwl-raw/') &&
      url.pathname.endsWith('.parquet');
  } catch {
    return false;
  }
}

function itemIsParquet(item) {
  return item && typeof item === 'object' && item.content_type?.split(';')[0].trim().toLowerCase() === PARQUET_MIME &&
    Number.isSafeInteger(item.size_bytes) && item.size_bytes > 0 && HEX_SHA256.test(item.sha256 || '');
}

function footerRangeAllowed(range, item, footerBytes) {
  if (!Number.isSafeInteger(footerBytes) || footerBytes <= 0) return false;
  const footerStart = item.size_bytes - 8 - footerBytes;
  if (!Number.isSafeInteger(footerStart) || footerStart < 4) return false;
  const metadataOnly = `bytes=${footerStart}-${item.size_bytes - 9}`;
  const metadataAndTrailer = `bytes=${footerStart}-${item.size_bytes - 1}`;
  return range === metadataOnly || range === metadataAndTrailer;
}

function exceptionMatches(url, range, item, policy) {
  if (!policy || policy.schema_version !== 1 || policy.kind !== 'grwl_parquet_footer_range' ||
      policy.dataset_id !== 'grwl-raw' || policy.case_id !== 'grwl-raw-mississippi-z7' ||
      policy.object_url !== url || policy.object_sha256 !== item.sha256 ||
      policy.object_size_bytes !== item.size_bytes || policy.range !== range ||
      !HEX_SHA256.test(policy.range_sha256 || '') || !itemIsParquet(item) || !isParquetObjectUrl(url)) return false;
  if (!footerRangeAllowed(range, item, policy.footer_metadata_bytes)) return false;
  try {
    return parseRange(range, item.size_bytes).length > DEFAULT_RANGE_LIMIT &&
      parseRange(range, item.size_bytes).length <= METADATA_RANGE_LIMIT;
  } catch {
    return false;
  }
}

export function validateMetadataPolicy(policy, { planSha, controlsSha, objects }) {
  assert(policy && typeof policy === 'object' && !Array.isArray(policy), 'Metadata policy must be an object');
  assert(policy.schema_version === 1 && policy.kind === 'grwl_parquet_footer_range', 'Unsupported metadata policy');
  assert(policy.dataset_id === 'grwl-raw' && policy.case_id === 'grwl-raw-mississippi-z7', 'Metadata policy case differs');
  assert(policy.max_requests_per_case === 1, 'Metadata policy request limit differs');
  assert(HEX_SHA256.test(planSha || '') && policy.plan_sha256 === planSha, 'Metadata policy plan pin differs');
  assert(HEX_SHA256.test(controlsSha || '') && policy.browser_controls_sha256 === controlsSha, 'Metadata policy controls pin differs');
  assert(isParquetObjectUrl(policy.object_url), 'Metadata policy URL is not an allowed GRWL Parquet object');
  assert(HEX_SHA256.test(policy.object_sha256 || '') && HEX_SHA256.test(policy.range_sha256 || ''), 'Metadata policy SHA-256 is malformed');
  assert(Number.isSafeInteger(policy.object_size_bytes) && policy.object_size_bytes > 0, 'Metadata policy object size is invalid');
  assert(Number.isSafeInteger(policy.footer_metadata_bytes) && policy.footer_metadata_bytes > 0, 'Metadata footer length is invalid');
  assert(typeof policy.range === 'string', 'Metadata policy range is missing');
  const item = objects instanceof Map ? objects.get(policy.object_url) : null;
  assert(itemIsParquet(item), 'Metadata policy object is absent or has the wrong MIME');
  assert(item.sha256 === policy.object_sha256 && item.size_bytes === policy.object_size_bytes, 'Metadata policy object identity differs from plan');
  assert(footerRangeAllowed(policy.range, item, policy.footer_metadata_bytes), 'Metadata policy range is not exactly the Parquet footer');
  const { length } = parseRange(policy.range, item.size_bytes);
  assert(length > DEFAULT_RANGE_LIMIT && length <= METADATA_RANGE_LIMIT, 'Metadata policy range length is outside the exception limit');
  return policy;
}

export function boundedRange(url, range, item, policy = null) {
  assert(item && Number.isSafeInteger(item.size_bytes) && item.size_bytes > 0, 'Planned object size is invalid');
  const { length } = parseRange(range, item.size_bytes);
  if (length <= DEFAULT_RANGE_LIMIT) return length;
  assert(length <= METADATA_RANGE_LIMIT && exceptionMatches(url, range, item, policy), 'Range exceeds the ordinary transfer limit');
  return length;
}

export function verifyRangeBody(url, range, item, body, policy = null) {
  const length = boundedRange(url, range, item, policy);
  assert(body && Number.isSafeInteger(body.byteLength), 'Range body must be a byte buffer');
  assert(body.byteLength === length, 'Range body length differs from requested interval');
  if (length <= DEFAULT_RANGE_LIMIT) return null;
  const rangeSha = createHash('sha256').update(body).digest('hex');
  assert(rangeSha === policy.range_sha256, 'Metadata range body SHA-256 differs from policy');
  return { kind: 'parquet_footer', range_sha256: rangeSha };
}
