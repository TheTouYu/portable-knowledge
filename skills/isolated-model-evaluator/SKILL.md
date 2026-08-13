---
name: isolated-model-evaluator
description: 把具体任务委派给一个全新的隔离 Pi 模型上下文去执行（子代理/独立模型），或评估技能/文档/工作流在无隐藏上下文下是否可用。当任务确定型、有明确验收、可写成任务文件、想节省主会话上下文或并行推进时（如派活、委派、子代理、独立模型、技术评估、验证技能/CLI/文档可用性、测试检索质量、模型对比），使用本技能。它启动一个无会话、无上下文、无自动技能的干净 Pi 进程，只加载指定的技能/工具，保留 JSONL trace 并汇总工具调用、错误、成本、最终答案与工作区变化。
compatibility: Project skill for Pi and other Agent Skills-compatible harnesses; the bundled runner requires Python 3 and the pi CLI.
---

# Isolated Model Evaluator

Two equally valid uses, same runner:

1. **Delegation（派活/子代理）**：把确定型任务交给独立模型执行，主模型只校验结果——节省主会话上下文、并行推进、避免上下文污染。
2. **Evaluation（评估）**：验证技能/CLI/文档/工作流在无隐藏上下文下能否被理解与执行（本技能的历史定位）。

## Delegation（派活）

### 什么时候适合派活

满足多数条件时派：

- 任务确定型：目标、输入、验收标准都能写清楚，不需要主会话的历史来理解；
- 可形成独立任务文件：背景 + 精确目标 + 验收命令/标准 + 约束（哪些不能碰、只读还是允许候选）；
- 任务自包含：不需要追问用户、不需要主会话的中间结论；
- 收益明确：任务耗时长、工具调用多、或会塞爆上下文（如大范围搜索、批量分析、代码审查、独立验证）。

不适合派活：需要用户拍板、需要主会话的未落盘结论、跨多个仓库的大改、有安全边界的写回决策。

### 任务文件编写原则：给材料，不给答案

调用子代理时**只给最关键的信息和原始信息**，不要给主模型推导好的详细方案：

- **必须给**：任务目标、用户教学/设计依据（原文或精神）、工作基（副本/输入文件路径）、验收标准、安全边界（禁止项）、知识入口（规则文档位置 + 要加载的核心技能列表）
- **不要给**：实现细节、具体步骤、坐标/ID/推导结论——这些让子代理自己从规则文档和技能里查出来
- **为什么**：①详细方案是主模型从规则+技能推导的，子代理用同样的材料能自己推导，还给方案会限制它发挥（可能发现更好的做法）；②主模型方案若有错，子代理照做会把错误放大；③"告诉它规则文档在哪里、有哪些核心技能"比"告诉它怎么做"更有价值
- **必须给的数据要标注来源**：任务文件里的规格/数值分两类标注——「真实样本确认」（子代理无需重验）vs「主模型推导」（**以真实样本/文档为准**，子代理落地前自行验证）。实测教训（2026-08-12 复盘）：任务文件 3 处错误前提（inflow 无 name 字段、node-add 参数顺序、param 类型大小写）导致子代理 6-8 回合"被迫自证→试错"；标注来源后这类浪费整体消失

### 标准派活流程

1. 按上述原则把关键信息写成任务文件（放 /tmp，不放项目里）；
2. 运行：

```bash
python3 ~/.pi/agent/skills/isolated-model-evaluator/scripts/evaluate.py \
  --root <项目根> \
  --skill <显式技能路径> \
  --task-file /tmp/<task>.md \
  --output-dir /tmp/<eval-dir>
```

   默认 `deepseek / deepseek-v4-flash / thinking=max`（用户指定）；要改模型/思考级别时显式传 `--provider --model --thinking`；
3. 子模型只产 /tmp 候选（执行类任务）或只读结论（验证类任务）；
4. 主模型校验结果（候选 diff、报告、trace），通过后再向用户汇报或由用户授权写回；
5. 汇报时附：子模型结论 + 主模型校验结论，区分两层。

执行类任务不要带 `--assert-no-changes`（它要求只读）；只读验证类任务带上。

### 代码仓派活清单（2026-08-13 PKC 五 Issue 横向复盘）

