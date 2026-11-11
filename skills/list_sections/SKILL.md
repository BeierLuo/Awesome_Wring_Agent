---
name: list_sections
description: 查看章节目录
---

# 查看章节目录

用 list_sections 获取章节 ID、文件名、最新版本和页码范围，不读取正文。目录超过一页时按 next_offset 继续。initialized=false 表示没有已提取当前稿，应按需读 PDF，不能把空稿当成事实。
