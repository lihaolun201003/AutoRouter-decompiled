# 修正 L1–L5 模型 vs 历史 / R15-2D 对照表（自动生成）

- 生成时间（UTC）：2026-10-20T15:23:52Z

## 0. 重要警告：旧 5L 数字不可比

- historical old-5L numbers from the WRONG model (z1=L1 / z2=L5); they are NOT comparable with corrected L1-L5 results and must never be mixed into the corrected numbers。
- 旧数字只出现在本对照表的“历史”列，**不进入**任何 corrected 统计。
- 修正模型：L1 接口层同时包含 z1（0.0 mm）与 z2（0.5 mm）两个端口行；L2–L5 额外布线层高度未确认（`unconfirmed_simulation`）→ 正式验收 **NOT GRANTED**。

## 1. 主对照（primary stack = medium_050）

| 方案 | corrected L1-L5 布通 | 相对 flat-L1 基线新增 | 抬升 | transitions | corrected 3D 总长 mm | R15-2D 基线 | Δ vs R15-2D | 历史旧 5L（不可比） | Δ vs 旧（不可比） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 963 | +20 | 44 | 117 | 156,179.288 | 943 | +20 | 985 | -22（不可比） |
| B | 621 | +106 | 130 | 298 | 116,731.501 | 515 | +106 | 723 | -102（不可比） |

## 2. 层堆栈参数敏感性（exploratory）

| 堆栈 | L2..L5 高度 mm | provenance | 堆栈有效 | 最小平面间距 mm | A 布通/新增/抬升/transitions | B 布通/新增/抬升/transitions | A 几何验收 | B 几何验收 |
|---|---|---|---|---:|---|---|---|---|
| medium_050 | {'2': 1.0, '3': 1.5, '4': 2.0, '5': 2.5} | unconfirmed_simulation | 是 | 0.500000 | 963/+20/44/117 | 621/+106/130/298 | — | — |
| compact_025 | {'2': 0.75, '3': 1.0, '4': 1.25, '5': 1.5} | unconfirmed_simulation | 是 | 0.250000 | 962/+19/43/115 | 611/+96/120/268 | — | — |
| wide_100 | {'2': 1.5, '3': 2.5, '4': 3.5, '5': 4.5} | unconfirmed_simulation | 是 | 1.000000 | 963/+20/44/117 | 611/+96/120/265 | — | — |

## 3. flat-L1 基线（修正模型）

| 方案 | flat-L1 布通 | z1 行 | z2 行 | 失败 | 与 R15-2D 参考一致 |
|---|---:|---:|---:|---:|---|
| A | 943 | 498 | 445 | 81 | 是 |
| B | 515 | 184 | 331 | 509 | 是 |

## 4. 正式验收状态

- granted: **否**
- 原因：L2-L5 physical heights are unconfirmed_simulation simulation inputs; formal process acceptance is refused for every stack

## 5. 损耗口径

- bend, crossing and interlayer coefficients are all unknown_uncalibrated; a total-loss number would require invented coefficients, so none is reported
- 唯一已知参数为传播损耗实验约定 0.05 dB/cm（非实测）；弯曲/交叉/层间均为 `unknown_uncalibrated`。

