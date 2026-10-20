# R15 半径审计（radius-related hardcodes / limits）

- 审计对象：`OpticalWaveguideRouter2D/four_side_1024` 与半径相关的硬编码、导入期绑定、
  阈值与文档表述；快照时间 **2026-10-20 15:05（本地）**。
- 工艺前提：2026-10-20 起 **所有平面弯曲与三维升降弯曲的最小曲率半径 R = 15 mm**，
  优先于历史 R = 40 mm 约定与 PDF 示例半径（R = 6000 µm / R = 6137.33 µm，仅形状参考，
  见 `PDF_GEOMETRY.md`）。
- 本文结论供最终报告使用；文件行号以快照时内容为准（`fslw/config.py`、
  `r15/profile_r15.py` 在 14:56–14:57 刚更新，含新增的进程半径传递机制）。

## 0. 分类编码与总结

| 类别 | 含义 | 本审计命中 |
|---|---|---|
| **(a)** | **导入期半径绑定**：模块 import 时把 `C.RADIUS_MM`（或派生值）拷进模块常量 / 函数默认参数；必须在 `profile_r15.apply()` 之后 import | `v2opt/candext.py`、`v2opt/ortho90.py`、`fsd25d/config25d.py`、`fsd25d/path3d.py`、`v2opt/ortho90_validate.py`、`fsd25d/validate25d.py`、`fslw/feasibility.py`、`fslw/config.py`（默认值 + 环境变量） |
| **(b)** | **逻辑/阈值中的 40 mm（或历史 5 mm）字面量**：默认参数、灵敏度表、元数据判断等，需显式覆盖或补丁 | `fslw/config.py`、`fslw/validate_fslw.py`、`d56/validate_d56.py`、`four_side_1024/geometry.py`（防御性 `min_radius=5.`） |
| **(c)** | **仅 docstring / 标签 / 报告措辞**：不影响计算 | 见各文件 `(c)` 行；无需改代码 |
| **(d)** | **半径无关的几何代码**（任意半径参数化，调用时读取） | `fslw/geom.py`、`fslw/candidates.py`、`d56/index.py`、`r15/u_geometry.py`（本轮新增） |

**一句话结论**：R15 可以完全不改任何既有源文件实现——前提是 **profile 必须在所有
(a) 类模块首次 import 之前 apply**；已 import 的模块中 `profile_r15.patch_radius()`
只能回填 **模块级常量**（5 个），**不会**回填函数默认参数（`ortho90.check_pure90`、
`config25d.transition_footprint`、`path3d.*` 的 `radius=CFG.RADIUS_MM` 默认值、
`validate25d.RADIUS_MM/MIN_CURVATURE_MM`），这是本轮最主要的残余风险（见 §4）。

## 1. R15 profile 策略（现状）

- `r15/profile_r15.py`：`RADIUS_MM = 15.0`；`apply()`（幂等）→ `patch_radius(15)`：
  1. 设环境变量 `FSLW_PROCESS_RADIUS_MM=15`：让 **multiprocessing 子进程重新 import
     `fslw/config.py` 时绑定 15**（否则子进程回落到 40，静默用 R40 出候选）；
  2. 改 `fslw.config.RADIUS_MM = 15`、`FIXED_RADIUS_40MM = False`；
  3. 替换 `fslw.config.process_record()`：写 `min_bend_radius_mm/radius_mm = 15`、
     `fixed_radius_40mm = False`、`process_profile = R15_min_radius_15mm`；
  4. 回填 **已 import** 模块的模块级常量（`_REBIND_CONSTANTS`）：
     `v2opt.candext.R`、`v2opt.ortho90.R`、`fslw.feasibility.R`、
     `v2opt.ortho90_validate.RADIUS`、`fsd25d.config25d.RADIUS_MM`。
- `r15/worker_boot.py`：子进程任务载荷带 `process_radius_mm`，worker 入口先
  `ensure_profile(radius)` 再生成候选。
- 正确用法（也是文档/README 的约定）：**先 `profile_r15.apply()`，再 import**
  `v2opt.candext`、`v2opt.ortho90`、`fsd25d.config25d`、`fsd25d.path3d`、
  `fsd25d.validate25d`、`v2opt.ortho90_validate` 等 (a) 类模块。
- 验证工具：`python -m four_side_1024.r15.profile_r15` 打印各绑定器的实际半径。

## 2. 逐文件审计

