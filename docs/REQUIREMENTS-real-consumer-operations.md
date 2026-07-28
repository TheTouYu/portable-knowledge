# Requirements: reduce real-project PKC maintenance friction without weakening governance

Status: proposed

Reported: 2026-07-28

Real consumer: an anonymized configured PKC project using a project-locked, non-editable runtime

Observed upgrade: `portable-knowledge 0.2.0rc1` at commit
`f4b8c98d150361144087374467e4800673d14bd0` to `0.2.0rc5` at commit
`3d772a129ff222125f163cc1c717fafe45d41be9`

Priority: mixed — P0/P1 operational improvements for the next Operator/Core iteration

## Summary

A real anonymized consumer-project maintenance session completed a source-code change, real-environment
validation, governed knowledge revision, Authority Reference lifecycle maintenance, exact-hash
Bundle approval/application, and a separate Git commit. The governance model worked: dirty
Authority was rejected, stale Authority blocked finalization, no formal authority changed before
approval, the exact approved Bundle was applied transactionally, and post-apply validation passed.

The session also exposed avoidable operational friction. The largest remaining gap is that the
Operator documents an upgrade mode but does not implement `plan-upgrade`; a configured locked
project therefore required a carefully performed manual exact-commit build and runtime switch.
Full staged preflight also discovered non-current Authority References only after the plan's delta
check, requiring repeated diagnosis and plan amendments. Canonical one-line Bundle JSON and broad
registry reserialization made the eventual Git diff harder to review than the semantic change.

This document proposes product requirements that preserve the existing fail-closed model while
making upgrades, preflight repair, human review, and interrupted-plan recovery deterministic and
practical.

## Real-consumer outcome

The consumer ultimately produced and applied one governed high-risk plan:

```text
plan operations: 13
Claims created: 3
Claims revised: 1
Authority References added: 3
Authority References refreshed: 6
Authority References retired: 0
expected authority files changed: 6
post-apply Claims: 31
post-apply events: 22
```

The immutable Bundle was approved and applied by exact 64-character content hash. Independent
`rebuild`, `validate`, representative L2 queries, Claim inspection, Authority status inspection,
and `git diff --check` passed. The runtime upgrade and formal knowledge application were reviewed
as separate risk operations, and Git commit/push remained separate authorization boundaries.

The successful result is evidence that the current governance design is viable. The requirements
below target operator effort and review quality, not weaker safety.

## Already resolved in `0.2.0rc5`

These items were blockers in the original locked `0.2.0rc1` runtime but are not open requirements:

- governed `knowledge-plan revise-claim`;
- governed `knowledge-plan refresh-authority-ref`;
- governed `knowledge-plan retire-authority-ref`;
- structured full-preflight Authority diagnostics instead of `ok:false` with `errors:[]`;
- explicit delta rejection of an Authority path modified by the same staged plan.

Regression coverage for these capabilities must remain. They form the minimum complete lifecycle
for maintaining committed Authority after ordinary source evolution.

## Governance invariants

Every requirement in this document must preserve the following behavior:

- Git-owned text remains authority; `.local/` and SQLite remain disposable projections.
- Working-tree-only observations cannot become stable Authority.
- Authority paths and approved hashes remain bound to an exact committed baseline.
- Runtime upgrades resolve an exact source commit and verified wheel SHA-256.
- The known-good runtime remains available until the new runtime passes validation.
- Delta/full validation, permission, lifecycle, provenance, and fact-class coverage remain
  fail-closed.
- Formal authority changes only through a typed immutable Bundle.
- Human approval applies only to the displayed exact Bundle content hash.
- Runtime/configuration changes, formal authority application, and Git/remote operations retain
  separate review boundaries.
- Compatibility mode, direct authority edits, editable installs, source-checkout `PYTHONPATH`, and
  low-level manifests are not normal recovery mechanisms.

## R1 — Implement a first-class exact-commit Operator upgrade transaction

Priority: P0

The Operator currently exposes `check-update`, `plan-install`, `plan-adopt`, and `apply-plan`, while
its contract describes an upgrade workflow without providing `plan-upgrade`. A configured project
cannot use install/adopt as an undocumented substitute for upgrade.

