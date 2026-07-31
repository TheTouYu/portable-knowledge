# PKC Optimization Plan v2

Status: implementation-ready
Updated: 2026-07-31
Supersedes: `docs/OPTIMIZATION-PLAN.md` (obsolete; kept as historical record)

This is an ordinary plan, not PKC Authority. It does not create Claims,
Authority References, Project Memory, project registry, Bundle, or approval to
change another project. It was drafted from the CLI-friction feedback record
`docs/FEEDBACK-star-cube-nexus-knowledge-plan-cli-friction-2026-07-31.md` plus
the unfinished work of the v1 plan. The feedback record itself is evidence
input; it is not rewritten or promoted here.

## 1. Why v2 replaces v1

v1 covered workflow protocol (recovery, feedback, closeout preview, Adapters,
federation, gap regression). It did not cover CLI contract friction, which a
real governed-capture session (Star Cube Nexus, 2026-07-31) then produced:
six work items W1–W6 about help texts, error messages, dry-run signaling, and
inspect output shape. The governance model itself (exact-hash approval,
committed-baseline Authority, dirty-path rejection) worked and stays intact;
the friction is in how the CLI surfaces its own contract.

v2 merges W1–W6 as a new first-priority workstream (WS-A) and carries every
still-unfinished v1 direction forward. Completed v1 work is not re-planned.

## 2. Outcome

Unchanged from v1: PKC is a reliable multi-project knowledge collaboration
system with an evidence-driven, staged product loop:

```text
project boundary → bounded recovery routing → work feedback → evidence-aware validation → explicit closeout → reusable knowledge or tracked next action
```

The goal is not more Claim machinery. Optimization improves the workflow
around existing Claim, Authority, provenance, exact-hash Bundle, and
stale/dirty fail-closed semantics. WS-A adds one concrete aim: a governed
capture session should not require reading PKC source or plan JSON internals
to use the CLI.

## 3. Evidence inputs

- `docs/FEEDBACK-star-cube-nexus-knowledge-plan-cli-friction-2026-07-31.md` —
  new; WS-A work items W1–W6; also real-project evidence for the Phase 1
  feedback protocol (a second governed-capture session recorded through it).
- `docs/FEEDBACK-star-cube-nexus-governed-capture-2026-07-31.md` — earlier;
  multi-Bundle orchestration, complementary.
- `docs/FEEDBACK-headroom-agent-context-handoff-2026-07-31.md` — earlier.
- Compiler project's feedback document (external to this repository).
- Temporary Adapter first-use handoff artifact (evidence, not a patch).

## 4. Workstreams

### WS-A: CLI contract surface (new, from feedback W1–W6)

Priority: P0. First implementation round. Bounded to `pkc knowledge-plan`
(`add-claim`, `add-authority-ref`, `check`, `init`, `inspect`, `abandon`),
`bundle-approve`, `bundle-apply`, `bundle-inspect`: help texts, error messages,
dry-run signaling, and inspect output shape. Excludes governance rules,
Bundle immutability, and Authority semantics.

Classification of the work items (interpretation; the feedback record remains
the verbatim source):

- A1 (W1) Unmistakable dry runs. `bundle-approve`/`bundle-apply` in dry-run
  mode must print an explicit "DRY RUN, nothing written" line; do not change
  `ok` semantics or exit codes in a way that breaks existing callers unless a
  distinct field/code is additive. Highest severity: a dry run was mistaken
  for a recorded approval (F1).
- A2 (W2) `--fact-class` enum must appear in `add-claim --help` and in the
  validation error. The enum is already a fixed source constant; surface it,
  do not move it.
- A3 (W4) Accepted `--mode` values must appear in `knowledge-plan check
  --help`.
- A4 (W3) `planned claim not found` must name the plan JSON path
  (`.local/pkc/semantic-plans/<plan_id>.json`) and where ids are listed;
  `add-claim` success output should print the generated claim id.
- A5 (W5) `init` with the same intent after `abandon` must never silently
  return the abandoned plan. Default: fail with an explicit message naming the
  abandoned plan id. (Open alternative: create a fresh plan id. Decision gate
  before implementation.)
- A6 (W6) Unify `bundle-inspect` output shape with `knowledge-plan inspect`
  or document the nesting, and include `*.approval.json` / `*.applied.json`
  in `expected_changed_files`. Additive field changes first; shape changes
  need a compatibility decision.

Placement default: help and error text live in the CLI layer; `docs/QUICKSTART.md`
is updated only where a doc pointer is the actual fix (e.g., the plan JSON
path hint in A4). Do not build a DSL or new Core subsystem for any of this.

Acceptance:

- each A item has a focused contract test (help text, error text, dry-run
  output, expected_changed_files content);
- dry-run output is visibly distinct from a recorded approval;
- all help/error enums match the source enum by construction, not by copy;
- a manual walkthrough of one fixture plan exercises every touched command
  and shows no read of source code needed;
- exit codes and `ok` fields remain compatible except where a test proves a
  caller cannot exist;
- no change to plan-id determinism, Bundle hashes, approval/application
  separation, or Authority gates.

### WS-B: Phase 2 closeout diagnostics (carried forward from v1)

Priority: P1, after WS-A's first evidence gate. Remaining v1 acceptance work:

- preview a fixture with a Claim-count Memory dependency;
- affected Authority report: path, old/new hash, linked Claim IDs,
  human-review reason;
- explicit added/refreshed/retired/affected Authority Reference counters;
- `PASS` / `PASS_WITH_REVIEW` / `FAIL` health presentation, compatible exit
  codes;
- dirty-Authority diagnostics with committed-baseline requirement and safe
  next steps;
- verify drift after preview still fails closed;
- keep approval distinct from application; no automatic Authority refresh or
  Git commit.

Not re-planned (completed): `knowledge-plan inspect` lifecycle facts
(`approval_recorded`, `bundle_state`, `bundle_applied`), the read-only
five-phase `closeout_preview`, and their tests.

### WS-C: Phase 1 protocol evidence review (carried forward from v1)

Priority: P1. The feedback protocol implementation is complete; its
real-project/manual evidence review remains separate. The two Star Cube Nexus
feedback records (governed-capture, CLI-friction) are the first real-use
inputs. Remaining: a manual walkthrough of the protocol against the real
records (including this CLI-friction record), `git diff --check`, and a
repository contract check. Do not rewrite or promote the feedback records.

### WS-D: Adapter maturity (carried forward from v1, unchanged)

Priority: P1. Bootstrap Adapter → reviewed/evaluated Adapter: deterministic
tracked proposal after first-use confirmation, static checks of concrete
references only, reviewed diff before replacing routing, isolated-task
evaluation marked evaluated only when agreed cases pass. No Adapter DSL, no
project-fact inference, no silent root Agent rewrite, no copy of stale
disposable treatments.

### WS-E: Read-only federation (carried forward from v1, unchanged)

Priority: P1/P2, after ownership/permission contracts are clear. Each project
owns its Claims, Authority, Memory, validation. A small registry of pointers
(no copied Claims) with a limited relation vocabulary (`produces`,
`consumed_by`, `verifies`, `documents`, `supersedes`). Cross-project writes
are not permitted in the first version.

### WS-F: Coverage-gap regression and human-readable Bundle review (carried forward from v1)

Priority: P2, after WS-B and relevant project boundary work. Preserve gaps as
source-only feedback first; convert important gaps into one evaluation case or
an explicit out-of-scope decision; bounded human-readable Bundle projection
with exact content hash as the only approval credential. WS-A's A6 is the
first small step toward the human-readable inspect side of this.

## 5. Priorities and dependencies

```text
WS-A (P0) → WS-B (P1) → WS-F (P2)
WS-C (P1, parallel with WS-A/B)
WS-D (P1) after first-use inputs/evaluation contract stable
WS-E (P1/P2) after ownership/permission contracts explicit
```

- A1–A4 first, A5–A6 after A1–A4's evidence gate: A5 carries a semantic
  decision and A6 carries output-shape compatibility risk; do not bundle them
  with pure help/error fixes.
- WS-B does not start before the WS-A evidence gate passes.
- WS-C can absorb the new feedback record as a walkthrough input at any time.
- WS-F must not change retrieval ranking and Bundle review in one unmeasured
  change.

Every workstream has two gates:

1. **Implementation gate:** review exact files, scope, tests, and preserved
   invariants before editing.
2. **Evidence gate:** inspect the focused result (tests + one manual
   walkthrough) before starting the next workstream.

Human confirmation remains required for tracked project Adapter changes,
formal Authority changes, real-project capture, Git commit/push, external or
game writes, evaluator runs against real project roots, and any new
cross-project write capability.

## 6. Exclusions and invariants

From v1, still binding: no second Claim store in feedback; no large state
machine before the Markdown protocol proves a need; no telemetry; no
weakening of stale/dirty Authority handling; no registry/federation cache/
remote service/embeddings until a bounded local read-only version fails a
demonstrated requirement; no initialization of this repository as its own PKC
instance without a separate explicit decision; no copying of disposable
Adapter treatments.

Added by the new feedback (WS-A): help-text and error-message improvements
must not weaken exact-hash, committed-baseline, permission, or evidence-layer
gates; dry-run must stay a dry run; plan-id determinism is a feature, not a
bug — the fix is signaling, not regeneration.

## 7. Next implementation slice

WS-A pass 1: A1 (dry-run unmistakable) + A2 (`--fact-class` enum) + A3
(`--mode` enum). These are pure CLI surface with no semantic decision and no
output-shape risk, and they directly serve the feedback's intent (a smoother
next capture session).

Scope: `bundle-approve`/`bundle-apply` dry-run output, `add-claim` and
`knowledge-plan check` help/error text, focused contract tests, QUICKSTART
only where a pointer is the fix. No Core semantic changes, no plan-id logic,
no inspect shape changes.

Evidence gate for this slice (do not start A4–A6 or WS-B until it passes):

- focused tests assert the dry-run line, the enum values in help and error
  text, and that exit codes / `ok` fields remain compatible;
- `python3 -m unittest tests.test_semantic_plan_contract tests.test_repository_contract tests.test_feedback_protocol` passes;
- one manual walkthrough of a fixture plan (`init` → `add-claim` →
  `knowledge-plan check --mode delta` → `bundle-approve` dry run →
  `bundle-apply` dry run) completes without reading PKC source or plan JSON;
- `git diff --check` clean.

Stop for review before A5 (needs the init-after-abandon decision) and A6
(needs the output-shape compatibility decision).