### `fslw/config.py`
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L19–L21 | `_ENV_RADIUS_MM = os.environ.get('FSLW_PROCESS_RADIUS_MM')`；`RADIUS_MM = float(env) if env else 40.0`；`FIXED_RADIUS_40MM = abs(RADIUS_MM-40.0)<=1e-12` | **a + b** | profile.apply() 打补丁；子进程靠环境变量；直接 import 该模块即 40（历史默认） |
| L1 | docstring “R>=40 mm experiment” | c | 仅文案 |
| L62 | `LEGACY_VIRTUAL_MODEL(... radius_mm=5.0 ...)` | b | 历史基线记录，R15 不使用 |
| L67–L72 | `SENSITIVITY_CONFIGS`：R5 ×2、R40 ×2 | b | 仅 Phase-11 sensitivity 用；R15 轮不跑 |
| L81–L116 | `process_record()` 读模块级 `RADIUS_MM/FIXED_RADIUS_40MM` 写元数据 | d（调用时读） | profile 替换为包裹函数，写入 15/False |

### `fslw/geom.py` — 半径无关（d），无导入期绑定
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L73、L90、L121、L136、L149、L163、L169、L181、L215、L250、L257 | 每个函数 `radius = C.RADIUS_MM if radius is None else float(radius)`（调用时读取，可显式覆盖） | d | 无需改动；`canonical_validate(..., radius=15)` 直接工作 |
| L1、L9–L12、L120 | docstring “R>=40 / R=40 / R=5” | c | 文案 |
| — | 几何本身（line/arc/quarte 弧/short-S/自交/边界）与半径值无关 | d | — |

### `fslw/candidates.py` — 半径无关（d）
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L36–L37 `_radius()`；L81、L102、L104、L115、L129、L147 直接读 `C.RADIUS_MM` | 候选族在调用时取半径 | d（无 import 绑定） | profile 后自动 R15 |
| L1 | docstring “R>=40 mm” | c | 文案 |

### `v2opt/candext.py` — 导入期绑定（a）
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L34 | `R = C.RADIUS_MM`（模块常量，import 时绑定） | **a** | `apply()` 之后再 import；或已 import 时由 patch 回填 `candext.R` |
| L210–L213 等 | `structural_x/y = [R, ...]`、`move_path`/`moves_polyline` 用 `R` | d（用模块常量） | 依赖上面的绑定/回填 |
| L4 | docstring “fixed R=40 mm quarter arcs” | c | 文案 |

### `v2opt/ortho90.py` — 导入期绑定（a），含**函数默认参数**陷阱
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L38 | `R = C.RADIUS_MM` | **a** | apply 后 import；patch 回填 `ortho90.R` |
| L50 | `def check_pure90(primitives, radius=R, tol=TOL)` —— **默认参数在 def 时求值** | **a (b 类陷阱)** | ⚠ patch 只回填 `ortho90.R`，**不会**改 `check_pure90` 的默认参数；若本模块在 apply 前已 import，`check_pure90(prims)` 仍按 40 mm 判定并把所有 R15 候选判非法 → 必须有正确 import 顺序 |
| L212–L218 | `solve_pattern` 内用 `geom.canonical_validate(...)`（radius=None→调用时读 config） | d | 正常 |
| L1、L21 | docstring “R=40” | c | 文案 |

### `fsd25d/config25d.py` — 导入期绑定（a），含函数默认参数
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L53 | `RADIUS_MM = C.RADIUS_MM` | **a** | apply 后 import；patch 回填 `config25d.RADIUS_MM` |
| L88 | `def transition_footprint(dz_mm, radius=RADIUS_MM)` —— 默认参数 import 时冻结 | **a (b 陷阱)** | ⚠ 回填 `RADIUS_MM` **不改变**该默认值；apply 前 import 时 `transition_footprint(0.125)` 仍返回 R40 的 4.4704 mm（而不是 R15 的 2.7358 mm） |
| L51–L58 | BOARD/HALF/CLEARANCE/WIDTH 等 | d | 与半径无关 |
| L12 | docstring “R=40” | c | 文案 |

### `fsd25d/path3d.py` — 导入期绑定（a），默认参数全面冻结
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L23 | `from . import config25d as CFG` | a（依赖链） | — |
| L164 `transition_theta(dz_mm, radius=CFG.RADIUS_MM)`；L174 `make_transition(..., radius=CFG.RADIUS_MM)`；L223 `place_transitions(..., radius=CFG.RADIUS_MM)`；L283 `build_route3d(..., radius=CFG.RADIUS_MM)` | 默认参数在 import 时求值 | **a (b 陷阱)** | apply 后 import 则全部 15；⚠ 若 apply 前 import，**patch 不会改这些默认参数**，而 `router25d.py:190` 调 `build_route3d(...)` 时不传 radius → R40 升降 S 静默进入 R15 轮 |
| L8–L11 | docstring “R=40” | c | 文案 |