- **给真实开发入口**：任务文件必须区分 production wrapper 与源码入口。若 detached worktree 不含被 `.gitignore` 排除的 runtime，直接给 `PYTHONPATH=src python3 -m <package>.cli ...`，不要把依赖缺失 runtime 的 wrapper 列为可用命令。
- **写清权限矩阵**：分别说明真实工作树和一次性 fixture/copy 允许什么。只有任务明确授权时，才可在 disposable fixture 内 `git commit` 或执行 approve/apply；该授权不外溢到真实工作树。
- **复用现有测试资产**：先定位已有 tempfile fixture、测试基类和 CLI helper；优先在现有测试中补一个聚焦回归。确需 smoke 时只保留一个一次性副本流程，不重复写多份内联脚本或新增通用 helper。
- **让探测命令表达预期**：允许“无匹配”的存在性探测写成 `rg ... || true`；预期必须命中的搜索保留非零退出，让 evaluator 能区分正常缺席与真实失败。
- **控制验证节奏**：任务文件写明基线命令、耗时和已知失败。实现期跑受影响的测试类，最终只跑一次全量；新增 CLI 文件参数必须至少走一次真实 CLI 入口。

## Evaluation（评估）

This is the optional evaluation companion to `pkc-project-operator`, not a second operator. Humans use the Operator for all ordinary project installation, query, capture, maintenance, runtime upgrade, and approval/application work. Invoke this Evaluator only when fresh-context model usability is itself being tested—for example after a Skill, CLI, project Adapter, routing Context, or model-facing workflow changes. A normal knowledge Bundle, Authority refresh, or real-environment check does not require it.

A target project's `<project>-knowledge-adapter` is a separate project-owned thin routing layer, not either repository companion Skill. Runtime upgrades do not update this Evaluator, the global Operator, or project Adapters. From a clean PKC checkout, both repository Skills are installed or updated together with `python3 skills/pkc-project-operator/scripts/pkc_operator.py install-global --source .`; Adapter changes use a separate reviewed project diff.

Test project intelligence and model-facing workflows without trusting the current conversation's accumulated context. The runner launches a new Pi process with no session, no context files, no auto-discovered Skills, and no extensions, then explicitly loads only the target Skill(s) requested for the evaluation.

This is the canonical package at `skills/isolated-model-evaluator/`. Resolve script paths from this directory.

## What It Verifies

Suitable targets include:

- whether a fresh model can operate PKC or a project Skill from documentation alone;
- whether a CLI contract is complete and discoverable;
- whether a claimed workflow can be reproduced without hidden chat context;
- whether retrieval answers satisfy explicit correctness, refusal, permission, and scope criteria;
- where the model guessed a command, hit a tool error, read extra files, or recovered;
- whether documentation or retrieval improvements reduce errors, tool calls, elapsed time, tokens, or cost.

A successful process does not by itself prove semantic correctness or improved performance. Define observable acceptance criteria before the run, keep the task and model settings stable for comparisons, and inspect the trace/report.

## Safety Defaults

1. Check `git status --short --branch` before evaluation and preserve all existing worktree changes.
2. The evaluator gives the child model only `read,bash` unless overridden. Read/query evaluations are read-only; plan/capture evaluations may create only the reversible candidate artifacts required by their task and normal review gates.
3. For read-only behavior, use `--assert-no-changes`; it adds an explicit read-only prompt boundary and fails when the workspace fingerprint changes.
4. For candidate-writing behavior, omit `--assert-no-changes`, use an expendable fixture, and define an external oracle for allowed candidate files and formal-Authority invariants. This is not permission to approve/apply, perform Git mutations, or change formal authority.
5. Pi's `bash` tool is not a sandbox. Fingerprinting detects changes after the fact; it does not prevent them. Use an expendable worktree, copy, or container for untrusted or mutation tests.
6. Never put secrets, raw sensitive materials, private mappings, or unrestricted transcripts in the task or trace.
7. Store raw traces and reports outside the repository by default. Do not commit model traces unless explicitly required and reviewed.
8. Do not stage, commit, push, publish, or delete files unless the user explicitly asks.
9. The fingerprint excludes `.git/`, `.local/`, and `__pycache__/` by default. It therefore does not prove those paths were untouched; add stronger process isolation when that matters.

