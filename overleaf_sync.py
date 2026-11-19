"""Explicit Overleaf Cloud source synchronization; secrets live outside projects."""
import copy, difflib, json, os, re, shutil, subprocess, tempfile, uuid
from pathlib import Path
import latex_project as latex


def normalize_url(value):
    if not isinstance(value,str):raise ValueError('Enter an Overleaf project or Git URL.')
    value=value.strip().removeprefix('git clone ').strip()
    match=re.fullmatch(r'https://(?:git@)?git\.overleaf\.com/([a-zA-Z0-9]{6,80})/?',value)
    if not match:match=re.fullmatch(r'https://(?:www\.)?overleaf\.com/project/([a-zA-Z0-9]{6,80})/?',value)
    if not match:raise ValueError('Use an https://git.overleaf.com/project-id URL without a password.')
    return 'https://git@git.overleaf.com/'+match[1]


def git_failure(stderr):
    # Return only fixed messages. Git output may contain private URLs or credentials.
    detail = stderr.lower()
    status = re.search(rb"requested url returned error: ([0-9]{3})\b", detail)
    code = int(status[1]) if status else None
    if code and 500 <= code <= 599:
        return f'Overleaf Git is temporarily unavailable (HTTP {code}). Try previewing again later.'
    if code == 401 or b'authentication failed' in detail:
        return 'Overleaf rejected the Git credentials. Check the saved Git token.'
    if code == 403:
        return 'Overleaf denied Git access (HTTP 403). Check your project permissions and Git access.'
    if b'could not resolve host' in detail or b'failed to connect' in detail:
        return 'Git could not reach Overleaf. Check the network connection and try again.'
    if b'[rejected]' in detail and (b'non-fast-forward' in detail or b'fetch first' in detail):
        return 'Overleaf changed since the preview. Preview again before pushing.'
    return 'Overleaf Git operation failed. Preview again and check Git access if the problem persists.'


def private_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(path.parent,0o700)
    temp=path.with_name(uuid.uuid4().hex+'.tmp')
    try:
        with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(data,f)
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)


def hashes(data):return {n:latex.digest(v) for n,v in data.items()}


def merge_files(local,remote,base,resolutions=None):
    result={};rows=[];resolutions=resolutions or {}
    for name in sorted(set(local)|set(remote)|set(base)):
        left,right=local.get(name),remote.get(name)
        lh=latex.digest(left) if left is not None else None
        rh=latex.digest(right) if right is not None else None
        if lh==rh:chosen=left;kind='same'
        elif lh==base.get(name):chosen=right;kind='remote'
        elif rh==base.get(name):chosen=left;kind='local'
        else:
            kind='conflict';choice=resolutions.get(name)
            chosen=left if choice=='local' else right if choice=='remote' else None
        if kind!='same':rows.append({'path':name,'kind':kind,'localDeleted':left is None,'remoteDeleted':right is None})
        if chosen is not None:result[name]=chosen
    return result,rows


