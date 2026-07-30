---
name: handoff
description: Preserve session continuity with a self-contained handoff, and route explicitly requested durable goals, decisions, feedback, or knowledge through the project's governed knowledge workflow.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

# Handoff

Create a handoff document that lets a fresh agent resume the work with the smallest useful context window.

The handoff document is the **minimum recovery surface**. A fresh agent should be able to understand the current state, choose the next safe action, and run the first read-only verification by reading only the handoff document. References are for later deep dives, not prerequisites for ordinary resumption.

## Two simple user paths

Keep the user-facing workflow simple:

1. When the user invokes `handoff`, create the recovery document. Do not require PKC terminology, a schema, or a second form. Record stable goals and decisions as **durable candidates** in the handoff, but do not silently write them into formal knowledge.
2. When the user says to remember something in the knowledge tree, knowledge base, project memory, or long-term project knowledge, treat that as an explicit durable-capture request. Inspect the target project's operating rules and Adapter, then use its configured governed knowledge workflow. Preserve the distinction between feedback, Memory, a proposed decision, and a formal Claim/Authority change. Stop at the project's human approval gate; never self-approve, directly edit Authority, or turn an ordinary handoff into a Bundle.

If the project has no configured knowledge workflow, keep the item in the handoff under `durable_candidates` with `promotion_status: blocked_or_not_configured`, state the exact missing prerequisite, and continue producing the handoff. Do not invent a PKC layout or copy a neutral example.

A handoff is a session cursor, not the long-term source of truth. Long-term goals, confirmed decisions, and reusable project facts belong in the project's governed knowledge or committed project documentation after explicit review. Git and the current worktree remain the source of truth for code and files.

The document must declare exactly one handoff mode:

- `next-task`: the current work package is substantially complete and the next session begins a new task using the current results and durable constraints.
- `interrupted-task`: the current work package is incomplete and the next session must resume from a concrete unfinished step.

Do not blur these modes. `next-task` summarizes delivered results and starts a new task; `interrupted-task` preserves the unfinished execution state and prevents duplicate or unsafe work.

## Output Location

Save the document in the operating system's temporary directory, never in the current workspace.

- Linux/macOS: use `/tmp/<descriptive-name>.md`.
- Windows: use the user's temporary directory, for example `%TEMP%\\<descriptive-name>.md`.
- If the harness provides an existing handoff path, use that path.

Report the exact output path when finished.

## Information Priority

Write information in this order:

1. **Resume now**: the immediate task, current objective, next action, and first verification command.
2. **Operational truth**: confirmed state, files, IDs, paths, hashes, commands, prerequisites, safety gates, and known blockers needed to act correctly.
3. **Decision boundaries**: what is confirmed, what is only generated/automatically tested, what requires explicit human confirmation, and what must stop the work.
4. **Optional context**: links to specs, plans, ADRs, research, commits, diffs, logs, or external sources for deeper understanding.

Do not make the reader reconstruct critical facts by following references. If a fact is needed to execute the next action, copy the fact into the handoff even when it also exists elsewhere.

## Required Handoff Content

Use concise headings and concrete values. Include the sections below unless a section is genuinely not applicable; state `none` instead of omitting it.

### 1. Mode and Next Session Focus

Start with machine-readable fields:

```text
mode: next-task | interrupted-task
focus: <one-sentence next-session objective>
status_at_handoff: <one-sentence state>
```

State the user's requested focus in one or two sentences. If the user passed arguments, treat them as the focus and tailor the handoff to it.

Also include this compact continuity block immediately after the machine-readable fields:

```text
durable_goal: <the long-lived goal this work serves, or none>
durable_candidates: <none, or numbered candidates worth preserving beyond this session>
promotion_status: <not_requested | candidate_only | plan_prepared | approved | applied | blocked_or_not_configured>
knowledge_entrypoint: <project wrapper/Adapter path, or none>
```

