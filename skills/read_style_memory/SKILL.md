---
name: read_style_memory
description: 按需读取作者样本的章节风格记忆
---
用 read_style_memory(author,section) 读取单份小型章节记忆。author 为 hongxin/xuefeng；section 必须与当前章节类型一致，取工具声明中支持的章节类型；不支持或未识别的章节不得回退到其他章节。
遵循适用条件和原文来源，不能把样本归纳当作当前论文事实。只读当前写作任务所需文件，需要具体原句用 find_style_examples；不要每轮加载整个记忆库。
用户要求比较写法、推荐最接近的论文、重新设计 hook/贡献表达时，可以调用 recommend_writing_strategy(goal,mode,section)，将2–3个候选方案提供用户选择。工具产生的建议不是用户确认过的计划。

所有章节统一隔离：参考例句、自动提供的风格范例、章节风格记忆与策略推荐只能使用当前章节类型的材料。Introduction、Related Work、Preliminary、Motivation、Method、Experiments、Results、Ablation、Discussion、Limitations、Conclusion、Appendix 等与 Abstract 一样隔离。不得因 role、关键词相似或同在第一页而跨章节引用。章节未知时先确认类型，不默认归入 Introduction；当前类型没有可用材料时明确说明，不借其他章节补足。此限制针对写作风格参考，不妨碍按需查证用户论文其他章节的事实。
