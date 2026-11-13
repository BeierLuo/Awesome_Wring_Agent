---
name: apply_revision
description: 整理 PDF Project 的待确认修改稿
---

# 整理待确认修改稿

适用于 PDF Project；LaTeX Project 直接从写作 Agent 的 latex-edit 段落替换块（或用户要求的完整 latex 稿）准备待确认稿，不调用本技能。

Produce the COMPLETE proposed content of the selected section by applying the chosen Gemini response to the current draft. Remove chat explanations. Preserve unrelated text, original language, citations, equations and data. Do not invent improvements, results or references. If suggestions lack precise replacement text, apply only unambiguous edits and explain uncertainty in notes. Follow the source file format: raw LaTeX for .tex, Markdown for .md. Other sections and PDF must not change. This is a proposal; only the user confirms writing.
