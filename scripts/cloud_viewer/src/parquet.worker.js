/* Keep DuckDB's message protocol separate from viewer transfer observations. */
performance.setResourceTimingBufferSize(4096);
performance.addEventListener('resourcetimingbufferfull',()=>performance.clearResourceTimings());
const session = new URL(self.location.href).searchParams.get('session');
const traffic = new BroadcastChannel('dataset-viewer-' + session);
if (typeof PerformanceObserver !== 'undefined') {
  new PerformanceObserver(list => {
    traffic.postMessage(list.getEntries().map(entry => ({
      name: entry.name,
      encodedBodySize: entry.encodedBodySize,
      transferSize: entry.transferSize,
      responseStatus: entry.responseStatus,
      duration: entry.duration,
    })));
  }).observe({ type: 'resource', buffered: true });
}
importScripts('./vendor/duckdb-browser-eh.worker.js');
