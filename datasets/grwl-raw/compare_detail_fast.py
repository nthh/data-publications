#!/usr/bin/env python3
"""Exact all-detail comparison with an independent C++ protobuf-wire oracle.

The existing Python oracle supplies only PMTiles directory traversal and overview
layer checks. Detail MVT decoding, typed signatures and multiplicity comparison
are performed independently by detail_oracle.cpp. Unknown fields, duplicate
singular fields, over-wide uint32 fields and concatenated gzip are refused.
"""
from __future__ import annotations
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT/'research/grwl-multiscale-20261103/criteria.json'
NATIVE_SOURCE = Path(__file__).with_name('detail_oracle.cpp')
spec = importlib.util.spec_from_file_location('grwl_fast_container_reader',Path(__file__).with_name('compare_detail.py'))
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
FRAME = struct.Struct('<IIIBBHQQ')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def descriptor(path):
    path=Path(path)
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha256(path)}


def compile_oracle(build_dir):
    """Compile once using the system compiler; immutable artifacts carry pins."""
    build_dir=Path(build_dir)
    binary,record=build_dir/'detail-oracle',build_dir/'native-info.json'
    if record.exists():
        saved=json.loads(record.read_text())
        if (not binary.is_file() or saved['source']['sha256']!=sha256(NATIVE_SOURCE)
                or saved['binary']['sha256']!=sha256(binary)
                or saved['source_snapshot']['sha256']!=sha256(saved['source_snapshot']['path'])
                or saved['compiler']['sha256']!=sha256(saved['compiler']['path'])):
            raise ValueError('Existing native oracle build differs from its immutable pins')
        return binary,saved
    if binary.exists():
        raise FileExistsError('Refusing to overwrite unrecorded native oracle binary')
    if shutil.disk_usage(build_dir if build_dir.exists() else build_dir.parent).free < 40*2**30:
        raise RuntimeError('Native oracle compilation requires 40 GiB free disk')
    compiler=shutil.which('clang++')
    if Path('/usr/bin/xcrun').is_file():
        compiler=subprocess.run(['/usr/bin/xcrun','--find','clang++'],check=True,capture_output=True,text=True).stdout.strip()
    if not compiler:
        raise RuntimeError('System clang++ is required; no compiler download is authorized')
    compiler=Path(compiler).absolute()
    if not compiler.is_file():raise RuntimeError('System compiler is missing')
    version=subprocess.run([str(compiler),'--version'],check=True,capture_output=True,text=True).stdout
    build_dir.mkdir(parents=True,exist_ok=True)
    snapshot=build_dir/'detail_oracle.cpp'
    if snapshot.exists():
        raise FileExistsError('Refusing to overwrite native oracle source snapshot')
    shutil.copyfile(NATIVE_SOURCE,snapshot)
    sdk_flags=[];sdk=None
    if Path('/usr/bin/xcrun').is_file():
        sdk=Path(subprocess.run(['/usr/bin/xcrun','--show-sdk-path'],check=True,capture_output=True,text=True).stdout.strip())
        if not (sdk/'usr/include/c++/v1/algorithm').is_file():
            fallback=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk')
            if not (fallback/'usr/include/c++/v1/algorithm').is_file():
                raise RuntimeError('Installed macOS SDK lacks C++ standard headers')
            sdk=fallback.resolve()
        sdk_flags=['-isysroot',str(sdk),'-isystem',str(sdk/'usr/include/c++/v1')]
    argv=[str(compiler),*sdk_flags,'-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Werror',str(snapshot),'-lz','-o',str(binary)]
    completed=subprocess.run(argv,capture_output=True,text=True)
    if completed.returncode:
        raise RuntimeError('Native oracle compilation failed: '+completed.stderr[-4000:])
    runtime=subprocess.run([str(binary),'--version'],check=True,capture_output=True,text=True).stdout.strip()
    saved={'schema_version':1,'source':descriptor(NATIVE_SOURCE),'source_snapshot':descriptor(snapshot),
           'binary':descriptor(binary),'compiler':descriptor(compiler),'compiler_version':version,
           'command':argv,'runtime_version':runtime,'workers':1,
           'sdk':descriptor(sdk/'SDKSettings.json') if sdk is not None and (sdk/'SDKSettings.json').is_file() else None,
           'comparison':'exact vectors of ID/type/integer geometry/typed width/valid; sort fallback preserves multiplicity'}
    with record.open('x') as stream:
        json.dump(saved,stream,indent=2,sort_keys=True);stream.write('\n')
    return binary,saved


