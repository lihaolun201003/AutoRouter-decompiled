# Step 10 — Fixed 1024-Channel 3D Routing

## 1. Scope

**Step 10：PASS。** 固定1024输入、1024条解析二维初始几何、1024条Route3D、三层自动assignment、最终保存与全pair复核均完成。目标是固定项目可运行实验，不要求collision=0，不做图形界面或光学损耗优化。

## 2. Fixed 1024 Dataset

原始依据为保存的 `fiberBoard512.xlsx` 连接表及 `fiberBoard0data.xlsx` 端点快照，通过现有只读loader恢复原连接方向。审计确认512条波导、64个PMT、每PMT16个端点，总1024个端点；source和destination各512个，同一PMT内的方向混合，不能把32个PMT直接视为全部source。

新增固定种子 `data/fixed_1024_legacy_seed.json` 保存原512连接/端点及来源SHA256，复现本Step无需外部Excel路径。由种子生成128个PMT、2048个唯一端点、**exactly 1024 waveguides**，完整输入见 `outputs/step_10_fixed_1024_input.json`。每条记录含source/destination PMT、局部槽位、endpoint ID与XYZ。

## 3. Board / PMT Layout

旧数据上下边各32个PMT，y=0/150 mm；PMT起始x间距4.5 mm，PMT内16点间距0.175 mm。bottom从x=2开始，top从x=4开始，旧端点总x范围2～146.125 mm。旧allocator配置只用board_height，未定义board_width；保存图的xmin/xmax是显示留白范围，不能当作板边界。

固定1024板为 **300×200 mm**。上下各64个PMT，保持4.5 mm组间距、0.175 mm内部间距、上下起始x=2/4。原每个PMT的两份副本横向相邻插入；bottom端点x=2～288.125，top为4～290.125，y=0/200。所有初始解析primitive的XY包围盒在板内。

**PROJECT-SPECIFIC 1024 EXTENSION：仅为新fixture显式采用此板尺寸。** 容量诊断：同一1024横向布局在150 mm板高时800轨，800 assigned、160 no_available_track、64特殊Z；200 mm时1086轨，960 assigned、64特殊Z，轨道耗尽为0。未修改原allocator或512配置。证据见 board_capacity_check JSON。

## 4. Connection Rule

每个legacy PMT生成copy 0/1，PMT ID按原ID排序后映射为 `2*rank+copy+1`；局部槽位按原PMT内部x从小到大编号0～15，未将旧快照index列误当槽位。

每条legacy连接i生成两条：`route_id=2*i+c`，source使用copy c，destination使用 `c XOR (i mod 2)`。偶数原连接同copy，奇数原连接交换copy。原source/destination方向、PMT关联与端点槽位继承，端点副本映射为双射；source和destination各1024个，2048坐标、PMT/slot及endpoint ID均不重复。

这不是平铺两个互不相连的512结果，也没有按布线难易挑连接；规则在routing前固定。576条Z、224条bottom U、224条top U，继承原拓扑类型比例。

## 5. 2D Initial Geometry

复用原 `prepare_waveguides_2d`、ascending/exclusive `assign_tracks_2d`、普通正交平滑与special-Z构造。显式二维参数width=0.05、spacing=0.125、radius=5 mm，guard关闭。960条普通解析几何加64条special-Z，共1024；全部端点、连续性、切向方向及板边界检查通过，并解析lift到Layer 0。

**原 `router_2d.py` 未修改。** 新增 `src/fixed_1024_routing.py` 封装固定数据/配置及序列化；既有三维循环只增加此固定1024入口的停止上限和分阶段计时，原9-E/9-F预算入口保持不变。

## 6. 3D Layer Configuration

沿用9-F：Layer 0 z=0、Layer 1 z=1、Layer 2 z=2 mm；clearance=0.1 mm，required radius=5 mm，EXPERIMENTAL_SYNTHETIC。transition run继续由 `pi*sqrt(R*abs(dz)/2)` 计算并加既有微小余量；没有调参或引入第四层。

## 7. Routing Algorithm

直接复用9-F的当前collision集合、canonical最小target、当前degree较小victim优先、两目标层全部Line窗口候选统一排序。只在after collision count严格低于before时替换一条内存路线，允许少量新增collision，分别记录新旧集合差。

每个基本合法candidate检查其余1023条**当前**Route3D，包括此前已抬到Layer 1/2的路线。二维原投影只用于查找窗口CROSS锚点，不替代三维碰撞判断。端口与XY不变，不切Arc；每路线最多一次0→1→0或0→2→0。

初始完整建立523,776对，此后只更新移动route关联pair。失败或两者已抬层的目标在本轮实验跳过；已清除后重新出现的pair重新参与当前排序。防循环上限为1024次attempt，不是1024次成功。

