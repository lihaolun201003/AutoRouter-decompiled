本目录的验收记录命名约定（避免同名互相覆盖）

- page_by_page_lead.json / QA_REPORT_lead.md  —— Lead 亲自逐页查看并撰写，针对定稿 16 页
  PDF sha256 = c3cf0705ad72f3da3fa0dd3adc9bd74ad677d46eafb10bf4c8a96f84af2c2e76
- page_by_page.json / QA_REPORT.md           —— 同名标准文件；若子代理复审写入的是同一目标版本，可直接引用
- page_by_page_subagent.json / QA_REPORT_subagent.md —— 子代理复审产物（如存在）
- geom_check_final.json                      —— Lead 跑的机器几何检查（文本越界/块重叠；看不出图内重叠）
- page_01.png … page_16.png                  —— 定稿 16 页的 140 DPI 页图

校验：若 PDF 的 sha256 不是 c3cf0705…（16 页），上面的逐页结论即失效，必须按新文件重做。
重建步骤：build_v8_continuation_report.py → LibreOffice 转 PDF → _render_pages.py → geom_check_final.py