class Sync:
    def __init__(self,root,wid):
        self.root=Path(root)/'overleaf'/wid
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.root,0o700)
        self.config_path=self.root/'connection.json';self.repo=self.root/'repo.git';self.ticket_path=self.root/'preview.json'
        self.config=json.loads(self.config_path.read_text()) if self.config_path.exists() else {}

    def status(self):
        return {'connected':bool(self.config),'url':self.config.get('url',''),'lastSync':self.config.get('lastSync'),'hasToken':bool(self.config.get('token'))}

    def git(self,*args,data=None,index=None):
        # Ignore inherited Git configuration, credentials, hooks, tracing and repo overrides.
        env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','DRAFT_OVERLEAF_'))}
        env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0',GIT_LFS_SKIP_SMUDGE='1',LC_ALL='C')
        env.update(GIT_AUTHOR_NAME='Draft',GIT_AUTHOR_EMAIL='draft@localhost',GIT_COMMITTER_NAME='Draft',GIT_COMMITTER_EMAIL='draft@localhost')
        if index:env['GIT_INDEX_FILE']=str(index)
        # The helper contains no secret. The token never enters command arguments or Git config.
        helper=self.root/'askpass.sh'
        helper.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" git;; *) printf "%s\\n" "$DRAFT_OVERLEAF_TOKEN";; esac\n');os.chmod(helper,0o700)
        env.update(GIT_ASKPASS=str(helper),DRAFT_OVERLEAF_TOKEN=self.config.get('token',''))
        command=['git','-c','credential.helper=','-c','core.hooksPath='+os.devnull,'-c','http.followRedirects=false','-c','protocol.allow=never','-c','protocol.https.allow=always','--git-dir='+str(self.repo),*args]
        try:r=subprocess.run(command,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=90)
        except subprocess.TimeoutExpired:raise ValueError('Overleaf request timed out. Check the sync status before retrying.') from None
        if r.returncode:
            # Git diagnostics can contain authentication material; never forward raw output.
            raise ValueError(git_failure(r.stderr))
        return r.stdout

    def fetch(self):
        if not self.config:raise ValueError('Connect an Overleaf project first.')
        if not self.repo.exists():self.git('init','--bare',str(self.repo))
        refs=self.git('ls-remote','--symref',self.config['url'],'HEAD').decode()
        match=re.search(r'^ref: (refs/heads/[a-zA-Z0-9_/-]+)\tHEAD$',refs,re.M)
        if not match:raise ValueError('Overleaf project has no supported default branch.')
        branch=match[1]
        self.git('fetch','--no-tags','--depth=1',self.config['url'],branch)
        head=self.git('rev-parse','FETCH_HEAD').decode().strip()
        return head,branch,self.read_tree(head)

    def read_tree(self,head):
        entries=self.git('ls-tree','-rlz',head).split(b'\0');records=[];skipped=[];seen=set();total=0
        if len(entries)>2001:raise ValueError('Overleaf project exceeds 2000 files.')
        for entry in entries:
            if not entry:continue
            meta,name=entry.split(b'\t',1);mode,kind,oid,size=meta.split();name=name.decode('utf-8')
            if mode not in {b'100644',b'100755'} or kind!=b'blob':raise ValueError('Linked files and submodules are not supported.')
            try:latex.path_name(name)
            except ValueError:skipped.append(name);continue
            if name.casefold() in seen:raise ValueError('Overleaf contains duplicate file paths.')
            seen.add(name.casefold());total+=int(size)
            if int(size)>latex.MAX_FILE or total>latex.MAX_TOTAL:raise ValueError('Overleaf sources exceed the supported file size limits.')
            records.append((name,oid,int(size)))
        raw=self.git('cat-file','--batch',data=b''.join(oid+b'\n' for _,oid,_ in records)) if records else b''
        result={};offset=0
        for name,oid,size in records:
            end=raw.index(b'\n',offset);header=raw[offset:end].split()
            if header!=[oid,b'blob',str(size).encode()]:raise ValueError('Invalid Git object response.')
            content=raw[end+1:end+1+size];offset=end+size+2
            if Path(name).suffix.lower() in latex.TEXT_EXT:
                try:content.decode('utf-8')
                except UnicodeDecodeError:raise ValueError('Convert source files to UTF-8 before syncing.') from None
            result[name]=content
        return result,skipped

    def connect(self,url,token):
        url=normalize_url(url)
        if not token and url==self.config.get('url'):token=self.config.get('token')
        if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<33 for c in token):raise ValueError('Enter a valid Overleaf Git token.')
        old=self.config
        self.config={**(old if old.get('url')==url else {}),'url':url,'token':token}
        try:self.fetch()
        except Exception:self.config=old;raise
        private_json(self.config_path,self.config);self.ticket_path.unlink(missing_ok=True)
        return self.status()

    def disconnect(self):
        self.config_path.unlink(missing_ok=True);self.ticket_path.unlink(missing_ok=True);self.config={}
        return self.status()

    def preview(self,folder,state,direction):
        if direction not in {'pull','push'}:raise ValueError('Choose pull or push.')
        head,branch,(remote,skipped)=self.fetch();local=latex.files(folder)
        _,rows=merge_files(local,remote,self.config.get('base',{}));budget=120000
        for row in rows:
            name=row['path']
            if Path(name).suffix.lower() in latex.TEXT_EXT and budget>0:
                # Bound diff computation as well as the returned preview.
                left=local.get(name,b'')[:16000].decode('utf-8',errors='replace').splitlines()
                right=remote.get(name,b'')[:16000].decode('utf-8',errors='replace').splitlines()
                diff='\n'.join(difflib.unified_diff(left,right,fromfile='Local',tofile='Overleaf',n=2))[:min(4000,budget)]
                row['diff']=diff;budget-=len(diff)
        ticket={'id':uuid.uuid4().hex,'direction':direction,'head':head,'branch':branch,'local':hashes(local),'revision':state['revision'],'url':self.config['url']}
        private_json(self.ticket_path,ticket)
        return {'previewId':ticket['id'],'direction':direction,'changes':rows,'skipped':skipped,'firstSync':not bool(self.config.get('base')),'status':self.status()}

    def push(self,head,branch,remote,merged):
        index=self.root/(uuid.uuid4().hex+'.index')
        try:
            self.git('read-tree',head,index=index)
            for name in sorted(set(remote)|set(merged)):
                if remote.get(name)==merged.get(name):continue
                if name not in merged:self.git('update-index','--force-remove','--',name,index=index)
                else:
                    oid=self.git('hash-object','-w','--stdin',data=merged[name]).decode().strip()
                    self.git('update-index','--add','--cacheinfo','100644',oid,name,index=index)
            tree=self.git('write-tree',index=index).decode().strip()
            if tree==self.git('rev-parse',head+'^{tree}').decode().strip():return
            commit=self.git('commit-tree',tree,'-p',head,data=b'Sync saved LaTeX sources from Draft\n').decode().strip()
            self.git('push',self.config['url'],commit+':'+branch)
        finally:index.unlink(missing_ok=True)

    def apply(self,folder,state,preview_id,resolutions,save):
        if not self.ticket_path.exists():raise ValueError('Preview changes before syncing.')
        ticket=json.loads(self.ticket_path.read_text())
        if ticket['id']!=preview_id or ticket['revision']!=state['revision'] or ticket['url']!=self.config.get('url'):raise ValueError('The project changed. Preview again.')
        if not isinstance(resolutions,dict) or any(v not in {'local','remote'} for v in resolutions.values()):raise ValueError('Choose local or Overleaf for each conflict.')
        local=latex.files(folder)
        if hashes(local)!=ticket['local']:raise ValueError('Local sources changed. Preview again.')
        head,branch,(remote,skipped)=self.fetch()
        if head!=ticket['head'] or branch!=ticket['branch']:raise ValueError('Overleaf changed since the preview. Preview again.')
        merged,rows=merge_files(local,remote,self.config.get('base',{}),resolutions)
        if any(r['kind']=='conflict' and r['path'] not in resolutions for r in rows):raise ValueError('Resolve every conflict before syncing.')
        # Validate the entire proposed project before changing either side.
        with tempfile.TemporaryDirectory(prefix='overleaf-',dir=folder/'.latex') as temp:
            stage=Path(temp);updated=copy.deepcopy(state)
            # Keep local files outside the supported source set; never publish them.
            shutil.copytree(folder/'latex',stage/'latex')
            for name in set(local)-set(merged):latex.source_path(stage,name).unlink()
            for name,raw in merged.items():latex.write(latex.source_path(stage,name),raw)
            latex.refresh(stage,updated,True)
            if hashes(latex.files(folder))!=ticket['local']:raise ValueError('Local sources changed. Preview again.')
            if ticket['direction']=='push':self.push(head,branch,remote,merged)
            changed=hashes(local)!=hashes(merged)
            if changed:
                backup=folder/'.latex/history'/('overleaf-'+uuid.uuid4().hex);backup.parent.mkdir(parents=True,exist_ok=True)
                (folder/'latex').rename(backup)
                try:
                    (stage/'latex').rename(folder/'latex')
                    archive=stage/'.latex/archive'
                    if archive.exists():
                        for item in archive.iterdir():latex.write(folder/'.latex/archive'/item.name,item.read_bytes())
                    updated['revision']+=1;updated['updated']=latex.now();save(updated)
                except Exception:
                    shutil.rmtree(folder/'latex',ignore_errors=True);backup.rename(folder/'latex');save(state)
                    raise ValueError('Local update failed and was restored. Preview again to check the remote state.') from None
                state=updated
        self.config['base']=hashes(merged if ticket['direction']=='push' else remote)
        self.config['lastSync']=latex.now();private_json(self.config_path,self.config);self.ticket_path.unlink(missing_ok=True)
        return {'state':state,'status':self.status(),'changed':changed,'direction':ticket['direction']}