@contextmanager
def native_session(binary):
    process=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1024*1024)
    try:
        process.stdin.write(b'GRWLFC01')
        yield process
        process.stdin.close()
        if process.wait(timeout=30):
            raise ValueError('Native detail oracle failed: '+process.stderr.read().decode(errors='replace').strip())
    finally:
        if not process.stdin.closed:
            try:process.stdin.close()
            except BrokenPipeError:pass
        if process.poll() is None:
            try:process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
        process.stdout.close();process.stderr.close()


def compare_pair(process,xyz,old,new,old_compression,new_compression):
    def flag(compression):
        if compression==reference.Compression.NONE:return 0
        if compression==reference.Compression.GZIP:return 1
        raise ValueError('Unsupported PMTiles tile compression')
    header=FRAME.pack(*xyz,flag(old_compression),flag(new_compression),0,len(old),len(new))
    try:
        process.stdin.write(header);process.stdin.write(old);process.stdin.write(new);process.stdin.flush()
        ack=process.stdout.read(8)
    except BrokenPipeError:
        ack=b''
    if len(ack)!=8:
        process.wait(timeout=30)
        raise ValueError('Native detail oracle rejected '+str(xyz)+': '+process.stderr.read().decode(errors='replace').strip())
    return struct.unpack('<Q',ack)[0]


MAX_BATCH_TILES = 8


class NativeWorker:
    """One dedicated thread owns one persistent native session and its pipes."""
    def __init__(self,binary):
        self.binary=binary
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='grwl-detail-pipe')
        self.session=None
        self.process=None

    def _compare_batch(self,batch):
        if self.session is None:
            self.session=native_session(self.binary)
            self.process=self.session.__enter__()
        try:
            results=[]
            for a,b in batch:
                count=compare_pair(self.process,a[0],a[1],b[1],a[2],b[2])
                length=len(b[1]) if b[2]==reference.Compression.GZIP else len(gzip.compress(b[1],mtime=0))
                results.append((a[0],count,length))
            return results
        except BaseException:
            # Close on the owning thread, preserving the original frame error.
            try:self.session.__exit__(*sys.exc_info())
            finally:self.session=None;self.process=None
            raise

    def submit(self,batch):
        return self.executor.submit(self._compare_batch,batch)

    def _close_session(self):
        if self.session is not None:
            try:self.session.__exit__(None,None,None)
            finally:self.session=None;self.process=None

    def close(self):
        try:self.executor.submit(self._close_session).result()
        finally:self.executor.shutdown(wait=True)


def _validate_pipeline(workers,batch_tiles):
    if type(workers) is not int or workers not in (1,2):
        raise ValueError('Native detail workers must be 1 or 2')
    if type(batch_tiles) is not int or not 1<=batch_tiles<=MAX_BATCH_TILES:
        raise ValueError('Native detail batch must contain 1 through 8 tiles')


def compare(source,candidate,*,binary,allow_overview=False,maximum_tile_bytes=1048576,
            progress_every=10000,workers=1,batch_tiles=MAX_BATCH_TILES):
    """Align in the parent; bound each pipe owner to one outstanding batch.

    At most workers*batch_tiles compressed pairs are retained by the pipeline.
    Native processes retain the existing per-frame 256 MiB compressed payload
    and 512 MiB decoded payload bounds. No per-feature hashes are used.
    """
    _validate_pipeline(workers,batch_tiles)
    stats={'detail_tiles':0,'detail_features':0,'overview_tiles':0,'maximum_gzip_tile_bytes':0,
           'detail_tiles_over_byte_limit':0,'by_zoom':{}}
    sentinel=object()
    def collect(future):
        for xyz,count,length in future.result():
            stats['maximum_gzip_tile_bytes']=max(stats['maximum_gzip_tile_bytes'],length)
            stats['detail_tiles_over_byte_limit']+=int(length>maximum_tile_bytes)
            stats['detail_tiles']+=1;stats['detail_features']+=count
            zoom=str(xyz[0]);stats['by_zoom'][zoom]=stats['by_zoom'].get(zoom,0)+1
            if progress_every and stats['detail_tiles']%progress_every==0:
                print(json.dumps({'progress':stats}),flush=True)
    with reference.archive_tiles(source) as old,reference.archive_tiles(candidate) as new,ExitStack() as cleanup:
        owners=[]
        for _ in range(workers):
            owner=NativeWorker(binary);owners.append(owner);cleanup.callback(owner.close)
        left=iter(reference.detail_tiles(old,candidate=False,allow_overview=False,stats=stats))
        right=iter(reference.detail_tiles(new,candidate=True,allow_overview=allow_overview,stats=stats))
        pending=deque()
        submitted=0
        exhausted=False
        while not exhausted:
            # Consume the oldest result before filling the newly freed slot.
            # This bounds both retained bytes and each owner's executor queue.
            if len(pending)==workers:collect(pending.popleft())
            batch=[]
            for _ in range(batch_tiles):
                a,b=next(left,sentinel),next(right,sentinel)
                if a is sentinel and b is sentinel:
                    exhausted=True;break
                if a is sentinel or b is sentinel or a[0]!=b[0]:
                    raise ValueError(f'Detail tile coordinate mismatch: {None if a is sentinel else a[0]} / {None if b is sentinel else b[0]}')
                batch.append((a,b))
            if batch:
                pending.append(owners[submitted%workers].submit(batch));submitted+=1
        while pending:collect(pending.popleft())
    if not stats['detail_tiles']:raise ValueError('No detail tiles compared')
    return stats


