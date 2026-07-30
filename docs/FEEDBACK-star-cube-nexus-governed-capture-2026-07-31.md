# Real-consumer feedback: governed Claim capture and Memory Authority closeout

Status: field feedback

Reported: 2026-07-31

Consumer: Star Cube Nexus, a configured project using a project-locked non-editable PKC runtime

Observed runtime/Core: `0.2.0rc5`

Consumer baseline before capture: `3 Nodes / 7 Topics / 26 Claims`, retrieval `13/13`

Consumer outcome after closeout: `3 Nodes / 7 Topics / 27 Claims`, retrieval `13/13`, Authority References `31 current / 0 pending`

Priority: P1 workflow orchestration and diagnostic clarity; no request to weaken governance

## Summary

A real consumer session promoted one bounded, owner-validated game-authoring conclusion from committed practice evidence into a governed Claim. The session completed read-only deduplication, candidate planning, exact-hash Bundle review, approval/application, Project Memory synchronization, Authority Reference refresh, two local Git commits, and final health verification.

The safety model worked throughout:

- no formal authority changed before exact-hash approval;
- a dirty Authority path was rejected;
- an invalidated Authority Reference blocked full preflight;
- the tool did not auto-refresh a semantic reference;
- Bundle application was transactional and post-apply checks passed;
- Git commit and push remained separate authorization gates.

The main friction was not a missing primitive. It was that the safe end-to-end sequence only became visible one blocker at a time. A single conceptual closeout required two Bundles and two commits because the governed Claim changed a configured Memory count/status surface, while that Memory file was itself Authority for a separate current-next-step Claim.

This report recommends making that multi-phase dependency explicit and mechanically guided while preserving committed-baseline and exact-hash invariants.

## What the consumer was trying to do

The source evidence already existed in two committed documents:

- fixed U/R recovery with offline, GIA, injection/readback, and owner in-game evidence;
- fixed U/R/F recovery with the same separated evidence layers and an explicit ceiling excluding arbitrary input, six-face gameplay, general cubie visual orientation, UI, and renewed real-map authorization.

The intended semantic result was one new internal Claim under an existing Topic:

```text
mvp-core / action-presentation
Pivot-follow has bounded three-axis in-game validation
```

The Claim was deliberately narrower than the implementation plan and did not claim complete MVP behavior.

## Exact observed workflow

### Phase A: Claim capture

1. Bounded L1/L2/L3 queries found no equivalent active Claim.
2. `knowledge-plan` created one Claim and two Authority References to committed evidence.
3. Delta check passed.
4. First finalize failed because an existing Memory Authority Reference was already invalidated:

```text
PLAN_FULL_AUTHORITY_NOT_CURRENT
path: memory/CURRENT.md
authority_ref_id: aref_ac6e4c730f24cb1a9e27c9b188
```

5. The linked current-next-step Claim was reviewed and remained supported, so the invalidated Ref was added to the same plan as a refresh operation.
6. Delta and full preflight passed; the Bundle was reviewed by exact hash, approved, and applied.
7. Post-apply counts became `3/7/27`.

This is additional real-consumer evidence for the existing full-Authority-closure preview requirement in `docs/REQUIREMENTS-real-consumer-operations.md` R3. Delta was truthful about touched operations but did not prepare the operator for the full closure blocker.

### Phase B: Memory synchronization

The configured count surface still said 26 Claims, so `knowledge-check` failed until `memory/CURRENT.md` was updated to 27. The same file also still called the U/R/F result a governed candidate, so it required a second owner-reviewed text synchronization after the Claim had been applied.

After the Memory edit:

```text
Knowledge health: PASS
Memory freshness: PASS
Retrieval: 13/13
Authority refs: 30 current / 1 pending_review
```

The overall check displayed PASS even though one Authority Reference required review.

### Phase C: Memory Authority refresh

The owner authorized generation of a refresh plan, but the first attempt failed correctly:

```text
PLAN_AUTHORITY_WORKTREE_DIRTY
path: memory/CURRENT.md
message: Authority path differs from plan committed baseline
```

The plan remained empty: zero operations, zero Bundles, no formal Authority write.

The project then needed a separately authorized local Git commit containing the first applied Bundle, its receipts, and the reviewed Memory update. Only after that commit could a new one-operation refresh plan bind the Memory Authority Ref to the committed hash. That second Bundle then required a second exact-hash approval/application and a second local Git commit.

Final state:

```text
Knowledge health: PASS
Nodes/Topics/Claims: 3/7/27
Memory freshness: PASS
Retrieval: 13/13
Authority refs: 31 current / 0 pending
```

