# PKC Optimization Plan

Status: implementation-ready
Updated: 2026-07-31

This is an ordinary plan, not PKC Authority. It does not create Claims,
Authority References, Project Memory, a project registry, a Bundle, or approval
to change another project. The next implementation round begins with the
smallest slice below and keeps later phases separate.

## 1. Outcome

Make PKC a reliable multi-project knowledge collaboration system whose product
loop is:

```text
project boundary
→ bounded recovery and routing
→ work or feedback
→ evidence-aware validation
→ explicit closeout
→ reusable knowledge or a tracked next action
```

The goal is not to add more Claim machinery. Existing Claim, Authority,
provenance, exact-hash Bundle, stale/dirty fail-closed, and progressive
retrieval semantics are the foundation. The optimization work improves the
workflow around them:

- sessions recover the current task without loading unnecessary context;
- feedback cannot disappear, masquerade as fact, or become silently half-done;
- closeout explains all required phases before a mutation is attempted;
- project Adapters mature through review and evidence rather than inference;
- project boundaries remain explicit when work crosses repositories;
- retrieval gaps can become bounded regression cases;
- humans can understand a Bundle before approving its exact hash.

## 2. Current Baseline

The recovery check was completed before this plan was finalized:

| Repository | Branch | HEAD | Worktree state |
|---|---|---|---|
| PKC repository | `main` | `212f46913452ed9a2032477a66acbac45fcbcd9f` | untracked feedback and plan documents; handoff Skill edited |
| Compiler project | `feat/composite-and-project-knowledge` | `59d57d0947a37cf247289221a4b2f0d20ae42389` | one modified source record and untracked feedback directory |
| Game project | `main` | `0a98f66421e9bf89bdf5c73ec2cbd3db1961fe8b` | clean |
| Personal project | `dev` | `7c093eeef73dd76fbb602a1e5ff542d726cbea47` | clean |

The PKC repository is not configured as its own PKC instance. This plan must
therefore remain ordinary repository documentation. Do not write this plan as
formal knowledge until a separate instance-configuration and governed-capture
decision exists.

The older disposable Adapter treatments and evaluator outputs are evidence,
not patches. They were produced from earlier project commits and must not be
copied into current project Adapters.

## 3. Evidence And Design Conclusions

Confirmed by real project use:

- exact-hash Bundle approval and stale/dirty Authority gates work;
- evidence layers must remain separate between source, automation, editor,
  writeback, and production or in-game verification;
- the main missing value is orchestration and recovery clarity, not a new
  semantic Claim type;
- install-time Bootstrap Adapters exist, but mature project-specific routing
  still needs a reviewed proposal and evaluation path;
- a resumed session can waste context by re-reading evidence already summarized
  in a handoff and can fail to state the round's main task early enough;
- real feedback can be immediately useful, deferred, partially handled, or
  later promoted to knowledge, so those states must remain distinct.

Primary real feedback sources:

- `docs/FEEDBACK-headroom-agent-context-handoff-2026-07-31.md`
- `docs/FEEDBACK-star-cube-nexus-governed-capture-2026-07-31.md`
- the compiler project's feedback document
- the temporary Adapter first-use handoff artifact

## 4. Decisions And Defaults

These defaults are adopted for the plan. They do not require another design
round unless implementation evidence disproves them.

### 4.1 Feedback is a work-control object

Feedback is not a low-confidence Claim. It records a user's input, work items,
processing state, validation state, and links to resulting artifacts. A Claim
is a stable assertion that passed the governed evidence workflow. An Authority
Reference is evidence for a Claim. Feedback may point to all of them, but never
replaces them.

### 4.2 The first feedback implementation is Markdown, not Core/CLI

Use reviewable project-owned Markdown for the first source-only protocol. Do
not add a Core schema, SQLite table, projection, or CLI command until real use
shows that Markdown cannot support the required workflow. This is the smallest
way to validate the lifecycle and avoids creating a second knowledge system.

