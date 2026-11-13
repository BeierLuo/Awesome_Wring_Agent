"""Project catalog and reversible moves; paper contents and credentials stay intact."""
import json, os, subprocess, sys
from pathlib import Path

def project_folder(root,ident,trashed=False):
    import server
    server.safe_id(ident)
    base=root/'.trash' if trashed else root
    folder=base/ident
    if base.is_symlink() or folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError('Project 路径无效')
    return folder

def catalog(root,trashed=False):
    base=root/'.trash' if trashed else root
    if base.is_symlink():raise ValueError('Project 回收站路径无效')
    items=[]
    for path in base.glob('*/workspace.json'):
        try:
            folder=project_folder(root,path.parent.name,trashed)
            if path.is_symlink():continue
            state=json.loads(path.read_text())
            if state['id']!=folder.name:continue
            removed=json.loads((folder/'.project-trash.json').read_text()) if trashed else {}
            items.append({'id':state['id'],'name':state.get('name') or 'Untitled Project','updated':state.get('updated'),
                          'created':state.get('created'),'revision':state.get('revision',0),'type':'LaTeX' if state.get('latex') else 'PDF' if (folder/'original.pdf').is_file() else '文本',
                          'sections':len(state.get('sections',[])),'deletedAt':removed.get('deletedAt')})
        except (ValueError,KeyError,TypeError,OSError):continue
    return sorted(items,key=lambda p:p.get('deletedAt' if trashed else 'updated') or '',reverse=True)

def change(root,action,payload):
    import server
    ident=server.safe_id(payload.get('id'));trashed=action=='restore'
    folder=project_folder(root,ident,trashed)
    state=server.read_state(folder)
    if payload.get('revision')!=state['revision']:raise ValueError('Project 已有新修改，请刷新列表后重试')
    if action=='rename':
        name=payload.get('name')
        if not isinstance(name,str) or not 1<=len(name.strip())<=120 or any(ord(c)<32 for c in name):raise ValueError('名称需要1–120个字符，不能包含换行或控制字符')
        state['name']=name.strip();state['revision']+=1;state['updated']=server.now()
        server.atomic(folder/'workspace.json',json.dumps(state,ensure_ascii=False,indent=2))
    elif action=='trash':
        target=project_folder(root,ident,True)
        if target.exists():raise ValueError('回收站中已有同 ID 的 Project')
        target.parent.mkdir(exist_ok=True)
        server.atomic(folder/'.project-trash.json',json.dumps({'deletedAt':server.now()}))
        os.rename(folder,target)
    elif action=='restore':
        target=project_folder(root,ident)
        if target.exists():raise ValueError('已有同 ID 的 Project，恢复不会覆盖现有内容')
        state['revision']+=1;state['updated']=server.now()
        server.atomic(folder/'workspace.json',json.dumps(state,ensure_ascii=False,indent=2))
        os.rename(folder,target);(target/'.project-trash.json').unlink(missing_ok=True)
    else:raise ValueError('未知 Project 操作')
    return {'id':ident,'revision':state['revision'],'name':state.get('name')}


def reveal_pdf(root, ident):
    """Reveal the project PDF using a fixed path, never a client-supplied filename."""
    folder=project_folder(root,ident)
    state=json.loads((folder/'workspace.json').read_text())
    pdf=folder/('.latex/compiled.pdf' if state.get('latex') else 'original.pdf')
    if pdf.is_symlink() or pdf.parent.is_symlink() or not pdf.resolve().is_relative_to(folder.resolve()):
        raise ValueError('PDF 路径无效')
    if not pdf.is_file():
        raise ValueError('尚未生成 PDF，请先编译项目。' if state.get('latex') else '此项目尚未导入 PDF。')
    path=str(pdf.resolve())
    if sys.platform=='darwin':command=['open','-R',path]
    elif sys.platform=='win32':command=['explorer','/select,',path]
    else:command=['xdg-open',str(pdf.resolve().parent)]
    try:
        subprocess.run(command,check=True,timeout=10,capture_output=True)
    except (OSError,subprocess.SubprocessError):
        raise ValueError('无法打开文件管理器。PDF 位置：'+path) from None
    return {'path':path}
