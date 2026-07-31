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