## 8. Initial Collision Statistics

Initial Layer-0 state：1024条路线全部在Layer 0，collision pair **204,291**，另有4个未决/边界pair单列。这里统计的是clearance=0.1 mm下的COLLISION，不是二维physical CROSS事件或multi数。

## 9. Final 3D Routing Results

实际尝试 **1024** 次，成功elevation **175** 次；BOTH_ALREADY_ELEVATED **845** 次，NO_IMPROVING **4** 次。停止原因：**TARGET_LIMIT**。达到1024次固定防循环上限；仍有剩余碰撞，不能据此宣称所有目标均无改善可能。

最终exactly 1024条有效Route3D全部保存。输出 `step_10_fixed_1024_final_route_state.json` 含每条source/destination、state、target layer、带类型primitive、transition run/Δz/R_min、总长及extra length，可完整重建。

## 10. Layer Usage

| 状态 | 初始 | 最终 |
|---|---:|---:|
| LAYER_0 | 1024 | 849 |
| SINGLE_ELEVATION_0_1_0 | 0 | 72 |
| SINGLE_ELEVATION_0_2_0 | 0 | 103 |
| 合计 | 1024 | 1024 |

没有对任何已抬路线进行第二次elevation。

## 11. Collision Reduction

| 指标 | 数值 |
|---|---:|
| Initial Layer-0 collision pairs | 204,291 |
| Final 3D collision pairs | 138,113 |
| 净减少 | 66,178 |
| 减少比例 | 32.3940% |
| 累计old collisions removed | 68,782 |
| 累计new collisions created | 2,604 |

每次接受后全局collision count严格下降；累计差值为净减少量，不把重复出现/消除的pair当作唯一事件计数。最终另有4个未决/边界pair，未将其假报为CLEAR。

## 12. Length Overhead

原总长 **226070.858358470 mm**；最终总长 **226158.264955731 mm**。总extra length **87.406597261 mm**；每次成功平均 **0.499466270 mm**，摊到全部1024条平均 **0.085358005 mm**，单条最大 **0.678120186 mm**。transition共 **350** 个。仅统计几何长度，不推导真实光学loss。

## 13. Runtime

| 阶段 | 秒 |
|---|---:|
| 数据与1024初始几何 | 0.359 |
| 初始523,776 pair扫描 | 40.966 |
| 连续assignment | 1086.564 |
| 最终重载/全pair复核 | 42.745 |
| pipeline总时间（含主要保存开销，不含测试） | 1172.659 |

以上为本机单次实测，不是通用性能保证。没有GPU、KD-tree或新增空间库。

## 14. Final Validation

从最终JSON重载全部1024条路线，与内存结果逐条相等；原端点保持、C0/C1方向连接、cosine R_min均通过。最终重新扫描 **523,776 pair**，collision与未决集合均与局部更新结果完全一致，结果 **PASS**。只执行必要的这次最终全量一致性复核，没有反复形式化证明。

输入、initial_stats、initial_geometry、steps.csv、attempts、summary、final_route_state、collision_sets、validation均为独立step_10输出；既有512成果不覆盖。

## 15. Tests

**696/696 PASS：历史684项 + 新增12项。** 新增覆盖1024数量/ID、2048端点唯一性、确定性生成、板边界、连接完整性、1024二维几何和lifting、三层候选、全路线及抬层路线序列化重载、停止上限与只读种子。局部collision更新一致性通过上述真实1024全pair最终复核确认。未安装依赖。

复现（项目根目录）：`.venv\Scripts\python.exe -B scripts\run_fixed_1024_3d.py . <输出目录>`；追加 `--tests-only` 可只运行测试。种子保存在项目data内，连接规则与参数显式固定。文件完整性证据见 `step_10_file_integrity.json`。

## 16. Limitations

这是固定1024实验布局，仍有138,113个collision pair，并非无冲突可制造版图。停止上限不是全局无改进证明，也不能证明当前低 degree victim ordering 最优；每路线一次抬层、三层、有限Line窗口仍限制消除能力。Self-clearance与未决分类沿用已有规则；层高/clearance为实验值，不是制造标准。

没有改变原512二维行为，没有multi recovery、联合搜索、重复升层、XY rerouting、Arc切割、事务/版本系统、loss优化、GUI/GDS或3D绘图。

## 17. Verdict

**Step 10：PASS。** 固定1024输入、全部解析geometry与Route3D、真实三层assignment、collision下降、可重载完整保存、最终523,776对一致性、历史测试及只读baseline要求均满足。本报告与保存产物组成checkpoint。

## 18. Recommended Next Step

建议下一Step只读取最终1024状态，完成基础3D可视化与Layer/transition展示，使当前可运行结果可演示；不同时改算法或继续优化。本Step到此停止，未开始可视化、GUI、GDS或论文写作。