### `d56/index.py` — 半径无关（d）
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| 全文 | 无 radius 常量；`D56Index(width, gap, sagitta, min_cross_angle_deg, ...)` 只按真实 primitive 几何（含 `prim.radius` 参与数学）判定冲突/交叉/间距 | **d** | R15 布局可直接用；不读 config 半径 |
| L9 | docstring “Radius (5 mm), waveguide width…” | c | 文案 |

### `d56/validate_d56.py` — 硬编码 R = 5 mm（b），**不可直接用于 R15**
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L46 | `RADIUS = 5.0` | **b**（模块常量） | 冻结的 R5 D56 验收器 |
| L507–L534 `_pair_reason`：L521–L523、L531 | short-S 判据 `2.0*RADIUS*(1-cosθ)`、`2R sinθ`、`θ=acos(1-d/(2R))` 用模块常量 | **b** | R15 short-S 会被误判；如运行期覆盖 `validate_d56.RADIUS = 15.0`，`_pair_reason` 会读新值（调用时读全局） |
| L572–L573 | `def check_route_primitives(..., radius=RADIUS, ...)` 默认参数 import 时冻结为 5.0 | **b（a 类陷阱）** | 覆盖 `RADIUS` 后**仍需显式传 `radius=15`**；而 L2115/L2379 的报告路径 `check_route_primitives(primitives, source, target)` 不传 radius → 永远按 5.0 |
| L618–L624 | 弧半径检查用参数 `radius`（≥ 1e-9 相等） | d | — |
| L2182 | 报告元数据 `"radius_mm": RADIUS`（调用时读全局） | b | 覆盖后元数据才正确 |
| 结论 | **R15 轮不要把 `d56/validate_d56.py` 当 authoritative validator**；二维 D56 产物由 `fslw/validate_fslw.py`（radius 15）验收，纯正交由 `v2opt/ortho90_validate.py`，`r15/validate_r15.py` 封装 | — | — |

### `fslw/validate_fslw.py` — 默认 40（b），但**设计上支持 R15 覆盖**
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L65 | `RADIUS = 40.0` 模块常量（默认） | **b** | 通过参数解析覆盖 |
| L93 | `RADIUS_TOL = 1e-9` | d | 不变 |
| L2262–L2289 `process_params()` | 优先级：显式 `radius=` > 最近 `config.json` 的 `radius_mm/min_bend_radius_mm` > 模块默认 40 | **b（可覆盖）** | R15 产物带 process/config 记录（radius 15）或显式 `radius=15` 即可 |
| L2708–L2746 `resolve_parameters()` | 优先级：显式 CLI > `routes.json` 内嵌 `process` 记录 > `config.json` > sensitivity 路径名 > 默认 40 | b（可覆盖） | 同上；建议 R15 产物必须写 process 记录 |
| L2305–L2310 `validate_dataset(..., radius=RADIUS, ...)` 默认参数冻结 | b（a 陷阱） | `build_report` 解析参数后显式传 radius（L2783）→ 不受影响 |
| L2478、L2515 | `fixed_radius_40mm = abs(radius-40.0)<=RADIUS_TOL` | b（标签逻辑） | R15 时输出 False，语义正确 |
| L2622、L2986、L3013 | 报告/CLI 文案 “R=40 mm”、`--radius default 40.0` | c | 用 `--radius 15` 或 process 记录 |
| L2676–L2686 | `SENSITIVITY_PARAM_MAP` 含 40.0/0.125 等 | b | 仅按路径名推断灵敏度用例；R15 输出目录不含这些名字时不触发 |

### `v2opt/ortho90_validate.py` — 导入期绑定（a）
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L28 | `RADIUS = float(_fslw_config.RADIUS_MM)` | **a** | apply 后 import；patch 回填 `ortho90_validate.RADIUS`（在 `_REBIND_CONSTANTS` 中） |
| L64 等 | `geometry_rule_audit` 调用时读模块全局 `RADIUS` | d | 回填后正确 |
| L8–L10 | docstring 已说明“R40 历史轮 / apply 后 15 mm” | c（已适配） | — |

