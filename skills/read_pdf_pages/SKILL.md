---
name: read_pdf_pages
description: 读取 PDF 页面和图像
---

# 读取 PDF 页面和图像

用 read_pdf_pages 读取1–2个指定物理页。先用 mode=text，遇到表格、公式、图片或扫描内容再用 mode=image。每轮最多6个不同页和2页图像，禁止连续扫描全文。original_pdf 是上传原版；compiled_pdf 是 LaTeX 本地编译版本。源码改变但 PDF 过期时先用最新章节，提示用户重新编译。只转交已实际读取的来源与图像。
