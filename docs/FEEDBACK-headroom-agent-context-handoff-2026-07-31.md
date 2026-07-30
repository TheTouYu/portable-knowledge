# Real-consumer feedback: Agent context usage during interrupted-task handoff

Status: field feedback

Reported: 2026-07-31

Consumer: Headroom, a real consumer project using the project-locked PKC runtime

Observed runtime/Core: `0.2.0rc5`

Priority: P1 Agent workflow efficiency and novice-facing communication; no request to weaken safety gates

## Summary

A resumed Headroom task completed correctly, but the Agent spent substantially more context than the user expected after receiving a handoff document. The main task was to finish and review a Pi project/global configuration change, run the tests and typecheck, report the result, and wait for explicit commit approval. The task was completed and committed only after approval.

The user then asked two basic questions:

1. Where did the context go, and was that amount necessary?
2. What was the main task of this round?

The second question exposed a communication failure: the Agent did not state the current round's main task before beginning the recovery and commit workflow. A novice user therefore had to infer the objective from tool activity and the final commit.

## What was necessary

These parts were justified by the handoff and safety boundaries:

- verify branch, baseline commit, dirty paths, expected file hashes, and port state;
- preserve an unrelated dirty `README.md` change;
- inspect the bounded implementation diff and relevant tests;
- run the Pi tests, typecheck, and diff hygiene check;
- obtain fresh commit confirmation before creating a new commit;
- scope the commit to the six requested Pi files.

These checks protected against resuming the wrong worktree, overwriting user changes, or expanding prior commit authorization.

## What was unnecessarily expensive

The handoff already contained expected hashes, expected dirty paths, test commands, completed status, and explicit next steps. The recovery still spent a large amount of context on:

- repeatedly reading long, truncated files and re-reading large diff outputs;
- investigating Pi's configuration-directory implementation after the requested tests and typecheck had passed;
- exploring the PKC capture workflow at length before deciding that a conversational feedback report should be delivered to the PKC project rather than promoted into Headroom authority;
- allowing tool output truncation to create follow-up reads instead of selecting only the relevant ranges earlier.

The handoff itself also repeated the same status, constraints, facts, execution recipe, and evidence table. It was safe but not context-efficient.

## Recommendations

### 1. Lead every resumed round with the task contract

Before the first tool call, state in plain language:

```text
本轮主要任务：完成并审查 Pi 的项目/全局配置闭环；验证测试和 typecheck；得到你的确认后再提交。
当前状态：实现已完成，尚未提交。
本轮不会做：不修改无关 README，不启动代理，不写真实全局配置。
```

This should be mandatory for resumed work and for novice-facing sessions.

### 2. Make handoffs compact and evidence-oriented

Prefer four sections:

- objective and acceptance criteria;
- current state and exact next action;
- protected changes and mutation gates;
- verification evidence already completed.

Avoid duplicating the same facts in separate “status”, “facts”, “execution recipe”, and “evidence” sections. Store large hashes or detailed historical notes separately only when they are actually needed for verification.

### 3. Treat handoff evidence as reusable evidence

When a handoff provides exact expected hashes and the first read-only check matches, do not re-derive the same facts by repeatedly reading complete files. Read only the bounded diff and the functions implicated by the review focus. If a new concern requires broader inspection, state the evidence gap first.

### 4. Add a context budget to recovery

A resumed task should have a small recovery budget, for example:

- one bounded worktree check;
- one diff review pass;
- one verification pass;
- one final communication pass.

When the budget is exceeded, the Agent should explain why the evidence gap matters before continuing.

### 5. Make user communication an acceptance criterion

A technically complete commit is not a complete interaction. The final report should explicitly answer:

- what this round's main task was;
- what changed;
- what verification passed;
- what was not changed;
- whether a commit was created and why.

This is especially important when a handoff document is involved: the handoff is internal recovery context, not the user's product-level task description.

## Suggested evaluation cases

Add a real-consumer evaluation where:

- the task resumes from a detailed handoff;
- the worktree contains one protected unrelated change;
- the implementation and verification are already complete;
- the Agent must identify the round goal before reading more files;
- the evaluator checks that the Agent does not repeat bounded evidence unnecessarily;
- the final answer explicitly names the main task in novice-friendly language.

Success means preserving all mutation and authority safety gates while reducing redundant context use and making the round objective obvious before execution.

## Scope and boundary

This feedback concerns Agent workflow orchestration, handoff format, context budgeting, and user communication. It does not claim that PKC authority checks, exact-hash review, project Memory, or Git confirmation gates should be weakened. It is a product feedback document, not a formal PKC Claim or an authorization to modify PKC behavior.