Add a mechanical interface equivalent to:

```bash
python scripts/pkc_operator.py plan-upgrade \
  --target /path/to/project \
  --source-repository /path/or/url/to/portable-knowledge \
  --source-commit EXACT_COMMIT \
  --output /tmp/pkc-upgrade-plan.json

python scripts/pkc_operator.py apply-plan \
  --plan /tmp/pkc-upgrade-plan.json \
  --plan-hash EXACT_PLAN_HASH \
  --human-reviewed
```

`plan-upgrade` must be read-only with respect to the target project. Its review payload must include:

- current and target PKC versions;
- current and target exact source commits;
- source repository identity;
- wheel filename and SHA-256;
- Python executable and ABI used to build and install;
- wheel cache path and proposed parallel runtime path;
- current rollback runtime path;
- exact tracked files and before/after hashes, normally including `tools/pkc-lock.json` only;
- compatibility/capability difference;
- planned post-switch checks;
- whether any target worktree path is already dirty;
- a deterministic plan hash.

Apply must fail closed if the source commit, wheel, target files, environment assumptions, or plan
hash drift. It must install non-editably into a parallel runtime, switch only the reviewed lock or
wrapper files, preserve the old runtime, and run capabilities, module-origin verification,
`validate`, `rebuild`, a second `validate`, configured representative queries, and configured
project tests. A failed check must leave or restore the prior canonical runtime selection and emit
an actionable rollback receipt.

### R1 acceptance criteria

1. A configured locked fixture can upgrade through `plan-upgrade` plus reviewed `apply-plan` without
   using install/adopt or manually editing its lock.
2. Planning makes no target-project changes and records an exact plan hash.
3. The target source checkout may be dirty, but the wheel contains only the requested committed Git
   object; uncommitted source bytes are excluded and reported.
4. A wheel/hash/file/environment drift test fails before switching the canonical runtime.
5. A post-switch validation failure restores the old selection and preserves both runtimes for
   diagnosis.
6. The resulting project wrapper imports only from the target parallel runtime, with no
   `PYTHONPATH` or system fallback.
7. Linux/Pi receives real-environment coverage first; other platform labels remain bounded until
   separately validated.

## R2 — Provide a reproducible exact-commit wheel builder with environment preflight

Priority: P0

The real upgrade first selected `/usr/sbin/python`, which had no `pip`, and failed with:

```text
/usr/sbin/python: No module named pip
```

The eventual build succeeded from the exact committed Git object without modifying the PKC source
worktree. This should be a supported mechanical path rather than operator improvisation.

The builder used by install/adopt/upgrade must:

- discover or accept an explicit Python `>=3.11` interpreter;
- report interpreter path, version, ABI, and availability of `venv`, `pip`, `build`, or `uv` before
  starting;
- prefer an isolated disposable build environment;
- build from a clean export of the exact Git commit, not directly from a possibly dirty checkout;
- avoid installing build tools into the consuming project runtime;
- verify wheel metadata name/version and importable package version;
- calculate and record SHA-256;
- cache by source identity, exact commit, Python/build compatibility, and wheel hash;
- never silently reuse a cache entry whose provenance cannot be verified.

A local source repository must be supported so maintainers can upgrade from an already reviewed
checkout without waiting for a remote release. Signed/tagged release wheels may remain preferred
when available.

### R2 acceptance criteria

1. A dirty source checkout and its clean `HEAD` produce the same committed-source wheel as a clean
   clone at that commit.
2. A missing build frontend produces one actionable environment finding before target changes.
3. Tests cover `uv`, `venv` plus pip/build where available, and a no-usable-builder outcome.
4. Wheel metadata, module version, source commit, and SHA-256 appear in one provenance record.
5. No build dependency leaks into the final project runtime unless it is a declared runtime
   dependency.

## R3 — Add a full Authority-closure preview before finalization

Priority: P1

A complete plan passed delta, but full staged preflight then identified three non-current existing
Authority References. After those were reviewed and added as refresh operations, additional
historical non-current References were exposed. The full check correctly blocked unsafe
finalization, but repair required multiple diagnose/amend/check cycles.