## Friction and recommendations

## 1. Add a first-class multi-phase closeout preview

Priority: P1

The system should recognize this dependency shape before the first finalize:

```text
new/revised Claim
→ configured count/current Memory surface changes
→ that Memory path is itself an Authority Reference
→ refreshed Authority requires a committed after-image
→ at least two governed/Git phases are required
```

Do not make one Bundle span uncommitted Authority or let PKC perform Git commits. Instead, add a read-only orchestration preview, either in Core or the Operator, that reports the required phases and gates up front.

Suggested output shape:

```json
{
  "phase_plan": [
    {
      "phase": 1,
      "purpose": "apply Claim capture Bundle",
      "requires_exact_hash_approval": true
    },
    {
      "phase": 2,
      "purpose": "synchronize configured Memory/count surfaces",
      "requires_reviewed_file_diff": true,
      "requires_git_commit": true
    },
    {
      "phase": 3,
      "purpose": "refresh Authority References to committed Memory",
      "requires_exact_hash_approval": true,
      "requires_git_commit_after_apply": true
    }
  ]
}
```

This preserves every current invariant while preventing the operator from discovering the sequence through repeated failures.

### Acceptance criteria

1. A fixture where a Claim count change affects a configured Memory surface that is also Authority reports the complete phase chain before the first Bundle is finalized.
2. Preview changes no tracked files, creates no Bundle, performs no Git mutation, and grants no authorization.
3. It distinguishes mandatory phases from optional project conventions.
4. It identifies exact paths, linked Authority Ref IDs, linked Claim IDs, and the reason a commit boundary is required.
5. Drift after preview still fails closed during ordinary plan/apply operations.

## 2. Make `knowledge-check` tri-state at the presentation layer

Priority: P1

`knowledge-check` reported `Knowledge health: PASS` while also reporting one `pending_review` Authority Ref. This is internally consistent if pending review is warning-only, but the headline is easy for a human or model to overread as “fully closed.”

Keep exit-code behavior if compatibility requires it, but expose an explicit summary state such as:

```text
PASS
PASS_WITH_REVIEW
FAIL
```

Machine-readable output should separately report:

```json
{
  "checks_passed": true,
  "review_required": true,
  "authority_refs": {"current": 30, "pending_review": 1, "invalidated": 0}
}
```

The final closed state would then be `PASS`, while the intermediate state would be `PASS_WITH_REVIEW`.

### Acceptance criteria

1. Pending or invalidated review-warning policy is explicit in JSON, not inferable only from warning strings.
2. Human text cannot be mistaken for full closure when review remains.
3. Existing automation can retain exit code 0 for warning-only states if documented.
4. Projects may choose whether `pending_review` is warning-only or blocking without changing Authority semantics.

## 3. Improve dirty-Authority failure remediation

Priority: P1

`PLAN_AUTHORITY_WORKTREE_DIRTY` was correct, but it did not state the actionable sequence. The operator had to infer that the reviewed Memory after-image must be committed before plan initialization/refresh, and that this would require a separate Git authorization.

Recommended structured fields:

```json
{
  "code": "PLAN_AUTHORITY_WORKTREE_DIRTY",
  "path": "memory/CURRENT.md",
  "required_state": "committed_baseline",
  "safe_next_steps": [
    "review the exact file diff",
    "obtain separate Git commit authorization",
    "commit the Authority path",
    "initialize a new refresh plan at the new HEAD"
  ],
  "forbidden_shortcuts": [
    "do not refresh to working-tree bytes",
    "do not fabricate a diagnostic hash",
    "do not bypass committed-baseline validation"
  ]
}
```

Also consider rejecting `knowledge-plan init` early when its declared intent names a dirty Authority Ref/path, if that can be determined without guessing semantic operations. Otherwise the refresh operation itself is an acceptable rejection point.

### Acceptance criteria

1. The error explains why a commit boundary exists, not only that the file is dirty.
2. It distinguishes “commit the reviewed source first” from “discard local changes.”
3. It never runs `git add` or `git commit` automatically.
4. An empty failed plan remains inspectable and easy to abandon.

## 4. Clarify `--apply` and `applied` in mutation command output

Priority: P1

After:

```bash
pkc bundle-approve BUNDLE_ID --content-hash HASH --apply
```

the output included:

```json
{"command":"bundle-approve","applied":true}
```

At this point the approval receipt had been written, but the knowledge Bundle itself had not yet been applied; `bundle-apply` was still required. The field name can mislead an operator into believing the Bundle lifecycle is already `applied`.

