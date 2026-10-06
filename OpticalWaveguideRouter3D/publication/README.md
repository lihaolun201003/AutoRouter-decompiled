# publication —— 科研图表与实验报告发布目录

本目录是**只读发布层**：从已有实验产物生成论文级图表、表格、实验清单与
审计台账。不启动实验、不修改任何原始数据。

## 一键生成

```powershell
# 在 OpticalWaveguideRouter3D 根目录执行
.venv\Scripts\python.exe scripts\publication\make_publication.py
```

脚本流程：数据源哈希（前）→ 生成全部图/表/清单 → 数据源哈希（后）对比
→ 输出来源台账与质量审查报告。重复执行可稳定重建全部产物。

## 产物结构

```
publication/
  figures/    35 张图 × (PDF / SVG / PNG 400 dpi)
  tables/     15 张 booktabs 三线表 .tex + 对应 _data.csv（原始精度）
  manifest/
    experiment_inventory.csv   全部 41 项实验（数据文件、指标、覆盖图、状态）
    figure_coverage.csv        每张图的源文件与覆盖实验
    table_coverage.csv         每张表的源文件与覆盖实验
    figure_sources.csv         每张图的导出记录（生成时登记）
    data_hashes_before.json    生成前 346 个数据文件 SHA-256
    data_hashes_after.json     生成后核验（必须与 before 完全一致）
    build_summary.json         本次生成摘要
    quality_review.md          图表质量审查报告
```

报告正文：`../docs/reports/experimental_results_publication.md`。

## 代码结构（scripts/publication/）

| 文件 | 职责 |
| --- | --- |
| `pubstyle.py` | 统一风格：字体（Times New Roman + SimSun fallback）、色盲友好配色、方案颜色/名称/marker 注册表、尺寸、保存与字形缺失检测 |
| `pubdata.py` | 数据加载层：全部实验产物路径与读取函数（图脚本不得硬编码数值） |
| `figs_thesis.py` | 论文复现组图（f31–f39、f310） |
| `figs_step12.py` | Step 12 主结果与消融（f51–f54） |
| `figs_step13.py` | Step 13 主结果、补修、受约束、敏感性（f61–f67） |
| `figs_step14.py` | Step 14 冻结对照、保护、接受过程、诊断（f71–f77） |
| `figs_3d.py` | 三维实验与几何重绘（f80–f86） |
| `tables.py` | booktabs 表生成（含原始精度 CSV） |
| `inventory.py` | 实验清单、图/表覆盖与闭合性检查 |
| `make_publication.py` | 一键入口、哈希核验、台账与质量审查报告 |

## 约定

* 图内不放长标题；条件、口径与样本量写在图注（`save_figure(note=...)`）与报告正文；
* 方法颜色跨图一致（`pubstyle.METHODS`）；同一方法同色、同 marker；
* 中文标签中不使用 mathtext（避免中文字形缺失），变量用正体字母；
* 全部图输出 PDF/SVG（矢量）与 PNG（400 dpi）；
* 含未布通/未通过验收的结果照常展示，但明确标注、不参与排名。