Keep the current touched-operation delta mode, but add an explicit read-only preview that computes
the same Authority closure used by finalize without consuming the one allowed finalization budget
or creating a candidate Bundle. For example:

```bash
pkc knowledge-plan check PLAN_ID --mode full-preview
```

The preview must return all currently known blockers in one deterministic response, including:

- Authority Reference ID and path;
- expected and observed hashes where safe;
- baseline, worktree, staged, and effective status;
- affected Claim IDs;
- whether the path is touched by the current plan;
- why the Ref entered the closure;
- allowed next operations such as review-and-refresh or review-and-retire;
- an explicit warning that refresh is a semantic human judgment, not an automatic fix.

This preview must not auto-refresh, auto-retire, create a Bundle, write authority, or replace the
final full staged preflight. Finalize must rerun authoritative checks against current state.

### R3 acceptance criteria

1. A fixture with six independently stale Refs reports all six in one preview.
2. Preview does not increment candidate-Bundle or full-preflight counters and changes no files.
3. Findings identify the dependency chain from changed source to Ref to affected Claims.
4. Adding reviewed lifecycle operations and rerunning preview produces a clean result.
5. State drift after preview is still caught by finalize.
6. Existing fast delta behavior and budgets remain unchanged.

## R4 — Produce a human-review manifest alongside canonical Bundle bytes

Priority: P1

Canonical Bundle JSON is intentionally deterministic and compact, but a large one-line file is hard
to review in Git. Human approval currently depends on separately reconstructing the semantic diff
from CLI output.

Preserve canonical immutable Bundle bytes and content-hash semantics. Add either a deterministic
review artifact or a richer bounded inspect command that can be saved verbatim. The preferred
tracked form is:

```text
data/knowledge/bundles/BUNDLE_ID.json       # canonical machine payload
data/knowledge/bundles/BUNDLE_ID.review.md # deterministic human review projection
```

The review projection must display:

- Bundle ID and full content hash;
- intent, risk, permission effect, and baseline commit;
- Claims created/revised with IDs and bounded before/after summaries;
- Authority References added/refreshed/retired;
- old/new approved hashes and affected Claim IDs for lifecycle operations;
- expected changed files;
- validation/preflight receipt identity;
- explicit exclusions and unresolved claims when supplied by the plan;
- a statement that the Markdown projection is not the hashed authority payload.

Approval must continue to require the canonical exact content hash. Regenerating a review projection
must never change Bundle identity.

### R4 acceptance criteria

1. Two machines produce byte-identical review projections for the same Bundle.
2. The projection clearly distinguishes canonical payload hash from ordinary file SHA-256.
3. Tampering with canonical bytes invalidates approval/apply as today.
4. Tampering with a tracked review projection is detected by validation or deterministic rebuild.
5. A reviewer can identify every Claim and Authority lifecycle change without opening compact JSON.
6. Existing consumers that store only canonical JSON remain compatible.

## R5 — Minimize semantic-registry diff noise

Priority: P1

Refreshing six Authority References caused hundreds of changed lines in the Authority registry,
well beyond the number of semantic fields changed. Deterministic output is necessary, but broad
reserialization raises review cost and obscures meaningful old/new hashes.

Define and enforce a canonical stable serialization policy for Git-owned registries:

- stable object-key ordering;
- stable array ordering based on documented identity keys;
- stable indentation and trailing newline;
- normalization performed explicitly and reported, not incidentally on an unrelated operation;
- no reorder-only changes after a registry is already canonical;
- lifecycle history appended to its event store without rewriting unrelated events.

If a legacy registry must be normalized, expose that as a distinct expected change in the plan and
review manifest. Do not hide schema migration inside an Authority refresh.

### R5 acceptance criteria

1. Refreshing one Ref in a canonical registry changes only that Ref's current representation and the
   required append-only lifecycle event.
