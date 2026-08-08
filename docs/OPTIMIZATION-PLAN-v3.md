# PKC Optimization Plan v3

Status: WS-G, WS-B closeout, WS-D D1-D3, and WS-E E1 implemented; WS-F active
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

### WS-G: Second-session recovery and inspect surface (completed)

Completed in `c9738e4`. Bounded to `pkc knowledge-plan`
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

### WS-D: Adapter maturity (D1-D3 completed)

Completed across `3a63c6b`, `281c15e`, and `af67bf9`. `plan-adapter` creates a
deterministic external `not_evaluated` proposal with concrete-reference static
checks. `apply-adapter` applies only the exact human-reviewed proposal and fails
closed on proposal, Git, configured-path, current-file, or candidate-file hash
drift. `evaluate-adapter` runs only human-confirmed, `cases_hash`-locked isolated
cases against the exact applied Adapter and records cases, results, tool errors,
cost, latency, and workspace changes in a separate evaluation record. It marks
the Adapter evaluated only when every agreed case passes. Synthetic fixtures,
static checks, application success, generic runner success, and one model output
are not real-project, production, game, or compiler evidence.

### WS-E: Read-only federation

Priority: P1/P2. E1 completed in `f5c4853`; its knowledge boundary was recorded in `7270ad6`.

The first real topology is a three-project loop: the game project and compiler
project use PKC for long-term memory and retrieval, while this knowledge project
provides PKC and learns from their feedback and retrieval results. The game may
query compiler knowledge while diagnosing whether a failure is local,
documentation-related, or a compiler defect; the compiler may query game
knowledge for reproduction knowledge during fixes and feature work.

Confirmed v1 contract:

- an explicitly supplied local registry lists allowed PKC project ids, roots,
  fixed read permissions, and evidence boundaries;
- each query explicitly selects one or more registered projects; PKC never
  scans every local repository;
- each project remains the sole owner of its Claims, Authority, Memory,
  validation, and projection;
- results stay grouped by owning project and are not merged or ranked across
  projects;
- the registry stores pointers only, never copied Claims;
- federation uses existing lexical retrieval and never rebuilds a missing
  projection;
- one unavailable project is reported without hiding successful project
  results;
- v1 has no cross-project writes, Git mutation, semantic plans, remote service,
  cache, relation graph traversal, or Context-level filtering.

Implementation slice E1 is the completed `federation-search` only. The earlier relation
vocabulary (`produces`, `consumed_by`, `verifies`, `documents`, `supersedes`)
is deferred until direct project search proves that relation traversal is
needed. Acceptance requires focused registry/scope/permission/partial-result
contracts, grouped JSON/text output, the full test suite, and a fixture
walkthrough proving no target project files or projections are changed.

### WS-F: Coverage-gap regression and human-readable Bundle review

Priority: P2. WS-B and the relevant WS-D/WS-E boundaries are complete. The
minimum slice converts one explicit, reproducible feedback gap into a
deterministic evaluation-case proposal outside the target project and adds a
bounded human-readable Bundle projection. It does not write project evaluation
cases, modify Claims, Authority, Memory, Adapter, runtime, or retrieval ranking,
or run an evaluator. A proposal hash is only a review aid; the exact Bundle
`content_hash` remains the only Bundle approval credential. Synthetic fixture
evidence proves mechanism only.

## 5. Priorities and dependencies

```text
WS-G complete → WS-B closeout complete
WS-D D1-D3 complete
WS-E E1 complete; relation traversal deferred
WS-F minimum proposal/review slice active
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

WS-F minimum slice: `propose-evaluation-case` turns one schema-version-1 feedback
gap into deterministic JSON and human-readable review files outside the target
project. `bundle-inspect --format text` displays semantic diff, evidence and
Authority references, permission effect, risk, operation counts, affected
paths, lifecycle state, and the exact Bundle content hash.

Scope: Operator script/mode contract, additive Bundle inspect fields/text, focused
tests, and this ordinary plan. No project evaluation-case write, Claim,
Authority, Memory, Adapter, runtime, retrieval-ranking, UI, DSL, database,
cache, telemetry, dependency, evaluator, commit, or push change.

Evidence gate:

- focused tests prove deterministic proposal hashes, changed-input hash drift,
  bounded assertions, external-only outputs, `not_evaluated`, zero target
  project writes, synthetic evidence labeling, and exact-hash Bundle review;
- the full test suite passes;
- a fully `/tmp` synthetic fixture walkthrough proves mechanism and target
  project immutability, not real-project retrieval correctness;
- `git diff --check` is clean.
