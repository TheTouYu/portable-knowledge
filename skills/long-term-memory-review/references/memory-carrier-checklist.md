# 记忆载体盘点清单（五类）

审查目标项目时逐类检查，回答一个总问题：

> 任务中用到的关键规则、需求和结论，现在落在哪个**可检索**的载体里？
> 如果只活在会话里（会被 checkpoint 压缩蒸发），就是记忆缺口。

## 1. 技能（`.agents/skills/`）

- 位置：`<project>/.agents/skills/`（可能是 symlink 到共享目录，先 `ls -ld` 确认单源/双副本）。
- 检查：
  - 任务涉及的操作是否有对应技能、技能本身是否沉淀了本轮结论（新章节 / 新 references）。
  - 技能里的"阻碍点 / 未闭合 / 续作入口"是否记录了该任务踩过的坑。
- 判据：从技能 SKILL.md 能直接找到"下一步该怎么做 / 已闭合规则"，无需重新推导。

## 2. 知识树 PKC（长期记忆引擎）

- 入口：`<project>/tools/pkc.py`（只读查询，见项目 AGENTS.md 的信息检索优先级）。
- 检查命令（**必须先查再下"缺失"结论**）：
  - `python tools/pkc.py query "<关键词1 关键词2 关键词3>" --level 2`——必须带 `--level 2`（level 1 只搜节点标题）。
  - `python tools/pkc.py tree`——看 topic 覆盖。
  - `python tools/pkc.py progressive-query --context <ctx> --intent "<问题>"`——是否 coverage gap。
  - gap 时降级全库 `query`（换个关键词 / 中英混排 / `knowledge-search --semantic`）。
- 判据：关键规则有 claim、能被关键词召回；缺 → 记 pending-capture，走 `pkc-project-operator` 的 knowledge-plan 入库（不要直接手写 registry/SQLite）。

## 3. 权威文档（`docs/**`）

- 位置：`docs/game-engine-knowledge/`（引擎/领域规则书）、`docs/architecture/`（当前实现）、
  `docs/maintenance/`（账本与开放项）、`docs/project-intelligence/`（评测集/基线/contexts）。
- 检查：规则是否带状态标签（已验证 / 待验证 / 当前实现）、是否有样本路径 + 命令 + 观察 + 结论 + 适用范围。
- 判据：真实 GIA/GIL 结论有证据链；只有结论没证据 = 不知道能不能信。

## 4. 账本（open-items / PROGRESS / TASKS）

- 位置：`docs/maintenance/open-items.md`、`PROGRESS.md`、`TASKS.md` 等。
- 检查：任务级需求与未完成项是否登记 OPEN、已落地是否登记 DONE（带证据 + 落地方式）。
- 判据：**需求 / 目标形态变化有外部账本**；否则 27 次上下文压缩后需求漂移，用户只能再提醒一次。

## 5. git 提交状态

- 命令：`git log --oneline -20`、`git status --short`、`git diff --stat`、`git diff --cached --stat`。
- 检查：
  - 提交粒度：小步（每可验证步骤一提交）还是堆积。
  - 未提交积压：untracked / modified 是否包含"会话里已闭环但没落盘"的成果。
  - staged 悬置：暂存区是否有不属于本任务的删除/修改，会不会污染下一次 `git commit`。
- 判据：每可验证步骤已提交；存在未提交成果时明确 owner 与丢失风险。

## 输出格式

每类一行：

```text
技能      ✓/✗  缺口一句话 + 证据（文件路径/时间点）
知识树    ✓/✗  ...
权威文档  ✓/✗  ...
账本      ✓/✗  ...
git 提交  ✓/✗  ...
```