def run(source,candidate,report,*,source_sha256,candidate_sha256=None,allow_overview=False,
        criteria_path=CRITERIA,native_build_dir=None,workers=1):
    _validate_pipeline(workers,MAX_BATCH_TILES)
    report=Path(report)
    if report.exists():raise FileExistsError('Refusing to overwrite immutable comparison report')
    report.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    result={'schema_version':1,'status':'failed','semantic_preservation':False,
            'source':descriptor(source),'candidate':descriptor(candidate),'comparator':descriptor(__file__),
            'criteria':descriptor(criteria_path),'directory_reader':descriptor(reference.__file__),
            'protobuf_implementation':'independent_cpp_wire_v1','workers':workers,
            'pipeline':{'batch_tiles':MAX_BATCH_TILES,'maximum_outstanding_batches':workers,
                        'maximum_outstanding_tile_pairs':workers*MAX_BATCH_TILES,
                        'pipe_ownership':'one dedicated thread per native process','result_order':'submission'},
            'packages':{name:importlib.metadata.version(name) for name in ('pmtiles','mapbox-vector-tile','protobuf')}}
    error=None
    try:
        if result['source']['sha256']!=source_sha256:raise ValueError('Source archive differs from sealed checksum')
        if candidate_sha256 and result['candidate']['sha256']!=candidate_sha256:raise ValueError('Candidate archive differs from expected checksum')
        binary,native=compile_oracle(native_build_dir or report.parent/'native-oracle')
        result['native_oracle']=native
        limit=json.loads(Path(criteria_path).read_text())['detail']['maximum_gzip_tile_bytes']
        result['counts']=compare(source,candidate,binary=binary,allow_overview=allow_overview,maximum_tile_bytes=limit,workers=workers)
        if sha256(source)!=result['source']['sha256'] or sha256(candidate)!=result['candidate']['sha256']:
            raise ValueError('Archive changed during comparison')
        if sha256(binary)!=native['binary']['sha256'] or sha256(NATIVE_SOURCE)!=native['source']['sha256']:
            raise ValueError('Native oracle changed during comparison')
        result['semantic_preservation']=True
        result['tile_byte_gate']=result['counts']['detail_tiles_over_byte_limit']==0
        result['status']='passed' if result['tile_byte_gate'] else 'failed'
        if not result['tile_byte_gate']:raise ValueError('Detail tile byte limit exceeded (semantic preservation passed)')
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}';error=exc
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    with report.open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    if error:raise error
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--allow-overview',action='store_true')
    parser.add_argument('--criteria',type=Path,default=CRITERIA)
    parser.add_argument('--native-build-dir',type=Path)
    parser.add_argument('--workers',type=int,choices=(1,2),default=1)
    args=parser.parse_args()
    result=run(args.source,args.candidate,args.report,source_sha256=args.source_sha256,
               candidate_sha256=args.candidate_sha256,allow_overview=args.allow_overview,
               criteria_path=args.criteria,native_build_dir=args.native_build_dir,workers=args.workers)
    print(json.dumps(result,sort_keys=True))
