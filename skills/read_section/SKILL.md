---
name: read_section
description: 读取最新章节
---

# 读取最新章节

用 read_section 按 section_id 读取最新章节。优先于原始 PDF；支持 offset 和 max_chars（最多12000字符），根据 next_offset 只补读相关片段。LaTeX 是源码，保留命令含义，不擅自解释缺失宏。