2. Refreshing multiple Refs preserves unrelated Ref byte order and formatting.
3. A legacy alias/key normalization is reported as a schema-normalization action.
4. Apply/rebuild/apply-idempotence tests prove a canonical registry does not churn.
5. Content hashes and current Authority observations remain unchanged by formatting alone.

## R6 — Support safe reuse of an abandoned or obsolete semantic plan

Priority: P2

The consumer abandoned several plans because its locked runtime could not express required Claim
and Authority lifecycle operations. After upgrade, already reviewed Claim wording had to be
recovered manually from an abandoned plan and re-entered into a new plan.

Add a governed planning convenience such as:

```bash
pkc knowledge-plan fork OLD_PLAN_ID --baseline CURRENT_COMMIT
```

or an equivalent export/import operation. It must copy only typed semantic intent into a new open
plan and must not inherit:

- old baseline hashes;
- delta/full receipts;
- candidate Bundles;
- approval or application state;
- counters that belong to the old execution;
- stale observed Authority state.

Every copied operation must be revalidated against the new committed baseline. Unsupported or
conflicting operations must be reported individually, and the old plan must remain immutable and
inspectable.

### R6 acceptance criteria

1. Forking an abandoned plan creates a new plan ID with explicit provenance to the source plan.
2. No approval, receipt, Bundle, or old Authority hash is treated as current.
3. Compatible Claim wording and typed metadata are preserved exactly.
4. Changed/removed paths and now-duplicate Claims become structured findings.
5. The new plan must pass ordinary delta and full preflight before finalization.

## R7 — Bound repository scans and diagnose broken symlinks precisely

Priority: P2

A tracked broken, machine-specific symlink outside the configured knowledge domain blocked an
otherwise unrelated `knowledge-plan add-claim`. The fail-closed result prevented hidden input
substitution, but the relevance and remediation path were not obvious.

Repository inspection should follow configured Authority and operation scope. When a symlink is
encountered, diagnostics must distinguish:

- a configured Authority or prospective-write path, which may block;
- a configured knowledge/Memory path, which may block according to policy;
- an unrelated tracked path, which should normally warn rather than block;
- an explicitly excluded path;
- a link escaping the repository or resolving to a missing target.

No command may guess, recreate, delete, or retarget a broken link. Remediation remains a separate
human-reviewed repository operation.

### R7 acceptance criteria

1. An unrelated broken symlink does not block a bounded semantic operation unless a documented
   repository-integrity policy requires it.
2. A broken Authority path fails closed with path, raw target, resolved target, operation phase, and
   reason for relevance.
3. A prospective write through a symlink receives explicit containment checks.
4. Tests cover internal, external, missing, excluded, and operation-relevant links.
5. No diagnostic command mutates or repairs a symlink.

## R8 — Make permission and projection diagnostics consistent across retrieval commands

Priority: P2

During post-apply verification, representative L2 queries returned newly created internal Claims,
while an exact Claim lookup temporarily returned `claim not found`; subsequent explicit internal
inspection succeeded. The session did not isolate a reproducible Core defect, so this is a
requirement for diagnostic clarity and consistency rather than a confirmed permission bug.

All retrieval commands should expose the effective permission scope and projection identity in
machine-readable diagnostics. `query` and `show-claim` defaults must remain aligned. When safe under
the configured disclosure policy, distinguish:

- syntactically invalid ID;
- Claim absent from the current projection;
- projection stale or missing;
- Claim filtered by permission/lifecycle;
- Claim present and available.

Where non-disclosure requires `not found`, return a non-sensitive reason category or remediation
hint suitable for an authorized local operator without revealing restricted content.

### R8 acceptance criteria

1. CLI parser tests prove aligned default permission for query and exact lookup.
2. JSON output reports effective permission and projection generation/authority fingerprint.
3. A stale projection produces an actionable rebuild diagnostic rather than an ambiguous absence.
4. Non-disclosure tests prove restricted Claim existence is not leaked to unauthorized callers.
5. Authorized local-operator tests can distinguish projection failure from permission filtering.

## Suggested delivery order

### Milestone 1 — upgrade closure

Deliver R1 and R2 together. This removes the largest manual and highest-risk operational gap:
switching a configured project from one exact locked runtime to another.