### 4.3 Handoff is a compact recovery package

A handoff puts the task contract directly at the front: objective, current
state, next action, first read-only check, acceptance criteria, protected
changes, authorization gates, and stop conditions. The receiving agent reads
that package first. Original references are conditional deep dives, read only
for a named missing fact or bounded evidence gap.

### 4.4 Ownership follows the system being improved

Workflow feedback about PKC, handoff, routing, diagnostics, or the Operator
belongs in the PKC repository. Behavior feedback belongs in the project that
owns the behavior. Cross-project work uses source pointers and explicit
relationships; it does not copy facts into a central pool.

### 4.5 Orchestration belongs at the Operator seam first

The Operator owns user-facing orchestration, reports, and proposal workflows.
Core owns deterministic validation and semantic invariants that need reuse by
multiple callers. A new Core abstraction requires a demonstrated second
caller or a contract that cannot be safely implemented at the Operator seam.

### 4.6 Safety gates remain unchanged

No automatic Claim promotion, Authority refresh, Git mutation, external write,
permission broadening, evidence-level promotion, or exact-hash bypass is part
of this plan.

## 5. Phased Roadmap

### Phase 0: Plan and recovery contract

Status: complete for this planning round.

Delivered:

- reconciled the current repository snapshots and protected dirty paths;
- recorded the real-consumer evidence and stale evaluator boundary;
- added the repository-owned `grill-me` and `grilling` Skills;
- replaced the old global Skill directories with links to the repository;
- narrowed the handoff Skill to core-first recovery and evidence-gap reads;
- produced this implementation-ready plan.

The current changes remain ordinary worktree changes. No commit, push, formal
knowledge capture, or project-file modification is implied.

### Phase 1: Recovery and source-only feedback protocol

Priority: P0. First implementation round.

Purpose: make the most common workflow failure observable without adding a
new PKC semantic subsystem.

Scope:

1. Keep the handoff Skill's compact core recovery package as the required
   session-start contract.
2. Add a small reviewable Markdown feedback template or protocol for
   source-only records. Preserve the original report and separate it from
   interpretation, actions, and validation.
3. Record independently:
   - feedback identity and source;
   - affected system or project;
   - observation and user intent;
   - suggested change, if any;
   - processing state: `received`, `in_progress`, `blocked`, `deferred`, or
     `rejected`;
   - validation state: `none`, `local_passed`, `user_pending`, or
     `production_passed`;
   - independent work items and their completion;
   - completed evidence, remaining work, and artifact links;
   - explicit promotion decision, defaulting to not promoted.
4. Use the three existing real feedback documents as examples or regression
   inputs without treating their recommendations as Claims.

Do not add a CLI, Core type, SQLite projection, automatic duplicate detector,
or automatic Claim conversion in this phase. A duplicate or related record may
be linked manually. That is enough to test whether the lifecycle is useful.

Acceptance:

- a new feedback record is created before work starts, including when work is
  expected to happen immediately;
- original feedback is preserved and later interpretation cannot overwrite it;
- partial work is visible as completed and remaining items;
- local success cannot close a record that still needs user or production
  validation;
- deferred and rejected work remains discoverable with a reason;
- a handoff names the round's main task before deeper recovery;
- a matching handoff does not require re-reading its original references;
- a missing fact causes one targeted reference read with a stated reason;
- the protocol changes no Claim, Authority Ref, Memory, Bundle, projection, or
  Git state by itself.

Verification:

- Markdown structure and repository contract checks;
- a small deterministic check or test for required fields and allowed states;
- manual walkthrough using the three real feedback documents;
- `git diff --check` and worktree inspection.

Human gate: implementation may change only the PKC handoff Skill, the
repository-owned feedback protocol/template, and focused tests or docs. Real
consumer feedback must not be rewritten or promoted as part of this phase.

### Phase 2: Closeout preview and diagnostic clarity

Priority: P1. Start after Phase 1 passes.

