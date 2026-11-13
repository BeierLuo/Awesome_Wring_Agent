#!/usr/bin/env python3
"""Provision this Mac's external runtime and copy existing data without overwrites."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def install(source, destination):
    source, destination = Path(source).resolve(), Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('目标目录已存在；为保护论文与配置，不会覆盖：' + str(destination))
    runtime = Path(subprocess.check_output([str(source/'.venv/bin/python'), '-c', 'import sys; print(sys.base_prefix)'], text=True).strip())
    packages = source/'.venv/lib/python3.12/site-packages'
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.draft-install-', dir=destination.parent))
    try:
        shutil.copytree(runtime, stage/'runtime', symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(packages, stage/'runtime/lib/python3.12/site-packages', dirs_exist_ok=True, symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # Runtime links must remain self-contained after removing the original project.
        for path in (stage/'runtime').rglob('*'):
            if path.is_symlink() and not path.resolve().is_relative_to(stage/'runtime'):
                raise ValueError('运行环境包含外部链接：' + str(path.relative_to(stage)))
        data = stage/'data'
        data.mkdir(mode=0o700)
        for name in ('workspaces', 'style-library', '.local', 'agents', 'skills'):
            if (source/name).exists():
                shutil.copytree(source/name, data/name, ignore=shutil.ignore_patterns('__pycache__', '*.log', '.DS_Store'))
        tools = stage/'tools'
        if (source/'.tools').exists():
            shutil.copytree(source/'.tools', tools, ignore=shutil.ignore_patterns('.DS_Store'))
        else:
            tools.mkdir()
        for path in (data/'.local').rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        if (data/'.local').exists(): (data/'.local').chmod(0o700)
        subprocess.run([str(stage/'runtime/bin/python3.12'), '-I', '-B', '-c', 'import pymupdf, langgraph, langgraph.checkpoint.sqlite, certifi; import ssl; ssl.create_default_context(cafile=certifi.where()); print("Runtime verified")'], check=True, cwd=stage)
        (stage/'installation.json').write_text(json.dumps({'version': 1, 'architecture': os.uname().machine, 'python': '3.12', 'dataMigrated': True}))
        stage.rename(destination)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print('运行环境与数据已安装：' + str(destination))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path, default=Path.home()/'Library/Application Support/Draft')
    args = parser.parse_args()
    install(args.source, args.destination)