### Milestone 2 — preflight and review quality

Deliver R3, R4, and R5. These reduce the number of repair iterations and make exact-hash human
review materially easier without changing approval semantics.

### Milestone 3 — recovery and diagnostics

Deliver R6, R7, and R8. These improve interrupted workflows and edge-case diagnosis after the core
upgrade and review paths are reliable.

## End-to-end acceptance scenario

Create a committed configured fixture locked to an older PKC runtime. The fixture contains:

- a canonical Authority registry;
- several change-sensitive Authority References, including multiple stale Refs;
- one unrelated broken external symlink;
- an abandoned semantic plan with reusable typed Claim wording;
- representative retrieval evaluation cases.

Then verify:

1. `check-update` identifies a newer commit but changes nothing.
2. `plan-upgrade` builds or resolves a wheel from an exact commit and returns a complete reviewed
   plan with source/wheel/runtime/lock/rollback identities.
3. Reviewed apply installs a parallel runtime, switches the lock, and passes origin, capability,
   rebuild, validate, query, and project checks while retaining rollback.
4. A new plan forked from the abandoned plan revalidates all operations against the current
   baseline without inheriting approval or receipts.
5. Full Authority preview reports every stale Ref at once and explains the Claim dependency chain.
6. After explicit review, typed refresh/retire operations make preview clean.
7. Finalize creates one canonical Bundle and deterministic human review projection.
8. Exact-hash approval/application changes only expected authority paths, produces a successful
   post-apply receipt, and keeps the unrelated broken symlink untouched.
9. Rebuild, validate, representative query, exact Claim inspection, lifecycle inspection, and Git
   diff checks pass.
10. No commit, push, publication, or old-runtime deletion occurs without its own authorization.

## Out of scope

- Weakening committed-baseline or clean-Authority requirements.
- Automatically deciding whether a stale Ref should be refreshed or retired.
- Automatically approving or applying a Bundle after successful validation.
- Combining runtime upgrade, knowledge application, Git commit, and push into one implicit consent.
- Treating source implementation as proof of external-environment behavior.
- Reconstructing missing machine-specific paths or symlink targets.
- Replacing canonical Bundle content hashing with a human-readable file hash.
- Claiming cross-platform support without corresponding real-environment evidence.

## Success measures

After implementation, repeat the same class of real-project maintenance and measure:

- one reviewed upgrade plan instead of manual runtime construction;
- one Authority-closure preview instead of iterative stale-Ref discovery;
- zero direct authority or lock edits outside reviewed transactions;
- a materially smaller semantic-registry Git diff;
- a review artifact that exposes every Claim and Authority lifecycle change;
- successful rollback simulation;
- successful exact-hash Bundle approval/application;
- no regression in dirty-Authority rejection, full preflight, permission filtering, provenance,
  transaction rollback, or post-apply validation.

The target is not fewer safety gates. The target is that each gate has one supported operation,
one complete diagnostic, and one reviewable artifact.

## Skill-level assessment and requirements

The two project-provided Skills used around this workflow are fundamentally useful and should be
kept. They provide the correct separation of responsibilities:

- `pkc-project-operator` routes human-facing installation, maintenance, upgrade, approval, and
  Git-risk decisions while delegating semantic correctness to the installed Core;
- `isolated-model-evaluator` tests whether a fresh model can understand and execute a documented
  workflow without hidden conversation context.

The real session did not expose a need to replace either Skill. It exposed a smaller maintenance
problem: the Skill contracts should stay synchronized with the mechanical interfaces and should
make the cost/benefit of evaluation explicit.

### R9 — Keep `pkc-project-operator` contract and implementation synchronized

Priority: P1

The Operator Skill already declares an `upgrade` mode and describes an exact-commit parallel
runtime switch, but the current mechanical CLI exposes `check-update`, `plan-install`, and
`plan-adopt` rather than a first-class `plan-upgrade`. This is the same real-consumer gap described
in R1, viewed from the model-facing contract. A fresh model can correctly follow the Skill's safety
principles and still have no supported command for the configured-project upgrade it was asked to
perform.

