---
name: analyze_style
description: 从原文建立可追溯的分层写作分析
---
输入为论文的连续原文块，每块有 id 和页码。块可能不等于语义段落。
overview 总结该批次的章节组织和论证推进，不泛化成未见全文的结论。
挑选最多12个有借鉴价值的完整论证段落块（跳过参考文献列表、页眉、纯公式和碎片），每个 paragraph_id 必须来自输入。
role 表示该段主要写作作用；section 为可确认的章节，不确定写未知。
purpose 说明段落对全文的作用；logic 说明与上下文的衔接及段内推进；sentence_moves 按原文顺序逐句概括句子的作用；wording 分析用词、句式、措辞强度，保留少量短语例子。
只提供分析，原文由程序按 id 附回，不重写或编造原文。

严格输出 JSON 对象，只有 overview 和 examples 两个顶层字段。overview 最多600字，只写整体组织，不得把逐段分析塞入 overview。每段分析必须作为 examples 数组中的独立对象；通常选择3–6个范例，最多8个。只有输入完全是参考文献/纯公式时 examples 才可为空。
每个例子的 role 必须使用以下英文枚举之一：background, gap, motivation, contribution, method, experiment, result, limitation, conclusion；不得填中文解释，解释放 purpose。paragraph_id 必须逐字复制输入 id。sentence_moves 使用字符串数组。各分析字段保持简洁，不重复原文。

在已有 purpose/logic/sentence_moves 字段内明确细粒度叙事任务（例如方法引入、理论陈述、理论解释、总结过渡），不要只重复 method 等粗角色。purpose 说明对章节目标的贡献；logic 区分前后衔接与段内推进，只依据可见上下文，未知就说明未知。位置不等于作用，理论结果后的直觉解释应区别于参数扩展和公式引入。
