import { verifiedRuntimeAssets } from './fetch-assets.mjs';
import { build } from 'esbuild';
import { mkdir, copyFile, readFile, writeFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join } from 'node:path';
import { createHash } from 'node:crypto';

const here = dirname(fileURLToPath(import.meta.url));
const outputIndex = process.argv.indexOf('--out');
const output = resolve(outputIndex < 0 ? join(here, 'dist') : process.argv[outputIndex + 1]);
await mkdir(join(output, 'vendor'), { recursive: true });
await build({
  entryPoints: [join(here, 'src/app.js')], outfile: join(output, 'app.js'),
  bundle: true, format: 'esm', target: 'es2022', platform: 'browser',
  minify: true, legalComments: 'linked', define: { 'process.env.NODE_ENV': '"production"' },
});
for (const name of ['index.html', 'parquet.worker.js', 'land.geojson']) {
  await copyFile(join(here, 'src', name), join(output, name));
}
for (const name of ['duckdb-eh.wasm', 'duckdb-browser-eh.worker.js']) {
  await copyFile(join(here, 'node_modules/@duckdb/duckdb-wasm/dist', name), join(output, 'vendor', name));
}
await copyFile(join(here,'node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs'),join(output,'vendor/maplibre-gl-worker.mjs'));
const lock = await readFile(join(here, 'package-lock.json'));
const runtimeAssets=await verifiedRuntimeAssets();
for(const asset of runtimeAssets){await mkdir(dirname(join(output,asset.destination)),{recursive:true});await copyFile(asset.path,join(output,asset.destination));}
const entries = {};
for (const name of ['index.html','app.js','app.js.LEGAL.txt','app.css','parquet.worker.js','land.geojson','vendor/duckdb-eh.wasm','vendor/duckdb-browser-eh.worker.js','vendor/maplibre-gl-worker.mjs']) {
  const bytes = await readFile(join(output,name));
  entries[name] = { size_bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
}
for(const asset of runtimeAssets)entries[asset.destination]={size_bytes:asset.size_bytes,sha256:asset.sha256};
await writeFile(join(output,'build.json'), JSON.stringify({
  schema_version: 1, package_lock_sha256: createHash('sha256').update(lock).digest('hex'),
  files: entries,
}, null, 2) + '\n');
console.log(JSON.stringify({output, files:Object.keys(entries).length, bytes:Object.values(entries).reduce((n,x)=>n+x.size_bytes,0)}));