When R1 is implemented, the Skill and its mode reference must be updated in the same change so that:

- the canonical command examples use the real `plan-upgrade` interface;
- install, adopt, repair, and upgrade are explicitly distinguished;
- the upgrade mode names its plan hash, lock diff, wheel hash, parallel runtime, rollback path,
  and post-switch checks;
- the Skill does not imply that `plan-install` or `plan-adopt` is an upgrade substitute;
- unsupported platform or Agent claims remain marked `designed` or `unsupported` until real
  evidence exists;
- the temporary recovery path for older runtimes is documented only as a bounded migration note,
  never as an alternate governance bypass.

The Skill should also surface Core diagnostics using the same vocabulary as the CLI. For example,
`PLAN_AUTHORITY_STAGED_DRIFT`, non-current Authority status, projection staleness, and permission
filtering should be named consistently in operator guidance and final reports.

#### R9 acceptance criteria

1. A fresh model reading only the Operator Skill can choose the correct command family for install,
   adopt, upgrade, maintenance, and approval without guessing.
2. Every command shown as canonical in the Skill exists in the released Operator interface, or is
   explicitly marked planned and not executable.
3. A documentation/CLI contract test extracts or checks the critical command names and risk gates.
4. The Skill's upgrade instructions produce the same exact-commit, wheel-hash, rollback, and
   post-check behavior as the implementation.
5. A fresh model reports a permission-filtered Claim as unavailable at the current scope rather than
   treating it as repository-wide absence.
6. No Skill revision weakens the human review gates or delegates semantic decisions to the model.

### R10 — Make isolated evaluation a targeted usability tool, not a default maintenance step

Priority: P2

`isolated-model-evaluator` is well suited to validating whether a new Skill, CLI contract, or
workflow is discoverable from a fresh context. It is not necessary for every ordinary knowledge
Bundle maintenance operation. The real session was completed through bounded project routing and
PKC validation; running a fresh-model evaluation would have added cost without being required to
approve or apply the Bundle.

The Skill should make the evaluation decision explicit. Recommend an isolated evaluation when at
least one of the following is true:

- a Skill or operator contract has changed;
- a CLI command, permission default, refusal boundary, or lifecycle workflow has changed;
- a documentation change is intended to reduce model guessing or tool errors;
- a new project Adapter or routing Context is being introduced;
- before/after model usability is an explicit acceptance criterion.

Do not recommend it solely because a normal Claim, Authority refresh, real-map validation, or
already documented Bundle application occurred. A real environment result and a fresh-model
usability result are different evidence layers and should not be merged.

Add an optional lightweight smoke mode for Skill/contract iteration that keeps the existing full
trace/report contract but supports:

- one bounded read-only task;
- fixed provider/model/thinking settings;
- `--assert-no-changes` by default;
- an external task-specific oracle for correctness;
- a short summary of first tool error, undocumented command recovery, unnecessary file reads,
  final answer presence, and workspace changes;
- no automatic claim, evidence, Bundle, commit, or push mutation.

The existing evaluator safety defaults and trace/report separation remain authoritative. A smoke
mode is a convenience for deciding whether a full evaluation is warranted, not a replacement for
the full evaluator when correctness or performance comparisons matter.

#### R10 acceptance criteria

1. The Skill documents clear positive triggers and non-triggers for running an isolated evaluation.
2. A read-only smoke task leaves the project unchanged and reports tool errors and final-answer
   presence.
3. Full evaluation and smoke evaluation use the same isolation boundaries and cannot approve/apply
   knowledge or mutate Git.
4. Documentation iteration can compare a fixed task before and after without changing provider,
   model, thinking level, fixture, or oracle.
5. Reports distinguish model usability evidence from project semantic, runtime, and external-
   environment evidence.

### Skill optimization boundary

No immediate wholesale rewrite of either Skill is justified by this real session. The highest-value
changes are synchronization and routing clarity, and they should land alongside the corresponding
Core/Operator capabilities. Until then, the existing Skills remain usable when the operator follows
their explicit fail-closed rules and reports unsupported command gaps instead of guessing.
