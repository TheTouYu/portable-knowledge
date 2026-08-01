# PKC Optimization Plan v3

Status: implementation-ready
Updated: 2026-08-01
Supersedes: `docs/OPTIMIZATION-PLAN-v2.md` (kept as historical record)

This is an ordinary plan, not PKC Authority. It does not create Claims,
Authority References, Project Memory, project registry, Bundle, or approval to
change another project. It is drafted from the second Star Cube Nexus feedback
record `docs/FEEDBACK-star-cube-nexus-signal-types-session-2026-08-01.md`
(W7–W12), the unfinished v2 work (WS-A A6 remainder, WS-D, WS-E, WS-F), and
the environment findings from the first implementation pass (test month
hard-coding, stale runtime install).

## 1. Why v3 replaces v2

v2's WS-A (CLI contract surface, F1–F6) is implemented and its evidence gate
was exercised in the first implementation pass: A1–A5 verified live on a
fixture walkthrough, A6 partially (lifecycle_files present; expected_changed_files
documented resolution below). A second real governed-capture session
(2026-08-01) then produced W7–W12: baseline staleness has no recovery path
(N1), revise-claim vs add-claim ref error is misleading (N2), invalidated refs
cannot be enumerated before finalize (N3), and inspect output is empty (N4).
The governance model again held; the friction is again CLI surface plus one
missing non-destructive workflow (rebase).

## 2. Outcome

Unchanged from v2: PKC is a reliable multi-project knowledge collaboration
system with an evidence-driven, staged product loop. This round adds one aim:
an open plan must never dead-end — every error names a remedy, and a stale
baseline is recoverable without replaying operations.

## 3. Evidence inputs

- `docs/FEEDBACK-star-cube-nexus-signal-types-session-2026-08-01.md` — new;
  W7–W12, second real governed-capture session.
- `docs/FEEDBACK-star-cube-nexus-knowledge-plan-cli-friction-2026-07-31.md` —
  F1–F6, tracked in v2 WS-A; W11 completes F2, F1/F4 verified in locked
  runtime.
- First implementation pass findings (this repository, 2026-08-01): A1–A5
  verified; two contract tests fail only because they hard-code the proposal
  shard month `2026-07`; the project `.venv` install predates the WS-A fixes.

## 4. Workstreams

### WS-G: Second-session recovery and inspect surface (new, from W7–W12)

Priority: P0. First implementation round. Bounded to `pkc knowledge-plan`
(`init`, `rebase`, `add-claim`, `add-authority-ref`, `refresh-authority-ref`,
`finalize`, `inspect`) help texts, error messages, one new non-destructive
command, and inspect output. Excludes governance rules, Bundle immutability,
and Authority semantics.

- G1 (W7) `PLAN_STALE_BASELINE` names a remedy, and a new non-destructive
  `knowledge-plan rebase <plan_id> --reason` re-baselines an open plan when no
  plan-referenced Authority path changed between the old baseline and HEAD.
  Conflicting paths are enumerated and rejected. Plan identity (`plan_id`,
  `plan_digest`) is preserved; the rebase is recorded in the plan. `delta` is
  invalidated. Decision gate: rebase is allowed only for `open` plans and only
  when the authority_refs registry plus every ref path referenced by the plan
  is unchanged across the baseline gap — the plan's semantics are baseline
  independent, so moving the pointer is safe. Plan-write files (staged, not
  applied) are untouched.
- G2 (W8) `add-authority-ref` `PLAN_CLAIM_MISSING` distinguishes "no such
  claim id" from "claim was revised, not added — refresh the existing ref with
  `refresh-authority-ref`", pointing at the plan JSON path in both cases.
- G3 (W9) `inspect` closeout preview reports externally invalidated Authority
  Refs (not staged by the plan) in the same `affected_authority_refs` list,
  with `effective_status` and expected/observed hashes, so the full set is
  enumerable before any `finalize` round.
- G4 (W10) `knowledge-plan inspect` gains a summary of claims (id, title,
  fact classes), operations (id, type), revised claims, and staged refs in
  JSON; `--format text` prints the same summary instead of an empty OK line.
- G5 (W11) `--fact-class` allowed values already appear in help and argparse
  validation errors (v2 WS-A A2, commit `3adc0d2`); the feedback session ran
  against an older locked runtime. Add a focused contract test asserting the
  enum is surfaced in `add-claim`/`add-authority-ref` help text, and record the
  runtime re-install requirement in the closeout notes.
