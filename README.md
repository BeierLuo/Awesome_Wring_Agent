# Draft · 本地论文写作工作区

Draft 是运行在本机浏览器中的论文写作工具，支持 PDF 和 LaTeX 项目。Gemini 负责写作与润色，GPT 按需查证资料、处理 PDF 章节和分析参考论文风格。修改内容经用户确认后保存，并保留历史版本。

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

打开 <http://127.0.0.1:8768/>。纯英文界面位于 <http://127.0.0.1:8768/en/>，也可点击顶栏的 English / Chinese 切换。两个版本共享项目和 API 配置，论文、对话及规则文件内容保持原文。macOS 安装好依赖后，也可双击 `启动写作工作区.command`。

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
