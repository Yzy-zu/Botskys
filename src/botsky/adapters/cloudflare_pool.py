"""Pool privado: cuota por cuenta, elección previa y una petición por mensaje."""
import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .cloudflare_interpreter import CloudflareInterpreter, InterpreterError, MODEL, read_credentials


def read_private(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        mode=os.fstat(stream.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077 or mode.st_size>65536:
            raise InterpreterError('pool_file_permissions')
        return json.load(stream)


def owned_path(root,value):
    if type(value) is not str or not value or Path(value).is_absolute() or '..' in Path(value).parts:
        raise InterpreterError('pool_path_invalid')
    path=Path(root)/value
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise InterpreterError('pool_path_escape')
    current=path
    while current!=Path(root):
        if current.is_symlink():raise InterpreterError('pool_symlink')
        current=current.parent
    return path


def write_private(path,data):
    temporary=path.with_name('.'+path.name+'.'+uuid4().hex)
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def state_lock(path):
    """Serialize only short read/merge/write operations, including across processes."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise InterpreterError('pool_lock_permissions')
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def quota_state(path):
    state = read_private(path) if path.exists() else {'version': 1, 'paused_until': {}}
    if type(state) is not dict or set(state) != {'version', 'paused_until'} or type(state['version']) is not int or state['version'] != 1 or type(state['paused_until']) is not dict:
        raise InterpreterError('pool_state_invalid')
    for key, value in state['paused_until'].items():
        if not re.fullmatch(r'[0-9a-f]{64}', key) or type(value) is not str:
            raise InterpreterError('pool_state_invalid')
        until = datetime.fromisoformat(value)
        if until.tzinfo is None:
            raise InterpreterError('pool_state_invalid')
    return state


def authentication_state(path):
    state = read_private(path) if path.exists() else {'version': 1, 'blocked_credentials': {}}
    if type(state) is not dict or set(state) != {'version', 'blocked_credentials'} or type(state['version']) is not int or state['version'] != 1 or type(state['blocked_credentials']) is not dict:
        raise InterpreterError('pool_auth_state_invalid')
    for fingerprint, code in state['blocked_credentials'].items():
        if not re.fullmatch(r'[0-9a-f]{64}', fingerprint) or code not in ('provider_http_401', 'provider_http_403'):
            raise InterpreterError('pool_auth_state_invalid')
    return state


class CloudflarePool:
    provider_name = "cloudflare"

    def __init__(self,http,root,pool_file,*,model=MODEL,reasoning_effort=None,deadline_seconds=40,max_concurrency=2,clock=None,factory=CloudflareInterpreter):
        self.http,self.root=http,Path(root).absolute()
        self.path=owned_path(self.root,pool_file)
        self.state_path=self.path.with_name('quota-state.json')
        self.auth_path=self.path.with_name('authentication-state.json')
        self.lock_path=self.path.with_name('pool-state.lock')
        self.options=dict(model=model,reasoning_effort=reasoning_effort,deadline_seconds=deadline_seconds,max_concurrency=max_concurrency)
        self.clock=clock or (lambda:datetime.now(UTC))
        self.factory=factory
        self.providers={};self.cursor=0;self.last_metrics=None;self.paused_until=None
        self.last_credential_alias=None
        self.load()

    def load(self):
        # Only explicitly registered own credential files, never environment/pools from elsewhere.
        data=read_private(self.path)
        if type(data) is not dict or set(data)!={'version','entries'} or type(data['version']) is not int or data['version']!=1 or type(data['entries']) is not list or not 1<=len(data['entries'])<=10:
            raise InterpreterError('pool_registry_invalid')
        aliases=set();accounts=set();entries=[]
        self.credential_errors={}
        self.blocked_credentials=authentication_state(self.auth_path)['blocked_credentials']
        for entry in data['entries']:
            if type(entry) is not dict or set(entry)-{'id','credentials_file','enabled'} or not {'id','credentials_file'}<=set(entry):raise InterpreterError('pool_entry_invalid')
            alias=entry['id']
            if type(alias) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',alias) or alias in aliases or type(entry.get('enabled',True)) is not bool:raise InterpreterError('pool_entry_invalid')
            aliases.add(alias)
            if not entry.get('enabled',True):continue
            try:
                credential_path=owned_path(self.root,entry['credentials_file'])
                credentials=read_credentials(credential_path)
            except (OSError, ValueError):
                self.credential_errors[alias]='credential_unreadable_or_invalid'
                self.providers.pop(alias,None)
                continue
            key=hashlib.sha256(credentials['account_id'].lower().encode()).hexdigest()
            if key in accounts:raise InterpreterError('pool_duplicate_account')
            accounts.add(key)
            fingerprint=hashlib.sha256(json.dumps(credentials,sort_keys=True).encode()).hexdigest()
            if fingerprint in self.blocked_credentials:
                self.credential_errors[alias]=self.blocked_credentials[fingerprint]
                self.providers.pop(alias,None)
                continue
            cached=self.providers.get(alias)
            if cached is None or cached[0]!=fingerprint:
                cached=(fingerprint,self.factory(self.http,credentials,**self.options))
                self.providers[alias]=cached
            entries.append((alias,key,cached[1]))
        if not entries:raise InterpreterError('pool_no_healthy_accounts' if self.credential_errors else 'pool_no_enabled_accounts')
        self.entries=entries
        state=quota_state(self.state_path)
        self.pauses={key:datetime.fromisoformat(value) for key,value in state['paused_until'].items()}

    async def propose(self,messages,tools):
        self.last_metrics=None;self.paused_until=None;self.last_credential_alias=None
        self.load()
        now=self.clock()
        available=[e for e in self.entries if self.pauses.get(e[1],now)<=now]
        if not available:
            self.paused_until=min(self.pauses[e[1]] for e in self.entries)
            raise InterpreterError('daily_quota_pool')
        alias,key,provider=available[self.cursor%len(available)];self.cursor+=1
        provider.last_metrics=None
        credential_fingerprint=self.providers[alias][0]
        self.last_credential_alias = alias
        try:
            return await provider.propose(messages,tools)
        except InterpreterError as exc:
            if str(exc)=='daily_quota':
                until=provider.paused_until or (now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                with state_lock(self.lock_path):
                    state=quota_state(self.state_path)
                    existing=state['paused_until'].get(key)
                    if existing is None or datetime.fromisoformat(existing)<until:
                        state['paused_until'][key]=until.isoformat()
                    write_private(self.state_path,state)
                self.pauses={k:datetime.fromisoformat(v) for k,v in state['paused_until'].items()}
            elif str(exc) in ('provider_http_401','provider_http_403'):
                fingerprint=credential_fingerprint
                with state_lock(self.lock_path):
                    state=authentication_state(self.auth_path)
                    state['blocked_credentials'][fingerprint]=str(exc)
                    write_private(self.auth_path,state)
                self.blocked_credentials=state['blocked_credentials']
                self.credential_errors[alias]=str(exc)
            # Never retry a message with a second credential after an uncertain request.
            raise
        finally:
            if provider.last_metrics:
                self.last_metrics={**provider.last_metrics,'credential_alias':alias}
