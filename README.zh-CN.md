# Caret · 本地论文写作工作区

[English](README.md)

正式版本下载：[Caret 0.3.4](https://github.com/BeierLuo/Awesome_Wring_Agent/releases/tag/v0.3.4)。安装前请阅读运行环境要求。

每次修改与发布记录见 [CHANGELOG.md](CHANGELOG.md)，记录规则见 [AGENTS.md](AGENTS.md)。

Caret 是运行在本机浏览器中的论文写作工具，支持 PDF 和 LaTeX 项目。Gemini 或 OpenAI 模型负责写作与润色，GPT 按需查证资料、处理 PDF 章节和分析参考论文风格。修改内容经用户确认后保存，并保留历史版本。

## 主要功能

- **PDF 项目**：导入论文、识别目录、逐节提取原稿、编辑 Markdown 和预览数学公式。
- **LaTeX 项目**：导入 ZIP、本地解析章节、编辑源码、确认修改后写回 `.tex`、导出源码 ZIP；macOS 可使用 Tectonic 编译 PDF。
- **按需查证**：搜索论文、读取最新章节或指定 PDF 页面，返回带来源的证据。
- **写作参考**：导入参考论文，分析表达与论证结构，检索范例，生成章节写作策略。
- **项目管理**：搜索、重命名、回收站与恢复；保存章节版本、对话及项目记忆。
- **可编辑规则**：通过 `agents/` 和 `skills/` 调整角色与任务说明。

## 安装与启动

需要 Python 3.10+。在项目目录创建独立环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

Windows 下可使用 `.venv\Scripts\python.exe -m pip install -r requirements.txt` 和 `.venv\Scripts\python.exe server.py`。

打开 <http://127.0.0.1:8768/>。纯英文界面位于 <http://127.0.0.1:8768/en/>，也可点击顶栏的 English / Chinese 切换。两个版本共享项目和 API 配置，论文、对话及规则文件内容保持原文。macOS 安装好依赖后，也可双击 `Launch Caret.command`。

可选启动参数：

```bash
python server.py --port 8769 --no-open
python server.py --root /path/to/private-workspaces
```

`--root` 只改变论文工作区位置；API 配置与全局参考论文库仍位于应用目录。服务绑定本机回环地址，按个人本地工具设计。

### 配置模型

在网页的 API 设置中配置自己的服务与凭据：

- 写作：Google Cloud Vertex AI（Express Key、标准项目 Key 或本机 ADC），或 Gemini Developer API。
- 资料助理、PDF 章节处理和风格分析：OpenAI API。
- 使用 ADC 时，需要本机安装 Google Cloud CLI 并完成 `gcloud auth application-default login`。

模型名称、Google Cloud 项目和地区请按自己的账号权限填写；界面默认值不保证对所有账号可用。凭据通过设置界面保存到 `.local/api-config.json`，应用将目录权限设为 `700`、文件权限设为 `600`。不要把凭据写入源码或角色规则。

本地存储不代表离线推理：调用模型时会发送任务所需的章节、参考片段或页面图像，并产生对应服务的费用。参考论文分析会分批发送可提取的论文文字。

### 可选：LaTeX 编译

安装 Tectonic，并确保 `tectonic` 可在 `PATH` 中找到；也支持将适合本机平台的可执行文件放在 `.tools/tectonic`。本仓库不附带本地编译器或缓存。

当前隔离编译流程支持 macOS；其他系统仍可编辑和导出源码。首次编译可能下载 TeX 宏包，不支持所有需要 LuaLaTeX、外部脚本或额外工具链的项目。

## 双栏写作与 PDF 预览

LaTeX 项目使用左侧章节导航、中间 Assistant / Source、右侧常驻 PDF 的布局。Source 页可编辑项目源文件，点击保存后再用 Recompile 编译；编译成功会自动刷新 PDF 并保留当前页，失败时保留上次成功的结果。预览默认适应整页，支持连续滚动、页码跳转、缩放、适应宽度及拖动分隔条调整宽度。PDF 按需加载页面；窄屏下编辑区与预览上下排列。输入框顶部的横条可上下拖动调整高度，自动记住大小，双击恢复默认。

当前章节类型可手动确认：先在左侧选中章节，再展开「项目与设置 → 写作策略 · 论文库」，在「当前章节类型」选择 Motivation 等类型，点击「确认章节类型」。类型按章节保存，下一条消息即可使用，无需先生成或选用写作方案；不修改章节标题和正文。写作策略关闭时，类型仍可保存，需启用策略后才用于规则与范例检索。

## 基本使用

1. 创建 Project，导入 PDF 或 LaTeX ZIP。
2. PDF 项目等待章节识别与原稿提取完成；LaTeX 项目直接从源码分节。
3. 选择章节，输入修改要求。资料不足时，写作 Agent 按需请求 GPT 查证。
4. 查看建议与拟写入稿，确认后保存新版本。模型回复不会直接覆盖原稿。
5. 按需上传参考论文、查看版本或导出项目。

扫描 PDF 可能需要先添加 OCR 文字层；复杂 LaTeX 宏和动态包含关系可能需要手动调整。新安装的参考库与风格记忆为空，需要自行导入论文并生成分析。

## 代码结构

| 文件 / 目录 | 用途 |
| --- | --- |
| `server.py` | 本地 HTTP 服务、配置、项目 API 与模型请求 |
| `writing_agent.py` | LangGraph 写作流程与工具协调 |
| `paper_assistant.py` / `paper_tools.py` | GPT 资料查证与本地论文读取 |
| `gemini_stream.py` | Gemini 流式响应处理 |
| `latex_project.py` | ZIP 导入、源码分节、写回与编译 |
| `projects.py` | 项目列表、重命名及回收站 |
| `style_library.py` / `style_memory.py` | 参考论文库、风格记忆与写作策略 |
| `agent_files.py` / `agents/` / `skills/` | 角色、技能与项目记忆管理 |
| `ui/` | 无需前端构建的浏览器界面 |
| `ui/vendor/` | Markdown、消毒与公式渲染库、字体及第三方许可证 |
| `tests/` | Python 与 JavaScript 测试 |

## 本地数据与 Git 上传范围

`.gitignore` 默认忽略所有文件，仅放行已明确列出的源码、前端资源、角色/技能说明、测试和安装文档。增加新代码文件时，需同步检查放行规则。

以下内容留在本机，不进入 Git：

| 路径 | 内容 |
| --- | --- |
| `.local/` | API 密钥、配置及规则历史 |
| `workspaces/` | 论文、LaTeX 源稿、对话、章节版本、记忆、检查点与回收站 |
| `style-library/` | 参考 PDF、分析结果和个人风格记忆 |
| `work/` | 本地工作产物 |
| `.venv/`、`.python/`、`.tools/` | 本机运行环境、工具与缓存 |
| `README.txt` | 旧的本机使用说明，保留在本地 |

环境文件、私钥、数据库、日志、临时文件和依赖目录也被排除。`agents/`、`skills/` 属于共享应用规则，会上传；不要在其中写个人论文内容或密钥。新增私人资料应放入上述本地目录。

首次提交前检查：

```bash
git add .
git diff --cached --stat
git diff --cached
```

`.gitignore` 不会阻止 `git add -f`，也不能移除已提交的秘密。不要强制添加本地目录；若凭据曾被提交或公开，应撤销并更换凭据，再清理历史。

## 测试

```bash
python -m unittest discover -s tests -v
node tests/test_ui.cjs
npm ci --prefix tests --ignore-scripts
node tests/test_markdown.cjs
```

JavaScript 测试需要 Node.js；渲染专项测试还需要安装 `tests/package.json` 中的开发依赖。模型测试使用模拟响应，不需要真实 API Key；真实模型连通性需要在设置中单独验证。

## Overleaf 同步

打开本地 LaTeX 项目后，点击 Assistant / Source 旁边的 **Overleaf 同步**。填写 Overleaf 项目地址或 Git 地址，以及在 Overleaf 账户设置中生成的 Git 访问令牌，点击连接。此版本支持 Overleaf Cloud，项目需要具有 Git 集成权限；暂不支持自建 Overleaf 服务。

- **预览获取 Overleaf 修改**：查看双方差异，确认后更新本地源文件和章节，保留仅在本地发生的修改。
- **预览推送到 Overleaf**：合并双方文件后推送。双方都改过的文件需要逐个选择保留本地或 Overleaf 的完整文件；差异面板仅显示节选。首次连接也会核对差异，不假设本地稿与远端拥有共同版本。
- 预览后如果任一方又发生变化，必须重新预览。推送不强制覆盖远端历史。
- 同步保留可匹配章节的对话和版本；移除的章节归档在本地。更新源文件后，点击重新编译以刷新 PDF。
- 仅同步项目 `latex/` 中支持的论文源文件和资源。Overleaf 上不支持的文件保留原样；本地对话、项目记忆、API 配置和编译日志不上传。

连接与令牌保存在 `.local/overleaf/<workspace-id>/connection.json`，权限仅限当前系统用户，不包含在源码导出或 Git 提交中。断开连接会删除本地令牌，但不会撤销 Overleaf 账户中的令牌。同步源文件备份保存在项目的 `.latex/history/overleaf-*`。目前为手动文件级同步，不提供逐字实时协作，也不迁移 Overleaf 评论和修订标记。

### OpenAI 写作服务

在「API 设置 → 写作服务」选择 **OpenAI API**，填写 OpenAI API Key，并填写独立的「OpenAI 写作模型 ID」。留空时使用资料助理模型。写作模型需支持 Responses API、工具调用和图像输入；资料助理继续使用自己的模型配置。支持流式预览、按需查证、风格工具及页面图像，修改仍需确认后才写入文件。配置保存在本机，不随论文备份导出。

会话菜单位于输入框下方，可创建新会话或切回当前章节/全文讨论的历史会话继续聊天；切换保留稿件、版本和每个会话的待发送输入。旧版清空上下文留下的消息会保留为历史会话（仅能恢复最后一次清空的分界）。

输入框右下角可直接选择已配置服务的写作模型；API 设置中每个服务的“更多可切换模型”支持填写多个逗号分隔的模型 ID。切换作用于下一条消息，生成中锁定模型；圆形发送按钮在生成时变为停止。新会话和历史菜单位于对话区上方。

模型菜单旁的思考强度可选默认、low、medium、high，按模型记住本机选择。OpenAI 使用 Responses 的 reasoning.effort，Gemini 4 及已支持的 Gemini 3 型号使用 thinkingConfig.thinkingLevel；未知或旧型号保留默认，不发送不兼容参数。选择仅影响写作模型，生成中不可切换。

点名参考论文时，写作 Agent 和资料助理可通过 search_reference_papers 按论文名、简称、作者或年份检索整个本地库，再用 read_reference_paper 读取指定章节。摘要原文直接按 PDF 标题边界读取，不依赖风格例句是否被选中；风格例句为空时会给出过滤原因。

### PDF 双击定位源码

LaTeX 项目重新编译后，双击 PDF 中的文字位置即可切换到 Source，打开对应文件并选中源代码行。支持缩放后的预览和 `\input` 子文件。旧项目需重新编译一次以生成 SyncTeX 映射；源码有未保存修改或 PDF 已过期时，请先保存并重新编译。定位精度取决于 TeX 的 SyncTeX 记录，公式、宏和图片可能指向附近的命令行。

PDF 预览支持拖动选择文字并复制，鼠标移到页面上显示文字选择光标。双击仍跳转源码；文字层随缩放对齐并按需加载。扫描图片中没有嵌入文字的内容暂不支持选词。

### Sites 远程工作区

`sites/draft-remote/` 是独立的私有 Sites 项目，复用本地界面；`remote_bridge.py` 让 Mac 主动领取远程请求。文件、版本记录、模型密钥和 LaTeX 编译环境仍在本机。Sites 仅暂存请求和返回结果，完成后删除；Mac 离线时远程保存不会被标成成功。连接配置在忽略提交的 `.local/sites-bridge.json`，保持权限 0600。

运行 `.venv/bin/python remote_bridge.py` 启动连接。云端 API 设置只读，需在本机修改密钥。单次远程请求上限 16 MB，大项目可在本地导入后远程使用。详细构建与运行说明位于 `sites/draft-remote/README.md`。

项目列表和 PDF 预览栏中的“打开 PDF 位置”会在本机文件管理器中显示对应 PDF（macOS Finder 会选中文件）。导入的 PDF 位于 `workspaces/<项目 ID>/original.pdf`，LaTeX 最近一次成功编译的 PDF 位于 `workspaces/<项目 ID>/.latex/compiled.pdf`；使用 `--root` 时以指定目录为准。未导入或未编译时会提示先生成 PDF。

LaTeX 局部润色默认只返回受影响段落，以 `latex-edit` 中的 `edits`（`old` 原文、`new` 修改稿）精确替换，未修改的源码保持原样。采用前校验版本、原文唯一匹配及编辑范围不重叠；无法定位则不写入。只有明确要求整章重写或完整稿时才返回完整 `latex` 代码块，旧的整章回复仍可采用。

在右侧编译 PDF 中拖选文字，点击“修改这一段落”，即可通过 SyncTeX 定位并扩展为完整源码段落，自动切到对应章节。输入框上方显示当前选区，可展开“查看选中 TeX”核对或“取消选择”。后续每条消息仅附带该选区的最新 TeX 作为当前正文；选择按章节保存，刷新或继续对话仍保留，采用修改后跟随更新后的段落。普通 PDF 导入项目不支持此功能。PDF 必须与当前源码一致；跨页可选，跨文件或跨章节需分别选择。公式等环境保留完整源码，最终范围以“查看选中 TeX”为准。源码发生无法安全跟随的外部改动时，会阻止发送并要求重新选择。

PDF 选区旁会显示“修改这一段落”浮标，点击后沿用蓝色选区持续标记当前修改段落；高亮独立于浏览器临时文字选择，输入、缩放和刷新不会清除。采用修改后保留旧 PDF 中的位置，重新编译后按新版源码恢复高亮。取消选择时移除标记；浮标可通过点击外部或 Esc 收起。

## macOS 轻量安装版

`dist/Caret.dmg` 中的 `Caret.app` 可直接拖入「应用程序」。App 自带应用源码和界面，
Python 环境与 LaTeX 工具放在本机应用支持目录，不内置到 App / DMG。

首次为当前 Mac 准备环境并复制已有数据：

```bash
.venv/bin/python macos/install_environment.py
.venv/bin/python macos/build.py
```

安装脚本保留原始数据，若目标目录已经存在则拒绝覆盖。目标目录为
`~/Library/Application Support/Draft/`：

- `runtime/`：独立 Python 与依赖，不再链接桌面项目。
- `tools/`：现有本机 LaTeX 工具及缓存。
- `data/`：论文工作区、参考库、角色规则与 `.local/` 配置。

此后 App 不依赖原项目目录，替换 App 不会覆盖论文。旧项目与新应用数据是两份独立副本，
不会自动同步；迁移后请使用新 App 继续写作。可从 Caret 菜单打开应用数据目录。
日常构建运行 `macos/build.py`，仅输出到 `dist/tmp/`，不增加正式版本号，不覆盖正式安装包或已安装 App。
所有功能确认完成、用户明确要求上线后，才运行 `macos/build.py --release --version X.Y.Z` 统一生成正式包，再更新已安装 App。无需重新安装环境或迁移数据。
DMG 供当前已准备好环境的 Mac 使用；其他 Mac 需要先单独准备运行环境。

App 优先使用本机端口 18768，冲突时自动使用空闲端口；只监听本机地址。
关闭窗口后仍在 Dock 运行，点击图标可重新打开，⌘Q 退出。
退出前请保存并等待生成或编译完成。启动日志位于 `data/.local/mac-app.log`。
构建需要 Apple Command Line Tools。应用采用本机临时签名，未做 Apple 公证。

输入消息时，Enter 仅换行或确认输入法候选，不发送消息；使用 ⌘Enter（或 Ctrl+Enter）或发送按钮提交。中文输入法组合期间不会触发发送快捷键。

LaTeX 项目中按 ⌘S 可重新编译 PDF；当前源文件有修改时先保存，保存失败则不编译。生成、编译或文件读取期间不会重复触发。

## 写作偏好与 Git 历史

聊天区顶部的「写作偏好」打开独立页面，默认展示当前章节生效的个人全局、个人章节类型、论文和章节偏好。
可新增、编辑、调整范围、停用规则，审核待确认建议，查看论文库作者记忆及有原文依据的风格补充。
每条模型回复中的「本轮偏好」显示实际使用的版本及规则快照。

有偏好信号的成功聊天轮次会用当前写作模型额外分析一次，可能增加 API 用量。
明确的长期新增要求可自动记录；推断、对已有规则的修订及作者风格总结必须先审核。
候选建议可编辑、接受或拒绝；接受前不进入写作上下文。作者补充要求论文 ID、段落及原文引文通过本地核验。
新偏好只约束表达，不是论文事实，也不会自动改稿。个人偏好以当前任务和更具体范围的规则为准。
可随时关闭「从聊天学习」。运行中关闭 App 可能中断后台分析，重启后不自动重跑。
分析失败不会丢失写作回复或修改已有偏好；不自动扫描全部历史聊天。

独立本地 Git 库位于配置目录下的 `preferences/`，安装版为
`~/Library/Application Support/Draft/data/.local/preferences/`。
每次修改记录操作者、来源和原因；支持差异查看、满意版本标记、单条恢复及整套恢复。
恢复产生新提交，保留历史，不回退论文正文。没有远端仓库，不自动上传偏好。
旧版 `memory/preferences.md` 继续作为论文记忆读取并在页面展示；旧作者记忆作为参考保留。
新偏好、候选和作者风格补充由新 Git 库管理，未静默重写旧作者记忆文件。

## 开发与集中发布

后续功能和修复先累积在同一轮 tmp 开发版中。完成单个需求只修改源码并验证，不自动发布。

- `python macos/build.py --plan`：只查看构建计划。
- `python macos/build.py`：生成 `dist/tmp/Caret.app` 与 `dist/tmp/Caret.dmg`，保留当前正式版本号。
- `python macos/check_installation.py`：使用临时数据验证 tmp 安装包。
- 用户明确要求统一上线后，才执行 `python macos/build.py --release --version X.Y.Z`；正式包验证使用 `macos/check_installation.py --release`。
- 打包脚本本身不会安装、关闭或重启 App。正式 App 更新也必须属于用户明确批准的这次上线。

偏好 Git 历史和论文版本仍逐次记录，方便恢复；它们不等同于 App 发布版本。

### 发布产物清理

正式版验证成功后，`macos/check_installation.py --release` 自动运行 `macos/cleanup_releases.py --apply`。仅将与已安装正式版内容一致的 dist / tmp App 压缩归档；尚未发布的 tmp 和正在运行的 App 保留。旧版备份验证压缩内容后再移除 App 副本，保留最近三份回退归档。正式安装包 DMG 保留，Applications、论文、设置和偏好历史不参与清理。

可运行 `python3 macos/cleanup_releases.py` 预览，添加 `--apply` 执行。定期清理由 Codex 中本聊天的每日任务执行。

应用已更名为 Caret，图标使用用户提供的 caret icon kit。内部 bundle ID 和 Application Support/Draft 数据目录保持兼容，以继续使用已有论文、运行环境与设置。发布改名版本时应替换旧 /Applications/Draft.app，避免同时安装两个名称的副本。