### `fsd25d/validate25d.py` — 导入期绑定（a），**未被 patch 回填**
| 位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| L105 | `RADIUS_MM = float(FSLW.RADIUS_MM)` | **a** | apply 后 import；⚠ 不在 `_REBIND_CONSTANTS` 中，apply 前 import 会一直是 40 |
| L107 | `MIN_CURVATURE_MM = RADIUS_MM * (1.0 - 1e-3)`（R40 → 39.96；R15 → 14.985） | **a（派生阈值）** | 同上；若冻结在 40，会把 R15 的 3D 路径（真实曲率 15）全部判为曲率违规 |
| L832、L969 | flat arc / transition 半径检查 `abs(radius - RADIUS_MM) <= RADIUS_TOL` | a→b | 依赖 L105 |
| L861–L862 | short-S 对判据用 `first.radius`（逐 primitive） | d | R15 安全 |
| L1299–L1302 | 采样最小曲率 vs `MIN_CURVATURE_MM` | a→b | 依赖 L107 |
| L27–L34、L831、L846 | docstring “R=40” | c | 文案 |

## 3. 清单外补充发现（与 R15 直接相关）

| 文件/位置 | 内容 | 类别 | R15 处理 |
|---|---|---|---|
| `fslw/feasibility.py:30` | `R = C.RADIUS_MM` | **a** | 在 `_REBIND_CONSTANTS` 中（`feasibility.R`） |
| `four_side_1024/geometry.py:348` | `validate(..., min_radius=5.)` 默认参数 | b（防御性默认） | 所有调用方显式传 min_radius；R15 调用需 `min_radius=15` |
| `r15/u_geometry.py`（本轮新增） | 半径在 **调用时**解析（`resolve_radius()`：显式 radius > profile（apply 后 `C.RADIUS_MM`=15）），无 import 期常量；所有弧强制 exact R，禁止缩半径；最小同侧间距 = 2R | **d（合规）** | 无需 patch；测试同时锁定 R15（30 mm）与 R40（80 mm）行为，证明无 40 硬编码 |
| `v2opt/finalize.py` | `finalize.fslw_config.RADIUS_MM` 在 profile 后为 15（`check_imported_modules` 已核对） | d（调用时读） | 正常 |

## 4. 残余 R40 假设与风险（按严重度）

1. **R1（高）——函数默认参数不会被 `patch_radius` 回填。** 若下列模块在
   `apply()` 之前已被 import，即使之后 apply，仍按 40 工作：
   - `v2opt/ortho90.py::check_pure90` 的 `radius=R` 默认值（会把 R15 候选全部判非法）；
   - `fsd25d/config25d.py::transition_footprint` 的 `radius=RADIUS_MM` 默认值
     （实测仍返回 R40 footprint 4.4704 mm，而 `config25d.RADIUS_MM` 已是 15）；
   - `fsd25d/path3d.py::transition_theta/make_transition/place_transitions/build_route3d`
     的默认值；`router25d.py:190` 调 `build_route3d` 不传 radius → 升降 S 静默 R40；
   - `fsd25d/validate25d.py::RADIUS_MM/MIN_CURVATURE_MM`（未在回填表内）→ 3D 验收
     把 R15 全判曲率违规；
   - `fsd25d/validate25d.py` 的 `RADIUS_MM` 与 `MIN_CURVATURE_MM` 都是派生阈值。
   **缓解**：R15 入口必须“先 apply 再 import”；子进程必须走 `worker_boot.ensure_profile`；
   建议在最终报告里明确这条执行顺序，并用 `profile_r15.check_imported_modules()` 的
   扩展版（同时打印上述默认参数）做启动自检。
2. **R2（高）——`d56/validate_d56.py` 冻结在 R = 5 mm。** `_pair_reason` 用模块常量、
   `check_route_primitives` 默认参数冻结、报告调用不传 radius：不能作为 R15 D56
   short-S 的验收器。R15 二维验收用 `fslw/validate_fslw.py`（process 记录/显式 radius）
   与 `v2opt/ortho90_validate.py`（纯 90°），三维验收用 apply 之后的 `fsd25d/validate25d.py`。
3. **R3（中）——`fslw/validate_fslw.py` 的默认回退是 40。** R15 产物必须携带
   `process.radius_mm = 15`（profile 的 `process_record()` 已保证）或显式传
   `radius=15`；否则无记录产物会回落到 40 并全部拒绝。`fixed_radius_40mm` 元数据在
   R15 下输出 False（语义正确，不是问题）。
4. **R4（中）——multiprocessing 子进程默认 40。** Windows spawn 重新 import
   `fslw/config.py`；未设 `FSLW_PROCESS_RADIUS_MM` 或未调 `worker_boot.ensure_profile`
   时会静默用 40 生成候选。profile 已从 `patch_radius` 设置环境变量，worker 侧仍应
   统一走 `ensure_from_payload`。
