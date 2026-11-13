#!/usr/bin/env python3
"""Build the lightweight app and DMG; runtime and personal data remain external."""
from pathlib import Path
import plistlib
import argparse
import json
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description='默认仅构建 tmp 版；用户确认统一上线后才使用 --release --version。')
parser.add_argument('--release', action='store_true', help='生成正式发行包，不自动安装')
parser.add_argument('--version', help='正式发布版本，例如 0.4.0')
parser.add_argument('--plan', action='store_true', help='只显示输出位置，不构建或修改文件')
args = parser.parse_args()
if args.release and not args.version:
    parser.error('正式发布必须显式指定 --version；日常修改请使用默认 tmp 构建')
if args.version and (not args.release or not re.fullmatch(r'\d+\.\d+\.\d+', args.version)):
    parser.error('--version 仅用于正式发布，格式为 major.minor.patch')
released = {}
for released_info in (root/'dist/Caret.app/Contents/Info.plist', Path('/Applications/Caret.app/Contents/Info.plist'), root/'dist/Draft.app/Contents/Info.plist', Path('/Applications/Draft.app/Contents/Info.plist')):
    if released_info.exists():
        released = plistlib.loads(released_info.read_bytes())
        break
version = args.version if args.release else released.get('CFBundleShortVersionString', '0.3.0')
build_version = version if args.release else released.get('CFBundleVersion', '6')
channel = 'release' if args.release else 'tmp'
app = root / ('dist' if args.release else 'dist/tmp') / 'Caret.app'
if args.plan:
    print(json.dumps({'channel':channel,'version':version,'app':str(app),'dmg':str(app.parent/'Caret.dmg'),'install':False}, ensure_ascii=False, indent=2))
    raise SystemExit(0)
with tempfile.TemporaryDirectory(prefix='draft-build-') as staging:
    contents = Path(staging) / 'Caret.app/Contents'
    binary = contents / 'MacOS/Caret'
    resources = contents / 'Resources'
    binary.parent.mkdir(parents=True)
    resources.mkdir()
    subprocess.run(['xcrun', 'swiftc', '-O', '-module-cache-path', str(Path(staging) / 'cache'), '-target', subprocess.check_output(['uname', '-m'], text=True).strip() + '-apple-macosx12.0', str(root / 'macos/Draft.swift'), '-o', str(binary)], check=True)
    shutil.copy2(root / 'macos/serve.py', resources / 'serve.py')
    code = resources / 'app'
    code.mkdir()
    modules = ('server', 'localization', 'agent_files', 'gemini_stream', 'latex_project', 'openai_writer', 'overleaf_sync', 'paper_assistant', 'paper_tools', 'paragraph_selection', 'pdf_text', 'projects', 'preferences', 'style_library', 'style_memory', 'synctex_mapping', 'writing_agent')
    for module in modules:
        shutil.copy2(root / (module + '.py'), code)
    shutil.copytree(root / 'ui', code / 'ui', ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
    for directory in ('agents', 'skills'):
        for source in (root / directory).rglob('*.md'):
            target = code / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.copy2(root/'macos/caret.icns', resources/'caret.icns')
    info = dict(CFBundleName='Caret', CFBundleDisplayName='Caret', CFBundleIdentifier='local.paper.draft', CFBundleExecutable='Caret', CFBundlePackageType='APPL', CFBundleShortVersionString=version, CFBundleVersion=build_version, DraftBuildChannel=channel, CFBundleIconFile='caret', LSMinimumSystemVersion='12.0', NSHighResolutionCapable=True, NSAppTransportSecurity={'NSAllowsLocalNetworking': True})
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    subprocess.run(['codesign', '--force', '--sign', '-', str(contents.parent)], check=True)
    app.parent.mkdir(parents=True, exist_ok=True)
    if app.exists():
        shutil.rmtree(app)
    shutil.copytree(contents.parent, app)
print(app)
with tempfile.TemporaryDirectory(prefix='draft-dmg-') as folder:
    image = Path(folder)
    shutil.copytree(app, image / 'Caret.app')
    if args.release: (image / 'Applications').symlink_to('/Applications')
    (image / '安装说明.txt').write_text(('tmp 待发布版本：用于开发验证，请勿覆盖正式 App。\n' if not args.release else '') + '将 Caret.app 拖入 Applications 即可安装。\n本安装包适用于已准备好 Draft 运行环境的这台 Mac。\n应用数据与运行环境位于 ~/Library/Application Support/Draft，不依赖桌面源码目录。\n')
    dmg = app.parent / 'Caret.dmg'
    subprocess.run(['hdiutil', 'create', '-volname', 'Caret', '-srcfolder', str(image), '-ov', '-format', 'UDZO', str(dmg)], check=True)
    print(dmg)
