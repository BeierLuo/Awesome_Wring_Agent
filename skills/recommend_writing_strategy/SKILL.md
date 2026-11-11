---
name: recommend_writing_strategy
description: 结合当前 hook 和贡献推荐章节写法与参考论文
---
严格返回 JSON diagnosis/missing_information/options。提供2–3个真正不同的方案，不先假定用户必须选一篇模仿。
比较当前稿的研究缺口来源、贡献形态、论证证据和段落任务，与候选论文的 argument_overview、范例及作者样本记忆匹配；主题词相似仅作辅助。
每个方案写 title、author、hook、contribution_framing、paragraph_plan、why_fit、risks、paper_ids、source_ids。来源必须来自实际提供范例，paper_ids 与 source_ids 需一致。当前稿没有支持的 hook 或优势，标成待验证的备选，不能包装为既定贡献。
自动模式可比较 Hongxin 样本、Xuefeng 样本或组合路线；单作者模式也要给出该样本内不同写法。author 必须为 hongxin/xuefeng/mixed。
不要照搬参考事实，不把作者样本规律当成固有个人属性。明确推荐哪些写法、哪些不适用；资料不足写 missing_information。
总体最多2500字。不会直接改正文；用户选择后才成为章节计划。需要人工核实的候选不能改写成已验证规则。
