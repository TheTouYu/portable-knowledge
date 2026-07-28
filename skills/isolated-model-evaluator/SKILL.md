---
name: isolated-model-evaluator
description: Run a fresh isolated Pi model context to verify whether a project conclusion, workflow, Skill, CLI, or documentation can be understood and executed without hidden conversation context; retain a JSONL trace and summarize tool calls, tool errors, cost, final answer, and workspace changes. Use when testing PKC usability, retrieval quality, project intelligence, documentation, agent workflows, or model performance across iterations.
compatibility: Project skill for Pi and other Agent Skills-compatible harnesses; the bundled runner requires Python 3 and the pi CLI.
---

# Isolated Model Evaluator

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
2. Default to read-only verification. The evaluator gives the child model only `read,bash` unless overridden.
3. Explicitly tell the child not to modify files, use apply flags, or perform Git mutations when evaluating read behavior.
4. Use `--assert-no-changes`; the runner fingerprints project files before and after and fails if tracked project content changes.
5. Pi's `bash` tool is not a sandbox. Fingerprinting detects changes after the fact; it does not prevent them. Use an expendable worktree, copy, or container for untrusted or mutation tests.
6. Never put secrets, raw sensitive materials, private mappings, or unrestricted transcripts in the task or trace.
7. Store raw traces and reports outside the repository by default. Do not commit model traces unless explicitly required and reviewed.
8. Do not stage, commit, push, publish, or delete files unless the user explicitly asks.
9. The fingerprint excludes `.git/`, `.local/`, and `__pycache__/` by default. It therefore does not prove those paths were untouched; add stronger process isolation when that matters.

## Standard Evaluation

Write a precise task file outside the repository or pass `--task` directly. State:

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

The runner defaults to the cost-effective evaluation profile `aijws / gpt-5.6-luna / medium`. Keep this profile for normal Skill iteration unless the human explicitly chooses another model. For reproducible comparisons, continue to pin all three in recorded commands:

```bash
python3 skills/isolated-model-evaluator/scripts/evaluate.py \
  --provider PROVIDER \
  --model MODEL \
  --thinking medium \
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