Use command-specific wording, for example:

```json
{
  "approval_recorded": true,
  "bundle_state": "approved",
  "bundle_applied": false
}
```

For `bundle-apply`:

```json
{
  "bundle_applied": true,
  "bundle_state": "applied"
}
```

The CLI flag could remain `--apply` as the generic dry-run/mutate switch, but output should not overload `applied` for both “the command mutation executed” and “the Bundle reached applied lifecycle state.”

### Acceptance criteria

1. Approval output cannot be confused with Bundle application.
2. `bundle-inspect` and mutation command outputs use the same lifecycle vocabulary.
3. Compatibility aliases, if retained, are documented as command-execution fields rather than Bundle state.

## 5. Count refresh operations explicitly in plan summaries

Priority: P2

A one-operation Authority refresh plan reported:

```text
operation_count: 1
authority_ref_count: 0
```

This may mean “new Authority Refs added,” but the name looks like “Authority Refs affected.” The semantic diff correctly showed one refreshed Ref, so the compact summary and detailed semantics use different counting intuitions.

Prefer explicit counters:

```json
{
  "authority_refs_added": 0,
  "authority_refs_refreshed": 1,
  "authority_refs_retired": 0,
  "authority_refs_affected": 1
}
```

Apply the same vocabulary to plan inspect, finalize, Bundle inspect, and receipts.

## 6. Provide a bounded human-readable Bundle review projection

Priority: P2; already substantially covered by `docs/REQUIREMENTS-real-consumer-operations.md` R4

The canonical Bundle was a very large one-line JSON object. The harness file reader could not display it directly, so review required `bundle-inspect` plus an ad hoc JSON projection. Canonical compact bytes are useful for deterministic hashing, but they are not a sufficient human review surface.

This session reinforces R4. A deterministic `.review.md` or richer `bundle-inspect --review` output should be considered part of the exact-hash review experience, while clearly remaining outside the hashed authority payload.

## 7. Make the recommended command sequence match actual efficient use

Priority: P2

The documented workflow says “one delta check after the plan is complete, then finalize once.” In the session, finalize exposed an existing non-current Authority Ref that delta did not report, so the plan had to be amended and delta rerun. This is safe but makes the idealized command budget unattainable without a full-closure preview.

Documentation should either:

- add the R3 full-preview before the one delta/finalize sequence; or
- explicitly say that a finalize-discovered closure blocker may require plan amendment and a new delta, without framing this as operator misuse.

## What should not change

The following behavior prevented incorrect authority and should remain:

- Authority References bind only to committed bytes.
- Dirty Authority blocks refresh.
- A model cannot self-approve its own Bundle.
- Exact-hash approval is invalidated by content change.
- Claim capture, Memory review, Authority refresh, Git commit, push, and external game writes remain separate authorization scopes.
- `knowledge-check` does not auto-rewrite Memory or Claims.
- A lower evidence layer never proves GIA generation, injection, editor loading, or in-game behavior.

## Suggested implementation order

1. Add full Authority/dependency phase preview and richer dirty-Authority remediation.
2. Clarify `knowledge-check` review-required state.
3. Clarify approve/apply output lifecycle fields.
4. Add explicit Authority operation counters.
5. Deliver the human review projection already proposed in R4.

## Minimal regression scenario

Create a configured fixture with:

- one current status Claim backed by `memory/CURRENT.md`;
- `memory/CURRENT.md` listed as both a current/count surface and an Authority path;
- a committed baseline count of one Claim;
- a new Claim candidate that changes the expected count to two;
- an exact retrieval fixture that remains green.

Verify:

1. Pre-capture health is fully clean.
2. Orchestration preview predicts Claim apply, Memory synchronization/commit, then Authority refresh.
3. First Claim Bundle can be reviewed and applied without weakening Authority checks.
4. The stale count is detected with an actionable Memory diff requirement.
5. After the reviewed but uncommitted Memory edit, refresh fails with structured commit-boundary remediation.
6. After commit, a one-operation refresh plan finalizes.
7. Approval output says approval was recorded but Bundle is not yet applied.
8. Apply output says Bundle reached applied state.
9. Final health reports no review required and all Authority Refs current.
10. No command performs an implicit Git commit or expands a prior approval.

## Evidence boundary

This is field feedback from one successful real consumer workflow. It proves the observed CLI behavior and operator friction in the stated runtime/project sequence. It does not by itself establish cross-platform behavior, performance characteristics, or the best internal implementation. Static-assembly upstream warnings present in the consumer project were unrelated and intentionally excluded.
