# 受保护的收尾流程

记录 PKC 在正式写入前如何展示收尾步骤和生命周期状态。

<!-- CLAIM:START clm_2A7C39AAEDCC3D4395D9E56EB5 -->

### 计划检查提供只读的五阶段收尾预览

knowledge-plan inspect 会返回只读的 closeout_preview，依次展示 Claim capture、Memory synchronization、Git commit、Authority refresh 和 final validation；当 Claim 变更影响配置为 count_surfaces 的 Memory 角色时，它会列出待同步路径及关联 Authority，报告 Authority Reference 的 added、refreshed、retired、affected 计数，并以 PASS、PASS_WITH_REVIEW 或 FAIL 表示当前收尾健康状态。

#### 适用边界

这只说明检查输出会预告阶段、依赖和审查状态；不表示检查会更新 Memory、创建 Bundle、批准或应用 Bundle、提交 Git、刷新 Authority，或修改本地投影。preview 后发生的基线或工作区漂移仍由普通 plan、approval 和 apply 门禁拒绝。

<!-- CLAIM:END clm_2A7C39AAEDCC3D4395D9E56EB5 -->

<!-- CLAIM:START clm_83EBA25FDD31CB6DF23447C7C7 -->

### 计划检查分开报告 Bundle 生命周期事实

knowledge-plan inspect 会把 approval_recorded、bundle_state 和 bundle_applied 作为三个独立的生命周期事实返回。

#### 适用边界

这只说明检查结果会区分是否已记录批准、Bundle 当前状态和是否已应用；它不自动批准或应用 Bundle，也不证明后续 Git 提交或最终验证已经完成。

<!-- CLAIM:END clm_83EBA25FDD31CB6DF23447C7C7 -->

<!-- CLAIM:START clm_75D42A38D15CF9BF2CA282BD18 -->

### 计划 Claim 标识可直接发现

knowledge-plan add-claim 的文本成功输出会显示生成的 Claim ID；add-authority-ref 找不到计划 Claim 时会指出对应计划 JSON 路径，并说明标识位于 claims 下。

#### 适用边界

这只描述 CLI 的可发现性；不改变 Claim ID 生成算法、计划内容、Authority 校验或正式写入流程。

<!-- CLAIM:END clm_75D42A38D15CF9BF2CA282BD18 -->

<!-- CLAIM:START clm_0CCABBA16112B45E1E013C7B9D -->

### 废弃计划不能被 init 静默复用

knowledge-plan init 若以相同确定性输入命中已废弃计划，会立即返回 PLAN_ABANDONED，指出计划 ID 并提示使用不同 intent 创建新计划。

#### 适用边界

开放计划的幂等重放保持不变；废弃计划不会重新打开，也不会自动生成新的计划 ID。

<!-- CLAIM:END clm_0CCABBA16112B45E1E013C7B9D -->

<!-- CLAIM:START clm_FEA9677C7712F21ACDD64C4212 -->

### Bundle 检查兼容地列出生命周期文件

bundle-inspect 保持 bundles 数组输出形状，并在每个 Bundle 记录的 lifecycle_files 中分别列出 Bundle、approval 和 applied 文件路径；expected_changed_files 继续只表示不可变 Bundle action 的目标文件。

#### 适用边界

指定单个 Bundle ID 时记录仍位于 bundles[0]；该字段不改变 Bundle 内容哈希、action 目标或审批与应用分离。

<!-- CLAIM:END clm_FEA9677C7712F21ACDD64C4212 -->

<!-- CLAIM:START clm_A8BA119B3C73E21DEB488EE768 -->

### Adapter 经精确审查应用后按约定 isolated cases 评测

### Adapter 经精确审查应用后按约定 isolated cases 评测

pkc-project-operator 的 plan-adapter 会在目标项目外生成确定、可审查且状态为 not_evaluated 的 Adapter 提案；人工查看完整候选差异并确认 plan_hash 后，apply-adapter 只应用该精确候选。随后，evaluate-adapter 仅对已经应用且 hash 匹配的 Adapter 运行人工预先确认、由 cases_hash 锁定的 capability 与 boundary isolated cases，逐项记录结果、tool errors、cost、latency 和 workspace-change status；只有全部约定 cases 的进程、runner、显式输出断言及只读门均通过时，独立 evaluation record 才标记 evaluated。

#### 适用边界

原 Adapter proposal 保持 not_evaluated，评测记录只证明精确 Adapter hash、精确 cases hash 和精确 provider/model/thinking 组合通过了这些 isolated tasks。静态检查、应用成功、generic runner ok、synthetic fixture 或单次模型输出都不证明真实项目、生产、游戏、编译器或其他真实环境行为；评测不修改 Adapter、Authority、Memory、runtime 或 Git，也不 commit/push。

<!-- CLAIM:END clm_A8BA119B3C73E21DEB488EE768 -->