- G6 (W12) `docs/QUICKSTART.md` states explicitly: Authority documents must be
  committed before `knowledge-plan init`; commits inside an open plan
  invalidate its baseline (`PLAN_STALE_BASELINE`) and the remedies are
  `knowledge-plan rebase` or abandon + re-init.

Acceptance:

- each G item has a focused contract test;
- a fixture walkthrough of `init → commit → add-claim → PLAN_STALE_BASELINE →
  rebase → continue` completes without reading PKC source or plan JSON;
- `inspect --format text` prints state, baseline, claims, operations, refs;
- exit codes and `ok` fields remain compatible except where a test proves a
  caller cannot exist;
- no change to plan-id determinism for un-rebased plans, Bundle hashes,
  approval/application separation, or Authority gates.

### WS-B closeout: A6 remainder (carried forward from v2)

Priority: P1, after WS-G. v2 A6 has two parts: unify `bundle-inspect` output
shape (done in v2: `lifecycle_files` exposes bundle/approval/applied paths and
tests assert them) and include `*.approval.json` / `*.applied.json` in
`expected_changed_files`. The second part is not implementable as a body field:
`content_hash` covers the body, the bundle_id derives from the hash, and the
lifecycle filenames contain the bundle_id — a circular dependency. Resolved by
documentation: `docs/QUICKSTART.md` states `expected_changed_files` lists
knowledge files only and `bundle-inspect` `lifecycle_files` lists the full
apply/approve artifact set; one test asserts the combination covers every
artifact a successful apply creates.

### WS-D: Adapter maturity (carried forward from v2, unchanged)

Priority: P1, after first-use inputs/evaluation contract stable. Bootstrap
Adapter → reviewed/evaluated Adapter: deterministic tracked proposal after
first-use confirmation, static checks of concrete references only, reviewed
diff before replacing routing, isolated-task evaluation marked evaluated only
when agreed cases pass. Not started; no change planned in this round.

### WS-E: Read-only federation (carried forward from v2, unchanged)

Priority: P1/P2, after ownership/permission contracts are clear. A small
registry of pointers (no copied Claims) with a limited relation vocabulary
(`produces`, `consumed_by`, `verifies`, `documents`, `supersedes`).
Cross-project writes are not permitted in the first version. Not started; no
change planned in this round.

### WS-F: Coverage-gap regression and human-readable Bundle review (carried forward from v2, unchanged)

Priority: P2, after WS-B and relevant project boundary work. Not started; no
change planned in this round.

## 5. Priorities and dependencies

```text
WS-G (P0) → WS-B remainder (P1)
WS-D (P1) after first-use inputs stable
WS-E (P1/P2) after ownership/permission contracts explicit
WS-F (P2) after WS-B and project boundary work
```

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

From v2, still binding: no second Claim store in feedback; no large state
machine before the Markdown protocol proves a need; no telemetry; no
weakening of stale/dirty Authority handling; no registry/federation cache/
remote service/embeddings until a bounded local read-only version fails a
demonstrated requirement; no copying of disposable Adapter treatments.

Added by WS-G: rebase must not change plan identity, must not weaken
exact-hash/committed-baseline gates, and must never make a plan finalizable
without a fresh successful delta check (`delta` is cleared); error-message
improvements must not weaken permission, provenance, or evidence-layer gates;
dry-run stays a dry run.

## 7. Next implementation slice

WS-G pass 1: G1 (rebase + stale-baseline remedy) + G2 (claim-missing
distinction) + G3 (external invalidated refs in preview) + G4 (inspect
summary) + G6 (QUICKSTART authority-before-init). G5 is a contract test only
(the code already landed in v2).

Scope: `semantic_plan.py`, `core.py` text rendering, `tests/`, `docs/QUICKSTART.md`.
No Core semantic changes, no plan-id logic changes, no inspect shape changes
beyond additive fields.

Evidence gate for this slice:

- focused tests assert rebase success/conflict/noop, the claim-missing
  distinction, external invalidated refs in the preview, inspect summary
  fields, and the fact-class enum in help;
- `python3 -m unittest tests.test_semantic_plan_contract tests.test_repository_contract tests.test_feedback_protocol` passes
  (including the month-hard-coding fix);
- one manual walkthrough of a fixture plan (`init` → commit → `add-claim` →
  `PLAN_STALE_BASELINE` → `rebase` → `check` → `inspect --format text`) shows
  no read of PKC source or plan JSON needed;
- `git diff --check` clean.

Stop for review before WS-B remainder and before any WS-D/E/F implementation.
