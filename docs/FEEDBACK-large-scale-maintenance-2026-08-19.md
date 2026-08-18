# FEEDBACK — 大规模知识维护实操（某大型消费方项目, 2026-08-19）

> 适用项目：Portable Knowledge Core（~/portable-knowledge，runtime 0.2.0rc5）
> 反馈来源：在 某大型消费方项目 项目完成一次大规模维护的真实踩坑——
> 96 条 stale authority ref 逐条评审、90 条 refresh/修正、24 条 claim 双语化调检索、全树 68 topic 检索评测接线（68/68）。
> 每条需求均标注 现状/痛点 → 建议 → 涉及文件/函数。

---

## A. API 需求（按优先级）

### P0-1 ｜ plan 操作的全仓复制太慢且脆（性能/健壮性）
- **现状**：`semantic_plan.py::_with_overlay`（约 272 行）每次 plan 操作都把整个仓库根（除 `.git`/`.local`）完整复制到 staging，单次 add/revise 耗时 10–30 秒。
- **痛点**：①大量操作被拖慢；②根目录易变临时文件（并发删建的 `tmp-*.ts`）会在复制中途触发瞬态 `FileNotFoundError`（本轮被迫加"重试"）。
- **建议**：只复制权威相关路径（`data/knowledge/**`、`knowledge/**` 及本次操作 touched/ref 涉及的路径），或改用稀疏复制 / 临时 git worktree。
- **文件**：`src/portable_knowledge/semantic_plan.py::_with_overlay`

### P0-2 ｜ 评估门一条失败卡死所有 finalize（设计）
- **现状**：`semantic_plan.py::finalize` 的 full preflight 跑**全部** retrieval-evaluation 用例，任何一个用例失败就阻塞所有 plan finalize（哪怕与被改内容无关）。
- **痛点**：本轮一个被"用户未提交文件"阻塞的 stage3 用例，阻塞了 usage/debug 等无关 claim 修订，只能临时把门切回全绿配置、完成工作后再接回。
- **建议（三选一）**：
  1. `evaluation_contract.py` 每用例支持 `blocking: false`（非阻塞只告警）；
  2. full preflight 只对 `affected_by` 与 plan 相交的用例跑（与 delta check 一致）；
  3. `finalize`/`apply` 提供 `--defer-evaluation <case-ids>`。
- **文件**：`src/portable_knowledge/evaluation_contract.py`、`semantic_plan.py::finalize/_assert_budget`

### P1-3 ｜ topic 元数据更新 API（检索调优的成本黑洞）
- **现状**：topic 创建后无法改 keywords/aliases/summary（`plan_new_claim` 对既有 topic 拒绝元数据）。
- **痛点**：检索索引已加权 `title 1.7 / summary 1.2 / keywords(identity)`，但唯一调优手段是逐条 `revise-claim` 改写正文——本轮为提升中文可检索性被迫改 24 条。
- **建议**：新增 `knowledge-plan update-topic --topic-id --title/--summary/--keywords/--aliases`，走 proposal + bundle + apply 治理。
- **文件**：`src/portable_knowledge/semantic_plan.py`（新增 update_topic 操作）、`core.py::plan_*`

### P1-4 ｜ authority ref 改路径 API（ref 无法重定向）
- **现状**：既有 claim 的 authority ref 无法改指向其它文件——`retire` 必须带 replacement、`add-authority-ref` 只能挂 plan 内新增/修订的 claim、revised claim 又强制 refresh 既有 ref。
- **痛点**：本轮"控制流规则从 `data-flow.md` 迁移到 `control-flow.md`"因此卡死（只能对旧路径 refresh 兜底，旧路径已不含规则，语义勉强）。
- **建议**：新增 `update-authority-ref --ref-id --path [--locator]`（在当前基线重算 approved_hash），或允许同一 plan 内 retire+add 配对（以 add 产出的新 ref 作为 retire 的 replacement）。
- **文件**：`src/portable_knowledge/semantic_plan.py`（add/retire-authority-ref）、`authority.py`

