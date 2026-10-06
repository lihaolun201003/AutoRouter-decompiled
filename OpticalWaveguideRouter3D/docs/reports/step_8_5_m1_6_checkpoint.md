# Step 8.5-M1.6 Checkpoint

日期：2026-09-11。状态：**PASS / COMPLETED / STOPPED**。

正式项目：C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D。
正式报告：docs/reports/step_8_5_m1_6_local_exact_recovery_design.md。

## Frozen baseline

ascending + exclusive A + guard OFF；width=.05、spacing=.125、pitch=.175、r=5、height=150 mm。
454 ordinary + 58 special-Z = 512 analytic routes；正式multi仍318。allocator与所有既有src未改，未commit任何recovery。

## Completed evidence

- M1.5的318 triplets、954 crosses及per_route参与计数一致；954坐标与保存physical事件及primitive membership再次核对。
- 800轨道；移除单ordinary后347候选，其中346为替代，1为原位。
- 唯一最低victim241，并列77；最低仅ordinary270、仅special29、混合19；无全不可移动目标。
- A/M0011：victim4，347/347几何合法，best M=318，无strict candidate。
- B/M0009：victim302，347/347，318→317，331个strict candidate，best track457。
- C/M0001：victim0，347/347，318→316，342个strict candidate，best track452。
- D/M0023：victim318，347/347，318→316，344个strict candidate，best track113。
- 三个下降都各自从原baseline出发，不能相加；special固定。
- 三个winner独立重建geometry及511 star pairs，重算固定第三边37128/4371/5995对；含victim所有130305可能三元组纳入遍历。removed/added集合与delta一致。非全512 all-pairs重跑；不含victim部分以冻结baseline和不变性证明保留。
- 四个原位negative control均M=318，目标仍在，delta为空。
- 143个既有文件哈希不变、两个源Excel不变；完整输入状态对象读前后相等。
- 初次505/505 tests PASS；新增非法index防御及一项测试后最终506/506 PASS，无新依赖。

## Adopted design, not production implementation

victim：special排除→multi_count升序→合法替代数降序→route_id最终确定顺序。保留并列；当前合法替代数全部346，无法打破并列。角色更局部尚无对照收益证据。

candidate：合法且目标消失且M_after<M_before；按(M_after,new_multi_created,abs(track displacement),track_index)字典序。拒绝equal-M与worse-M。

delta：仅重算(R,j)；保留完整CROSS multiplicity，枚举新的single-cross邻居三角形；M_after=M_before−|旧含R multi|+|新含R multi|。

rollback：当前copy-on-write沙箱，丢弃私有状态即回滚。未来正式状态发布应版本检查、独立完整验证、一次交换全部state，不允许半提交。本轮没有COMMIT API。

## Explicit limits / next task

不能证明lowest-multi-count victim ordering最优或优于其他顺序。4例非总体成功率，M0011只证明第一victim耗尽，不能称SINGLE_VICTIM_UNRECOVERABLE。未尝试第二/第三victim，未做318循环、迭代reroute、depth-2、fragment或3D。

建议M1.7：受控single-target depth-1原型与事务验收，验证逐ordinary victim回退与独立winner全布局验收；不自动实施。本轮按用户最后指令完成报告/checkpoint后停止。

## Artifacts

outputs/step_8_5_m1_6_probe_summary.json；victim_statistics.json；victim_order.csv；四个*_candidates.json；independent_validation.json；supplemental_checks.json；integrity.json；protected_hashes.json；tests.json（以上均有step_8_5_m1_6_前缀）。

scripts/local_recovery_feasibility.py、audit_local_recovery.py、verify_local_recovery.py、finalize_recovery_audit.py、run_local_recovery_tests.py；tests/test_local_recovery_feasibility.py。仅辅助沙箱，不是正式恢复器。
