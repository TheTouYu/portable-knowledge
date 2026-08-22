# FEEDBACK: PKC 知识树使用阻碍报告（2026-08-22）

来源：Genshin-TS 多智能体共享 git worktree 的真实使用反馈，针对
`portable-knowledge 0.2.0rc1` 的 `knowledge-plan` 工作流。

## 阻碍清单

1. **BLOCKER：`knowledge-plan add-authority-ref --path DESIGN.md` 失败**
   `PLAN_AUTHORITY_NOT_COMMITTED` 即使加了 `--baseline worktree` 也失败；
   暂存文件同样失败。期望 worktree 模式接受未提交/新写入的 Authority 文件，
   或提供显式的 pending-authority 机制。
2. **`init --help` 与实际行为不一致**
   `--baseline worktree` 的帮助文案声称接受 applied-but-uncommitted
   maintenance，但实现仍只检查 committed HEAD。
3. **`new-claim --help` 误导**
   help 列出 `--apply`，生产路径却拒绝 `new-claim --apply`。期望把
   `--apply` 标记为 maintainer/compat-only，或提供到 `knowledge-plan` 的快捷方式。
4. **`knowledge-plan` 流程长、重复、失败无指引**
   6 步流程反复填写 topic metadata；`AUTHORITY_FACT_COVERAGE` 报错不告诉怎么修。
   期望批量/单条都方便，且错误给出修复动作。
5. **Design-intent topics 死锁**
   第一条 claim 的 Authority 就是同一批新写入、未提交的 design doc；期望
   worktree/design_intent 模式允许同批 doc+claim 录入。

## 已实施修复（对应 commit）

- worktree baseline 现在真正读取 working tree 作为 Authority 快照：
  `add-authority-ref`、`refresh-authority-ref`、`update-authority-ref`、
  `check_delta`、finalize 环境校验均改用 `_authority_bytes`，committed 模式
  的 dirty/committed 检查保持原样。
- `knowledge-plan capture --file DRAFT.json` 增加 `--baseline worktree`，
  draft 也支持 `baseline_mode`，让批量录入直接引用未提交 design doc。
- `AUTHORITY_FACT_COVERAGE` 的 delta 错误现在附带 `recommended_action`，
  直接给出补 `add-authority-ref` 的完整命令模板。
- `new-claim --apply` 帮助文本标明生产模式禁用、仅 maintainer recovery。
- `init --help` 更新为明确接受“新写入的 working-tree 文件”作为 Authority。

## 验证

- `tests/test_semantic_plan_contract.py` 新增：
  - worktree baseline 接受未跟踪 design doc 并完成 check/finalize；
  - capture `--baseline worktree` 批量录入未提交 doc；
  - coverage 错误带 `recommended_action`。
- 全量测试 `python -m unittest discover -s tests -p "test_*.py"` 通过。
