"""Alta explícita de credencial propia; nunca recibe secretos por argumentos CLI."""
import argparse
import hashlib
import re
from pathlib import Path

from botsky.adapters.cloudflare_interpreter import read_credentials
from botsky.adapters.cloudflare_pool import read_private,owned_path,write_private


def register(root,pool_file,alias,credentials_file,replace=False):
    root=Path(root).absolute()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',alias):raise ValueError('invalid_alias')
    registry=owned_path(root,pool_file)
    registry.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    data=read_private(registry) if registry.exists() else {'version':1,'entries':[]}
    if set(data)!={'version','entries'} or type(data.get('version')) is not int or data.get('version')!=1 or not isinstance(data.get('entries'),list):raise ValueError('invalid_registry')
    reserved={'quota-state.json','authentication-state.json','pool-state.lock'}
    if registry.name in reserved or alias+'.json' in reserved or registry.name==alias+'.json':raise ValueError('registry_filename_collision')
    credentials=read_credentials(credentials_file)
    found=None
    for entry in data['entries']:
        old=read_credentials(owned_path(root,entry['credentials_file']))
        same=old['account_id'].lower()==credentials['account_id'].lower()
        if entry['id']==alias:
            if not replace:raise ValueError('alias_exists_use_replace')
            if not same:raise ValueError('replacement_must_keep_account')
            found=entry
        elif same:raise ValueError('duplicate_account_not_extra_quota')
    if found is None and len(data['entries'])>=10:raise ValueError('pool_max_accounts')
    relative=(Path(pool_file).parent/(alias+'.json')).as_posix()
    target=owned_path(root,relative)
    if target.exists() and found is None:raise ValueError('credential_target_exists')
    write_private(target,credentials)
    if found is None:data['entries'].append({'id':alias,'credentials_file':relative})
    else:found['credentials_file']=relative
    write_private(registry,data)
    return {'id':alias,'entries':len(data['entries']),'account_fingerprint':hashlib.sha256(credentials['account_id'].lower().encode()).hexdigest()[:12]}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True);p.add_argument('--pool-file',required=True)
    p.add_argument('--alias',required=True);p.add_argument('--credentials-file',type=Path,required=True)
    p.add_argument('--replace',action='store_true')
    import json
    print(json.dumps(register(**vars(p.parse_args()))))
