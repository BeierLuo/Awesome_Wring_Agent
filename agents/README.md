# Draft Agent 文件

角色规则：writer/AGENT.md（Gemini 写作）、researcher/AGENT.md（GPT 查证）、maintainer/AGENT.md（GPT 负责 PDF Project 的目录识别、原文提取和整理写回）。
技能说明：项目根目录 skills/<技能名>/SKILL.md。它们由 Draft 自己加载，不依赖 Codex 的技能加载器。
论文记忆：workspaces/<Project ID>/memory/ 下的 paper.md、preferences.md、decisions.md，每个 Project 独立。

在网页“Agent · 规则与记忆”中编辑，或直接编辑这些 UTF-8 文件。下一轮重新读取，运行中的请求保持开始时的快照。
角色和技能影响所有 Project；记忆只影响对应 Project。不要在这些文件中填写 API Key 或其他凭据。
记忆为用户手动维护，不会自动从全部聊天中生成，也不会由模型静默改写。查证时仍以最新稿和真实来源为准。
只加载当前角色需要的技能，记忆总量最多6000字符（每文件2000字符）。角色每文件12000字符，技能每文件6000字符。
编辑说明不会新增可执行工具、改变预算、取消证据校验或绕过用户确认；工具签名和执行仍在 Python 中。
网页保存前保留旧版本：全局规则在 .local/agent-history/，论文记忆在对应 Project 的 .agent/memory-history/。
Markdown 中的任意链接、路径或 shell 命令都不会被加载器自动读取或执行。

LaTeX 流程：ZIP → 本地源码分节（latex_project.py）→ Gemini 返回完整 latex 代码块 → 本地版本检查及用户确认（ui/workspace-core.js）→ 写回源文件。GPT researcher 仅按需查证；不调用 maintainer。

论文库：stylist/AGENT.md 负责 GPT 分批风格分析，analyze_style 生成原文锚定的范例；writer 通过 find_style_examples 查询缓存。Project 参考选择在 style-reference.json，论文与缓存在全局 style-library/。