`durable_candidates` must contain only items that are likely to change future work or remain valuable after three months. Mark observations, suggestions, and unverified conclusions as candidates or feedback, never as confirmed project facts. If the user explicitly requested durable capture, record the target, classification, plan/hash, and approval state; do not claim it was stored unless the project workflow reports that result.

For `next-task`, explicitly separate:

- `completed_this_round`: delivered results and their evidence;
- `next_round_task`: the new task, not a repetition of completed work;
- `durable_constraints`: facts from this round that must affect the new task.

For `interrupted-task`, explicitly separate:

- `completed_before_interruption`;
- `unfinished_step`;
- `last_successful_action`;
- `next_action`;
- `do_not_repeat`: commands or mutations already performed;
- `active_processes_or_artifacts`: running commands, watchers, locks, temporary files, candidates, or partial outputs, or `none`.

### 2. Current Status and First Check

Include:

- The exact next action, in execution order.
- The first read-only command or check to run.
- The expected successful result.
- The mismatch that means the handoff is stale.
- The point at which the agent must pause and ask the user.

The first check must reconcile the handoff against the current worktree, relevant files, generated artifacts, external files, or process state before any mutation. A handoff is a snapshot, not permission to trust stale hashes, IDs, paths, or outputs.

### 3. Working Context

Include only context needed for the next action:

- Repository or project paths.
- Relevant branch and commit identifiers.
- Files changed in the current work package.
- Existing dirty-worktree paths that must be preserved, listed by path only unless their contents are explicitly part of the task.
- Runtime/tool versions only when they affect execution.

Do not dump repository inventories, long conversation transcripts, or generic project background.

### 4. Facts and Constraints

Separate facts by status:

- **Confirmed**: directly established by source, test, user statement, or verified external evidence.
- **Unverified**: plausible or generated but not proven by the required evidence layer.
- **Unknown / blocker**: cannot be safely inferred.

Include exact values for IDs, names, paths, ports, hashes, configuration keys, graph names, resource IDs, or other identifiers whenever the next action depends on them.

### 5. Execution Recipe

Give a minimal, directly runnable recipe for the next bounded action:

- Required working directory.
- Required environment variables, with sensitive values redacted or replaced by placeholders.
- Commands in order.
- Expected outputs or assertions.
- How to interpret failure.
- Whether each command is read-only, generates local artifacts, changes tracked files, or mutates an external/real file.

Prefer commands that do not mutate external or real files for the first verification. If a command can write, label it clearly and state its authorization prerequisite. For an interrupted task, include the last known successful command separately from the next command; never make the recovering agent infer where execution stopped.

Do not include guessed values merely to make a command look complete. Use `<CONFIRM>` or mark the command blocked when a value is unknown.

### 6. Safety and Communication Gates

State explicitly:

- What the agent must not do without separate confirmation, such as injection, real-file writeback, deletion, rollback, commit, push, or editor/game operations.
- Which human confirmation has already been granted and its exact scope, target, and time boundary.
- Which actions still require fresh confirmation.
- Conditions that require an immediate stop and user question.
- How to preserve unrelated or concurrent work.
- Which dirty files belong to this work package, which belong to other collaborators, and which must not be read or touched.
- Whether a running process, watch mode, lock, temporary candidate, or partial output needs cleanup or human coordination.

A previous approval does not automatically authorize a different later mutation. A handoff may record an approval, but the recovering agent must not expand its target or reuse it for a different mutation.

### 7. Evidence Layers

For work involving code, generated artifacts, real files, or external behavior, distinguish the evidence already obtained and still needed:

- code/type/test checks;
- generated intermediate files and final artifacts;
- candidate generation or offline validation;
- real-file writeback and post-write structural verification;
- injection/import success;
- editor loading;
- in-product or game behavior.

Use an explicit table or status list with `done`, `pending`, or `blocked`. For every completed layer, include the observed result and its path/hash when relevant. For every pending layer, name the next evidence-producing action. Never describe a lower layer as proof of a higher layer.