### P1-5 ｜ finalized 但未 apply 的 plan 恢复（身份成本）
- **现状**：finalized plan 既不能 rebase 也不能 abandon（`PLAN_FINALIZED_IMMUTABLE`，行 1171/1216）。
- **痛点**：基线推进（如并发提交）后，恢复只能 abandon + 重新 capture，导致 claim ID 全部重新生成（身份丢失、authority 历史断裂）。
- **建议**：允许对 finalized-but-not-applied 的 plan `rebase`（在新基线重派生 bundle，保留 operations 与 claim 身份），或提供 `recover <plan>` 重新锚定。
- **文件**：`src/portable_knowledge/semantic_plan.py::rebase_plan/abandon_plan`

### P1-6 ｜ 批量 refresh authority ref
- **现状**：`refresh-authority-ref` 一次只能刷一条；本轮 81 条刷新需要 81 次 CLI 调用（每次还叠加全仓复制）。
- **建议**：`refresh-authority-ref --all-stale --reason` 批量；或维护类 capture 支持文件驱动的 refresh 列表。
- **文件**：`src/portable_knowledge/semantic_plan.py`、`core.py::knowledge_plan`

### P2-7 ｜ 评估指标与覆盖报告
- **现状**：`evaluate_normalized_cases` 中 `best_expected_claim_rank` 在 `expected_claim_ids` 为空时为 `None`（看不到主题排名分布）。
- **建议**：①同时报告 best topic rank；②`knowledge-check` 加 `--eval-coverage`，列出没有评测用例的 topic。
- **文件**：`src/portable_knowledge/evaluation_contract.py::evaluate_normalized_cases`、`core.py::knowledge_check_command`

### P2-8 ｜ 草稿/意图卫生
- **现状**：`PLAN_INTENT_OVERLAP` 仅警告，orphan draft 堆积无自动消重。
- **建议**：在 `finalize`/`bundle-status` 自动识别"意图已被 apply 覆盖"的 draft 并提示 `bundle-supersede`。
- **文件**：`src/portable_knowledge/core.py`、`bundle.py`

### P2-9 ｜ bundle approve/apply UX
- **现状**：`bundle-approve`/`bundle-apply` 必须手填精确 `--content-hash`（不能从 bundle-status 自动解析），且 `--apply` 必须显式（dry-run 默认）。
- **建议**：无歧义时自动解析 hash；dry-run 结果大声回显（明确"未落盘"）。
- **文件**：`src/portable_knowledge/core.py::bundle_approve_command/bundle_apply_command`

### P2-10 ｜ capture 扩展
- **现状**：`knowledge-plan capture` 仅支持 JSON 草稿且直接 finalize。
- **建议**：①支持 `--format markdown` 草稿；②`--preview-only` 先展示 bundle semantic_diff 不 finalize。
- **文件**：`src/portable_knowledge/semantic_plan.py::capture`

---

## B. 技能更新建议（`skills/pkc-project-operator/SKILL.md`）

新增"大规模维护实操模式"小节，沉淀以下实证经验：

1. **全仓复制 overlay 遇易变临时文件** → 对 `No such file or directory .../tmp-*` 瞬态错误做有限重试；根因见 A P0-1。
2. **ref 指向用户未提交 dirty 文件** → 触发 `PLAN_AUTHORITY_WORKTREE_DIRTY`；应暂缓该 ref（提交是用户职责），不要硬刷、不要替用户提交。
3. **finalized plan 不可变** → abandon + 重 capture 会重生成 claim ID（身份成本）；恢复前先确认是否可避免（见 A P1-5）。
4. **评估门接线时机** → 应在全部评测用例可绿之后接线；有已知失败用例时它会把 finalize 全部卡死；用例 `affected_by` 建议收到 topic 级，避免 node 级过宽误伤无关 plan。
5. **检索调优杠杆** = topic keywords/aliases（标题权重最高）；在 `update-topic` API 落地前，可用 revise claim statement 兜底。
6. **retire+add 改 ref 路径的限制** → 旧路径仍含相关内容时可用 refresh 兜底；否则需等 A P1-4。
