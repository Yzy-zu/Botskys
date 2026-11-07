"""Pool privado: cuota por cuenta, elección previa y una petición por mensaje."""
import hashlib
import json
import os
import re
import stat
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


class CloudflarePool:
    def __init__(self,http,root,pool_file,*,model=MODEL,reasoning_effort=None,deadline_seconds=40,max_concurrency=2,clock=None,factory=CloudflareInterpreter):
        self.http,self.root=http,Path(root).absolute()
        self.path=owned_path(self.root,pool_file)
        self.state_path=self.path.with_name('quota-state.json')
        self.options=dict(model=model,reasoning_effort=reasoning_effort,deadline_seconds=deadline_seconds,max_concurrency=max_concurrency)
        self.clock=clock or (lambda:datetime.now(UTC))
        self.factory=factory
        self.providers={};self.cursor=0;self.last_metrics=None;self.paused_until=None
        self.load()

    def load(self):
        # Only explicitly registered own credential files, never environment/pools from elsewhere.
        data=read_private(self.path)
        if type(data) is not dict or set(data)!={'version','entries'} or type(data['version']) is not int or data['version']!=1 or type(data['entries']) is not list or not 1<=len(data['entries'])<=10:
            raise InterpreterError('pool_registry_invalid')
        aliases=set();accounts=set();entries=[]
        for entry in data['entries']:
            if type(entry) is not dict or set(entry)-{'id','credentials_file','enabled'} or not {'id','credentials_file'}<=set(entry):raise InterpreterError('pool_entry_invalid')
            alias=entry['id']
            if type(alias) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',alias) or alias in aliases or type(entry.get('enabled',True)) is not bool:raise InterpreterError('pool_entry_invalid')
            aliases.add(alias)
            credential_path=owned_path(self.root,entry['credentials_file'])
            credentials=read_credentials(credential_path)
            key=hashlib.sha256(credentials['account_id'].lower().encode()).hexdigest()
            if key in accounts:raise InterpreterError('pool_duplicate_account')
            accounts.add(key)
            if not entry.get('enabled',True):continue
            fingerprint=hashlib.sha256(json.dumps(credentials,sort_keys=True).encode()).hexdigest()
            cached=self.providers.get(alias)
            if cached is None or cached[0]!=fingerprint:
                cached=(fingerprint,self.factory(self.http,credentials,**self.options))
                self.providers[alias]=cached
            entries.append((alias,key,cached[1]))
        if not entries:raise InterpreterError('pool_no_enabled_accounts')
        self.entries=entries
        state=read_private(self.state_path) if self.state_path.exists() else {'version':1,'paused_until':{}}
        if type(state) is not dict or set(state)!={'version','paused_until'} or type(state['version']) is not int or state['version']!=1 or type(state['paused_until']) is not dict:raise InterpreterError('pool_state_invalid')
        self.pauses={}
        for key,value in state['paused_until'].items():
            if not re.fullmatch(r'[0-9a-f]{64}',key) or type(value) is not str:raise InterpreterError('pool_state_invalid')
            until=datetime.fromisoformat(value)
            if until.tzinfo is None:raise InterpreterError('pool_state_invalid')
            self.pauses[key]=until

    async def propose(self,messages,tools):
        self.last_metrics=None;self.paused_until=None
        self.load()
        now=self.clock()
        available=[e for e in self.entries if self.pauses.get(e[1],now)<=now]
        if not available:
            self.paused_until=min(self.pauses[e[1]] for e in self.entries)
            raise InterpreterError('daily_quota_pool')
        alias,key,provider=available[self.cursor%len(available)];self.cursor+=1
        provider.last_metrics=None
        try:
            return await provider.propose(messages,tools)
        except InterpreterError as exc:
            if str(exc)=='daily_quota':
                until=provider.paused_until or (now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                self.pauses[key]=until
                write_private(self.state_path,{'version':1,'paused_until':{k:v.isoformat() for k,v in self.pauses.items()}})
            # Never retry a message with a second credential after an uncertain request.
            raise
        finally:
            if provider.last_metrics:
                self.last_metrics={**provider.last_metrics,'credential_alias':alias}