### 8. Suggested Skills

Include a `suggested skills` section. List only skills that are relevant to the next session, with one short reason each. Do not suggest skills merely because they exist.

### 9. References

End with optional deep-context references grouped by purpose, for example:

- Specification / plan
- Source implementation
- Tests / fixtures
- Research / external evidence
- Commits / diffs

For each reference, give an exact path or URL and one phrase explaining when to read it. Do not tell the recovering agent to read all references before starting. Use references to expand context only when the handoff's facts are insufficient or the next action enters a new subsystem.

## Recovery Contract

Write the handoff so that the receiving agent follows this protocol:

1. Read only the handoff document first.
2. Determine whether the mode is `next-task` or `interrupted-task`.
3. Extract the immediate objective, first check, constraints, authorization scope, and stop conditions.
4. Inspect the current worktree and run the first read-only reconciliation check.
5. Compare observed state with the handoff's confirmed facts, including dirty paths, hashes, IDs, generated files, and process state where applicable.
6. If they match, continue with the bounded next action.
7. If they differ, stop and report the mismatch before mutating anything; do not silently refresh the handoff from the new state.
8. Read optional references only when a specific implementation or evidence gap requires them.
9. Reconfirm any pending human gate immediately before the mutation it protects.

If project-specific rules require additional startup files, record that as an explicit exception in the handoff's `References` or `Safety and Communication Gates` section. Do not silently turn every referenced artifact into a recovery prerequisite.

## No-Duplication Rule

Avoid copying large specifications, plans, ADRs, issue bodies, logs, or diffs. Instead:

- copy only the exact facts needed to resume safely;
- summarize decisions and their current scope;
- reference the complete artifact for details;
- preserve distinctions between implementation, generated output, real-file evidence, and external behavior.

The handoff may repeat a small fact already present elsewhere when that repetition removes a required lookup during recovery. Minimal context means minimal **required reading**, not minimal operational detail.

## Redaction

Redact secrets and personal data, including API keys, passwords, access tokens, private URLs, account identifiers, and unnecessary local user names or home paths.

Keep technical identifiers that are required to resume, such as repository-relative paths, public commit IDs, map or graph IDs, fixture IDs, and non-sensitive hashes. Replace machine-specific paths with placeholders when the receiving agent can derive them safely. Never invent a replacement value that could be mistaken for a real target.

## Final Check

Before finishing:

- Verify the document exists at the requested temporary path.
- Verify exactly one mode is declared: `next-task` or `interrupted-task`.
- Confirm the first reconciliation action is executable or explicitly blocked.
- Confirm `completed_this_round`/`next_round_task` or the interrupted-task equivalents are not conflated.
- Confirm the last successful action and next action are distinguishable when work is interrupted.
- Confirm every critical unknown is marked instead of guessed.
- Confirm authorization scope is specific and pending gates are visible.
- Confirm active processes, temporary artifacts, and concurrent dirty paths are accounted for.
- Confirm sensitive data is redacted.
- Confirm the document does not require reading all references to understand the next action.
- Report the exact path and a one-line summary of the next session focus.
- Report whether `durable_candidates` were found and whether they were only recorded, sent through a governed plan, or blocked.
- If the user asked for knowledge capture, report the exact project entrypoint and approval boundary still pending; never imply that a handoff file alone made the item authoritative.

## Session-start rule

When a new session receives a handoff path, the receiving agent must first read only that handoff, then run its stated reconciliation check. It must not treat the handoff as permission to mutate anything. After reconciliation, it should load the project's configured Memory/Adapter and query durable knowledge only when the handoff's `knowledge_entrypoint` or the task requires it.

When the user did not explicitly request durable capture, the next session may use `durable_candidates` as a prompt for review, but must not promote them automatically. A candidate becomes durable only through the project's normal review and authority workflow.
