---
name: read_style_memory
description: 按需读取作者样本的章节风格记忆
---
用 read_style_memory(author,section) 读取单份小型章节记忆。author 为 hongxin/xuefeng；section 为 abstract/introduction/preliminary/motivation/method/experiments。
遵循适用条件和原文来源，不能把样本归纳当作当前论文事实。只读当前写作任务所需文件，需要具体原句用 find_style_examples；不要每轮加载整个记忆库。
用户要求比较写法、推荐最接近的论文、重新设计 hook/贡献表达时，可以调用 recommend_writing_strategy(goal,mode,section)，将2–3个候选方案提供用户选择。工具产生的建议不是用户确认过的计划。
