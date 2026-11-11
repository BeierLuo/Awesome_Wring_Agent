---
name: find_style_examples
description: 按指定参考论文和段落作用读取本地写作范例
---
用户已指定参考论文时优先使用提供的风格上下文，需要更多范例时调用 find_style_examples。
查询只在当前 Project 选定论文内进行；未指定时可搜索已分析的论文库。
role 可取 background/gap/motivation/contribution/method/experiment/result/limitation/conclusion；query 描述正在写的任务或主题。
返回包括原文、物理页码、段落作用、句子作用、措辞分析。注明实际参考论文和页码，说明借鉴的组织方式。
不逐字照搬，不迁移参考论文的事实，不将风格例子当作实验依据。结果为空或分析未完成时明确说明，不假装已参照。