Purpose: expose the complete governed workflow before the first finalize or
approval attempt, especially when Memory and Authority create commit
boundaries.

Scope:

- a read-only preview of Claim capture, Memory synchronization, Git commit,
  Authority refresh, and final validation phases;
- affected Authority report with path, old/new hash, linked Claim IDs, and a
  human-review reason;
- explicit lifecycle output: `approval_recorded`, `bundle_state`, and
  `bundle_applied`;
- explicit counters for added, refreshed, retired, and affected references;
- health presentation with `PASS`, `PASS_WITH_REVIEW`, and `FAIL` while
  retaining compatible exit codes where required;
- dirty-Authority errors that explain the committed-baseline requirement and
  the safe next steps without running Git commands.

Implementation default: first place the preview/reporting seam in the Operator
if existing Core diagnostics are sufficient. Move deterministic portions into
Core only when they have a reusable contract or a second caller.

Acceptance:

- preview is read-only, creates no Bundle, grants no approval, and makes no
  Git or projection mutation;
- a fixture with a Claim-count Memory dependency reports the full phase chain
  before finalize;
- drift after preview still fails closed during ordinary plan/apply;
- approval output cannot be mistaken for Bundle application;
- pending review cannot be mistaken for fully closed health;
- no automatic Authority refresh or Git commit is introduced.

### Phase 3: Bootstrap Adapter to reviewed/evaluated Adapter

Priority: P1. Start after the first-use inputs and evaluation contract are
stable.

Purpose: turn a generic install artifact into project-specific routing through
explicit review, not business-fact inference.

Scope:

1. Retain deterministic install-time Bootstrap Adapter generation.
2. After first use confirms project goal, next task, committed truth sources,
   privacy boundaries, Memory roles, Contexts, and tree shape, generate a
   tracked Adapter proposal.
3. Statically check only concrete references: Context, Node, Topic, paths,
   fallback files, wrapper path, canonical CLI forms, and permission/safety
   boundaries.
4. Require a reviewed diff before replacing or adding project routing.
5. After real Claims exist, run representative isolated tasks and record
   success, errors, cost/latency where available, and workspace-change status.
   Mark the Adapter evaluated only when the agreed cases pass.

Do not add an Adapter DSL, infer project facts, silently rewrite root Agent
instructions, or copy stale disposable treatments.

Acceptance:

- proposal generation is deterministic and reviewable;
- static failures identify the exact missing or invalid reference;
- runtime and global Skill upgrades do not replace a project Adapter;
- failed or incomplete evaluation is visible as not evaluated;
- no evaluation result is treated as game or production verification.

### Phase 4: Project registry and read-only federation

Priority: P1/P2. Start after project ownership and permission contracts are
clear.

Purpose: make compiler, knowledge, game, and other project boundaries visible
without merging their authority.

Scope:

- each project remains the owner of its own Claims, Authority, Memory, and
  validation commands;
- a small registry records project ID, root/reference, type, readable Contexts,
  writable capabilities, and current evidence boundary;
- explicit read-only relations use a limited initial vocabulary:
  `produces`, `consumed_by`, `verifies`, `documents`, and `supersedes`;
- cross-project results show the owning project, relationship, evidence level,
  timestamp, and permission;
- cross-project reads require explicit project selection or an explicit
  relation traversal.

Implementation default: keep the registry as a read-only index owned by the
knowledge project or an explicitly configured federation file. Store pointers,
not copied Claims. Do not permit cross-project writes in the first version.

Acceptance:

- a query cannot silently combine facts from two projects;
- a relation points to an owning artifact that can be inspected separately;
- unavailable or stale remote/project state is visible;
- project permissions and dangerous operations are shown before any action;
- no project becomes Authority for another project's source files.

### Phase 5: Coverage-gap regression and human-readable Bundle review

Priority: P2. Start after Phases 1, 2, and the relevant project boundary work.