5. **R5（低）——`fslw/config.py` 的 40 默认值本身。** 这是历史默认（“不 apply 时保持
   R40 行为”），不是 R15 缺陷；但任何在 apply 前读取 `C.RADIUS_MM` 的代码都会拿到 40，
   因此 R15 入口必须在最早期 apply。
6. **R6（低）——`four_side_1024/geometry.py::validate` 的 `min_radius=5.` 默认值。**
   仅防御性默认，所有调用方显式传半径；R15 的校验调用不能省略该参数。
7. **R7（低）——文档/报告措辞**：若干 docstring、CLI help、报告描述仍写 “R=40 mm /
   R>=40 mm”（`fslw/config.py`、`fslw/geom.py`、`fslw/candidates.py`、`v2opt/candext.py`、
   `v2opt/ortho90.py`、`fsd25d/config25d.py`、`fsd25d/path3d.py`、`d56/index.py`、
   `fsd25d/validate25d.py`）。R15 报告引用这些模块时应注明“历史轮文档措辞，本轮实际
   R=15”，避免误读。
8. **R8（提示）——历史 R5/R40 字面量属于基线数据**（`LEGACY_VIRTUAL_MODEL`、
   `SENSITIVITY_CONFIGS`、sensitivity 路径名映射）：R15 轮不运行这些配置时无影响。

## 5. 验证证据（快照时的实测）

1. `python -m four_side_1024.r15.profile_r15`（apply 后）：
   `fslw.config.RADIUS_MM = 15`、`candext.R = 15`、`ortho90.R = 15`、
   `feasibility.R = 15`、`ortho90_validate.RADIUS = 15`、
   `config25d.RADIUS_MM = 15`、`fsd25d.transition_footprint(0.125) = 2.7358 mm`。
2. **错误顺序实验**（先 import 全部 (a) 类模块 → 再 apply）：
   - 回填成功的 5 个常量 = 15；
   - 仍为 40 的默认参数/派生量：`ortho90.check_pure90` 默认 40.0；
     `config25d.transition_footprint(0.125) = 4.4704 mm`（默认参数 40）；
     `path3d.transition_theta(0.125) = 0.055909 rad`（R40 角）；
     `validate25d.RADIUS_MM = 40`、`MIN_CURVATURE_MM = 39.96`；
   - `profile_r15.check_imported_modules()` 此时也报
     `fsd25d.transition_footprint_0.125 = 4.4704`（即诊断本身能暴露该错误顺序）。
3. **正确顺序实验**（先 apply → 再 import）：上述默认参数全部为 15：
   `transition_footprint(0.125) = 2.735759 mm`、`transition_theta(0.125) = 0.091319 rad`、
   `validate25d.RADIUS_MM = 15`、`MIN_CURVATURE_MM = 14.985`。
4. **测试**：
   - R15 同侧 U 几何：`python -m pytest four_side_1024\r15\tests_r15 -q` → **42 passed**
     （含 R15 半径精确性、切线连续、可行性/不可行性、不允许缩半径、`canonical_validate`
     集成、四边板侧、真实端口表统计）；
   - 历史回归：`python -m pytest tests -q` → **62 passed**（未受本轮新增文件影响）。
5. 端口/可行性统计（R15 端口表，每侧每平面 256 端口，0.25 mm 网格）：
   同侧端口对 32640 对，R15（d ≥ 30 mm）可行 20098 对 = 61.6 %；
   R40（d ≥ 80 mm）仅 6706 对 = 20.5 %。

## 6. 给最终报告的建议措辞

- “R15 通过进程 profile 实现：既不打补丁也不降低任何验收标准；R40 历史结果保留、
  不混用。”
- “半径相关的唯一新增约束载体是 `r15/profile_r15.py`（apply/patch_radius）与
  `<r15/worker_boot.py>`（子进程重放）；既有 (a) 类模块的导入顺序是硬约束。”
- “历史 `d56/validate_d56.py` 固定 R5，不是 R15 的验收器；R15 验收链路 =
  `fslw/validate_fslw.build_report(radius=15/读 process 记录)` +
  `v2opt/ortho90_validate`（纯 90°，apply 后 import）+ `fsd25d/validate25d`
  （apply 后 import）+ `r15/validate_r15.py` 封装。”
- “残余 R40 假设集中在函数默认参数（R1）与历史验收器（R2），已在本审计列明；
  只要遵守 import 顺序与 process 记录要求，R15 产物可零源码修改地生成与验收。”
