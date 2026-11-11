---
name: synthesize_style_memory
description: 从多篇论文归纳小型章节写作规则
---
将作者样本中同一章节/写作任务的范例归纳为3–5条条件性规则（样本稀少可1–2条）。严格输出 JSON summary/rules/uncertainties，不写大篇幅文献总结。
summary 最多300字，每条 rule/when/avoid 分别最多100字。每条 source_ids 引用1–2个真实输入 source_id，优先跨论文相互支持的证据；单篇支持必须说明“单篇观察”。至少在 uncertainties 说明共同作者、研究题型、年份可能混淆个人风格。
规则覆盖 hook/贡献定位、段落推进、句子作用、用词及语气，可为不同论证任务提供不同办法；不要求每篇模仿同一个套路。
不要记录屏幕每轮可见的全文或实验事实，只保存推导得到的可迁移策略、适用条件与不适用情形。
Preliminary 的候选可能来自别的章节中承担“定义/形式化”任务的段落，必须据真实源章节描述，不要说它一定出自 Preliminary。