Purpose: close the loop from an important retrieval miss or confusing Bundle to
an explicit, bounded improvement.

Scope:

- preserve coverage gaps as source-only feedback first;
- after triage, convert an important gap into one evaluation case or an
  explicit out-of-scope decision;
- show route/topic candidates and the reason for refusal without claiming
  repository-wide absence;
- add a bounded human-readable Bundle projection containing semantic diff,
  evidence and boundaries, affected paths, permissions, operation counts, and
  the exact content hash;
- keep the exact hash as the only approval credential.

Acceptance:

- each promoted gap has a named evaluation case or a recorded out-of-scope
  decision;
- a passing routing regression proves the intended bounded result, not broad
  absence;
- a reviewer can understand the proposed semantic change without opening the
  full machine manifest;
- changing any Bundle content invalidates approval as before.

## 6. Cross-Phase Metrics

Use small, observable metrics rather than a new telemetry system:

- handoff recovery: first objective stated before deeper inspection;
- redundant reads: references re-read after a matching reconciliation;
- recovery expansion: targeted reads with a stated evidence-gap reason;
- feedback: records with visible next action, partial completion, and validation
  state;
- closeout: phases visible before finalize and lifecycle vocabulary accuracy;
- Adapter: static-check pass rate and isolated task workspace-change rate;
- routing: important gaps with a resulting evaluation case or explicit scope
  decision;
- safety: zero bypasses of exact-hash, committed-baseline, permission, or
  evidence-layer gates.

Measure from bounded tests, reports, and manual review. Do not add background
telemetry or network reporting.

## 7. Dependencies And Gates

Order is intentional:

```text
Phase 0
  → Phase 1 recovery/feedback protocol
  → Phase 2 closeout diagnostics
  → Phase 3 Adapter maturity
  → Phase 4 federation
  → Phase 5 gap regression and Bundle review
```

Phase 3 may begin in parallel with Phase 2 only if its static proposal
contract is independently bounded. Phase 4 must not begin before project
permissions and ownership are explicit. Phase 5 must not change retrieval
ranking and Bundle review in one unmeasured change.

Every phase has two gates:

1. **Implementation gate:** review exact files, scope, tests, and preserved
   invariants before editing.
2. **Evidence gate:** inspect the focused result before starting the next phase.

Human confirmation remains required for tracked project Adapter changes,
formal Authority changes, real-project capture, Git commit/push, external or
game writes, evaluator runs against real project roots, and any new cross-project
write capability.

## 8. Risks And Explicit Exclusions

- Do not turn feedback into a second Claim store. Keep it source-only until
  explicit evidence-backed promotion.
- Do not build a large state machine before the Markdown protocol exposes a
  real need.
- Do not use handoff size as a proxy for quality; measure unnecessary reads and
  recovery errors instead.
- Do not infer production or in-game correctness from tests, compiler output,
  editor import, or isolated model evaluation.
- Do not weaken stale/dirty Authority handling to make closeout shorter.
- Do not modify or inspect unrelated dirty project paths.
- Do not copy old disposable evaluator treatments into current repositories.
- Do not initialize PKC for this repository or write formal Claims without a
  separate explicit decision and the governed workflow.
- Do not add a registry, federation cache, remote service, embeddings, or
  background telemetry until a bounded local read-only version fails to meet a
  demonstrated requirement.

## 9. Next Implementation Round

Start with Phase 1 only.

First read-only checks:

```bash
git status --short --branch
git diff --check
python3 -m unittest tests.test_repository_contract
```

Then inspect only the handoff Skill, the three feedback documents, and the
focused repository contract before editing. Produce the Markdown feedback
protocol/template and its smallest deterministic check. Keep the existing
untracked feedback files and unrelated project changes intact.

The expected Phase 1 result is a reviewable, source-only workflow and a compact
handoff recovery contract. Stop for review before starting Phase 2 or changing
PKC Core, Operator behavior, any project Adapter, Memory, Authority, or Git
state.