## Standard Evaluation

Write a precise task file outside the repository or pass `--task` directly. For realistic routing evaluations, keep the child-facing request at the real user ambiguity level and put detailed expected classification, paths, counts, permissions, and lifecycle answers in an external child-inaccessible oracle. State only the boundaries the real user would know:

- the conclusion or capability being tested;
- exact observable steps and acceptance criteria;
- allowed tools and mutation boundary;
- expected outputs or invariants;
- instruction to report documentation/tool inconsistencies instead of guessing silently.

From this repository root:

```bash
python3 skills/isolated-model-evaluator/scripts/evaluate.py \
  --skill skills/pkc-project-operator \
  --task-file /tmp/pkc-eval-task.md \
  --assert-no-changes \
  --output-dir /tmp/pkc-isolated-eval
```

The runner defaults to the user's delegation profile `deepseek / deepseek-v4-flash / thinking=max`. Keep this profile unless the human explicitly chooses another model. For reproducible comparisons, continue to pin all three in recorded commands:

```bash
python3 skills/isolated-model-evaluator/scripts/evaluate.py \
  --provider PROVIDER \
  --model MODEL \
  --thinking max \
  --skill skills/pkc-project-operator \
  --task-file /tmp/pkc-eval-task.md \
  --assert-no-changes \
  --output-dir /tmp/pkc-isolated-eval
```

To evaluate the repository without loading a target Skill:

```bash
python3 skills/isolated-model-evaluator/scripts/evaluate.py \
  --task "Read the documented project entry points and verify ..." \
  --assert-no-changes
```

Repeat `--skill` to load more than one explicit Skill.

## Isolation Contract

The runner invokes Pi with:

```text
--print --mode json --no-session
--no-context-files --no-skills --skill <explicit target>
--no-extensions --no-prompt-templates --no-themes
--tools read,bash
```

The child does not receive the parent conversation, auto-discovered `AGENTS.md`, other project Skills, or a saved session. Explicit target Skills are the only Skill instructions appended to its system context. The child can still read files with its allowed tools when the task directs it to do so.

Do not use `--no-tools`: observing real project interaction is the point. Use `--tools` to narrow capability when appropriate.

## Outputs

Each run creates:

```text
<output-dir>/
├── trace.jsonl
├── report.json
├── final.md
├── task.md
└── invocation.json
```

`report.json` includes process status, provider/model settings, assistant turns, tool calls and errors, token/cache usage, reported cost, final-answer presence, and workspace changes. Read [the report contract and interpretation guide](references/report-contract.md) completely before drawing conclusions.

## Performance Iteration

For meaningful before/after comparisons:

1. Keep the task, fixture, provider, model, thinking level, tools, permissions, and timeout fixed.
2. Use a fresh output directory and fresh child context for every run.
3. Evaluate task-specific correctness and refusal behavior first.
4. Then compare workspace changes, tool errors, silent guessing, tool calls, elapsed time, token usage, and cost—in that order.
5. Use multiple runs when provider variance matters; do not claim improvement from one noisy sample.
6. Keep raw traces outside Git and record only reviewed aggregate conclusions in project documentation or governed knowledge.

This runner records metrics; it is not a statistical benchmark harness and does not calculate significance.

## Diagnosis Loop

When a run fails:

1. Inspect `report.json` for the first tool error and command.
2. Inspect only adjacent `trace.jsonl` events first to see what the model knew.
3. Classify the failure: missing/stale docs, wrong Skill, undiscoverable CLI, omitted prerequisite, ambiguous task, model noncompliance, or tool defect.
4. Fix the smallest authoritative source.
5. Run a completely fresh evaluation with a new output directory.
6. Compare correctness and errors before efficiency metrics.

## Completion Standard

A successful evaluation requires all task-specific criteria plus:

- child Pi exits zero;
- a final answer exists;
- no unexpected tool errors;
- no project file changes when read-only was required;
- the answer reports limitations and scope accurately;
- deterministic validation required by the task passes.

A model that recovers from undocumented flags demonstrates resilience, not documentation quality. Report recoveries and tool errors explicitly.
