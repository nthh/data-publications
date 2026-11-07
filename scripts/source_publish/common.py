"""Source API access using the official CLI's locked OAuth refresh cache.

Credential values never leave process memory or the existing OS credential store.
The CLI remains responsible for S3 credentials; this companion only obtains the
Ory access token required by Source's supported management API.
"""
from __future__ import annotations
import fcntl
import os
import subprocess
import shlex
import tempfile
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from urllib import request, parse, error

API = 'https://source.coop/api/v1'
ISSUER = 'https://auth.source.coop'
TOKEN_ENDPOINT = ISSUER + '/oauth2/token'
SERVICE = 'source-coop-cli'
ROLE = '_default'
USER_AGENT = 'data-publications/0.1 (Source Cooperative CLI companion)'


class AuthenticationError(RuntimeError): pass
class ApiError(RuntimeError):
    def __init__(self, status, response):
        self.status = status
        self.response = response
        super().__init__(f'Source API returned HTTP {status}; credential values are omitted.')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024*1024): h.update(chunk)
    return h.hexdigest()


class _NoRedirect(request.HTTPRedirectHandler):
    """Never forward an OAuth refresh grant to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_token_request(req):
    return request.build_opener(_NoRedirect()).open(req, timeout=45)


def _save_fallback_cache(path, value):
    """Replace the sole rotated-token copy atomically while the CLI lock is held."""

    serialized=json.dumps(value,separators=(',',':'))
    fd=None
    temporary=None
    try:
        fd, temporary=tempfile.mkstemp(prefix=f'.{ROLE}.',suffix='.tmp',dir=path.parent)
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            fd=None
            os.fchmod(out.fileno(),0o600)
            out.write(serialized)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary,path)
        directory_fd=os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if json.loads(path.read_text(encoding='utf-8'))!=value:
            raise AuthenticationError('Could not persist the rotated Source credential.')
    except Exception:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
        raise AuthenticationError('Could not persist the rotated Source credential.') from None


@contextmanager
def source_cache():
    """Use Apple's supported CLI for the exact Source generic-password item.

    All password output and command input use captured pipes. The write goes to
    security's stdin, never its process arguments, logs, or repository files.
    """
    argv=['security','find-generic-password','-s',SERVICE,'-a',ROLE,'-w']
    found=subprocess.run(argv,capture_output=True,text=True)
    if found.returncode==44:
        path=Path.home()/'Library/Caches/source-coop/credentials'/f'{ROLE}.json'
        if not path.is_file(): raise AuthenticationError('Source CLI login is required.')
        entry=json.loads(path.read_text())
        def save(value):
            _save_fallback_cache(path,value)
        yield entry,save
        return
    if found.returncode: raise AuthenticationError('Source credential-store access failed.')
    entry=json.loads(found.stdout)
    def save(value):
        serialized=json.dumps(value,separators=(',',':'))
        command='add-generic-password -U -s '+shlex.quote(SERVICE)+' -a '+shlex.quote(ROLE)+' -w '+shlex.quote(serialized)+'\n'
        saved=subprocess.run(['security','-i'],input=command,capture_output=True,text=True)
        check=subprocess.run(argv,capture_output=True,text=True)
        if saved.returncode or check.returncode or json.loads(check.stdout)!=value:
            raise AuthenticationError('Could not persist the rotated Source credential.')
    yield entry,save


def oauth_access_token():
    """Refresh once while holding the same per-role lock as source-coop 0.3.0.

    Retain a rotated refresh token before returning. Do not retry refresh grants:
    replaying a spent token can revoke the token family.
    """
    cache_dir=Path.home()/'Library/Caches/source-coop/credentials'
    cache_dir.mkdir(parents=True,exist_ok=True)
    try:
        discovery=json.load(request.urlopen(request.Request(ISSUER+'/.well-known/openid-configuration',headers={'User-Agent':USER_AGENT,'Accept':'application/json'}),timeout=30))
    except Exception: raise AuthenticationError('Could not read the Source OAuth discovery document.') from None
    endpoint=discovery.get('token_endpoint')
    if endpoint!=TOKEN_ENDPOINT:
        raise AuthenticationError('Unsafe OAuth discovery token endpoint.')
    with (cache_dir/(ROLE+'.lock')).open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            with source_cache() as (entry, save):
                return _refresh(entry, save, endpoint)
        except AuthenticationError: raise
        except Exception: raise AuthenticationError('Could not safely access or update the Source CLI credential cache.') from None


def _refresh(entry, save, endpoint):
    if endpoint!=TOKEN_ENDPOINT:
        raise AuthenticationError('Unsafe OAuth discovery token endpoint.')
    state=entry.get('refresh')
    if not state or not state.get('refresh_token'):
        raise AuthenticationError('Log in with Source CLI 0.3.0 to obtain refresh access.')
    if state.get('token_endpoint')!=endpoint or state.get('proxy_url')!='https://data.source.coop':
        raise AuthenticationError('Cached Source OAuth settings do not match the official service.')
    body=parse.urlencode({'grant_type':'refresh_token','refresh_token':state['refresh_token'],'client_id':state['client_id']}).encode()
    req=request.Request(endpoint,data=body,headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':USER_AGENT},method='POST')
    try:
        with _open_token_request(req) as resp: tokens=json.load(resp)
    except Exception: raise AuthenticationError('Source OAuth refresh failed; no token values were retained in output.') from None
    if tokens.get('refresh_token'):
        state['refresh_token']=tokens['refresh_token']
        save(entry)
    token=tokens.get('access_token')
    if not isinstance(token,str) or not token:
        raise AuthenticationError('Source OAuth response did not contain an API access token.')
    return token


class SourceApi:
    def __init__(self, token=None): self.token=token or oauth_access_token()
    def call(self, method, path, body=None):
        if method not in {'GET','POST','PATCH'} or not path.startswith('/') or path.startswith('//') or '#' in path or '\\' in path:
            raise ValueError('Unsupported Source API request.')
        payload=None if body is None else json.dumps(body).encode()
        req=request.Request(API+path,data=payload,method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/json','User-Agent':USER_AGENT,**({'Content-Type':'application/json'} if payload is not None else {})})
        try:
            with request.urlopen(req,timeout=60) as response:
                data=response.read();return response.status,json.loads(data) if data else None
        except error.HTTPError as exc:
            try: response=json.loads(exc.read(256000))
            except Exception: response={'error':'Non-JSON Source API error.'}
            raise ApiError(exc.code,response) from None
        except Exception: raise RuntimeError('Source API transport failed; request credentials are omitted.') from None
