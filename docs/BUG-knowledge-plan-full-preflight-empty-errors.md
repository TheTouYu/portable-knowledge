# Bug / requirement: `knowledge-plan finalize` loses full-preflight Authority findings

Status: fixed in `0.2.0rc4`; same-plan Authority-path overlap is explicitly rejected during delta

Reported: 2026-07-28

Observed runtime: `portable-knowledge 0.2.0rc1`

Current repository at report time: `0.2.0rc2`, commit `1e000861fbfbab2611bf10d2c448942e1cb3e127`

Priority: high — production semantic ingestion is safely blocked, but the operator receives no actionable diagnosis

## Summary

A real project used the documented high-level workflow to add one Claim and one `documented_contract` Authority Reference. The delta check succeeded with `can_finalize: true`. `knowledge-plan finalize` then exited non-zero and returned:

```json
{
  "ok": false,
  "command": "knowledge-plan",
  "read_only": false,
  "operation_authorized": false,
  "errors": []
}
```

No Bundle was created and no formal Authority was changed, so the fail-closed safety behavior worked. However, the empty `errors` array prevents the operator from understanding whether the failure came from validation, projection, evaluation cases, or Authority freshness.

The real plan added a Claim to an existing Markdown file and also used that same committed Markdown file as the new Claim's Authority Reference. This appears to expose an additional delta/full consistency gap: delta accepted the plan, while full preflight likely observed the Authority path after the staged Claim block changed it.

## Real-consumer evidence

The consumer used a project-locked, non-editable wheel with no source checkout or `PYTHONPATH` fallback.

Runtime identity:

```text
version: 0.2.0rc1
source commit: f4b8c98d150361144087374467e4800673d14bd0
wheel sha256: 8ae6c657f22e2cb3be2abef64bdd7136ee282da975797a20af2cfb63025a864f
module origin: <project>/.local/pkc/runtimes/<commit>/lib/python3.14/site-packages/portable_knowledge/
```

Plan state after the failure:

```text
state: open
operations: 2
claims: 1
authority refs: 1
delta checks: 1
full checks: 0
candidate Bundles: 0
formal authority written: false
```

Delta result:

```json
{
  "ok": true,
  "summary": {
    "can_finalize": true,
    "touched_operations": 2,
    "touched_files": 3
  },
  "failed_case_ids": [],
  "affected_case_ids": [],
  "findings": []
}
```

The three prospective paths were:

```text
data/knowledge/authority-refs.json
data/knowledge/registry.json
knowledge/<node>/<existing-topic-authority>.md
```

The third path was both:

1. the existing committed document used as the `documented_contract` Authority Reference; and
2. the Topic path receiving the new Claim block in the same plan.

Repeated `finalize` calls produced the same non-zero result, empty stderr, and empty `errors`. The tracked consumer worktree remained clean.

## Minimal neutral reproduction

First verify whether the issue still reproduces on current `0.2.0rc2`; do not assume an rc1 observation is automatically current.

1. Create a committed neutral PKC project with:
   - one existing Node;
   - an existing Markdown document under that Node;
   - configured and committed `authority_refs` registry;
   - no failing evaluation cases.
2. Initialize one semantic plan.
3. Add a new Topic and first Claim whose `--topic-path` is that existing committed Markdown document.
4. Add a `documented_contract` Authority Reference for the new Claim whose `--path` is the same Markdown document.
5. Run delta check.
6. Run finalize.

Representative command shape:

```bash
pkc knowledge-plan init \
  --intent "Reproduce staged self-referential Authority path handling" \
  --risk medium

pkc knowledge-plan add-claim PLAN_ID \
  --node N-01 \
  --topic-id N-01-existing-document \
  --topic-path knowledge/node/existing.md \
  --topic-title "Existing document topic" \
  --topic-summary "Neutral bounded summary" \
  --topic-keyword neutral \
  --duplicate-resolution create_distinct_with_boundary \
  --title "Bounded documented Claim" \
  --statement "One neutral documented assertion." \
  --boundary "Does not establish runtime or external behavior." \
  --permission internal \
  --fact-class documented_contract

pkc knowledge-plan add-authority-ref PLAN_ID \
  --claim-id RETURNED_CLAIM_ID \
  --path knowledge/node/existing.md \
  --locator "section:existing-contract" \
  --role documented_contract \
  --change-policy invalidate_on_change \
  --fact-class documented_contract

pkc knowledge-plan check PLAN_ID --mode delta
pkc knowledge-plan finalize PLAN_ID
```

If current behavior intentionally forbids an Authority Reference to a path changed by the same plan, the delta command should reject it explicitly. If the pattern is intended to be supported, finalize must define which committed or staged hash the new Authority Reference approves and must complete consistently.

## Confirmed defect in error propagation

`semantic_plan.finalize()` builds full-preflight findings only from:

- `records["validation"]["errors"]`;
- `records["projection"]["errors"]`;
- failed evaluation case IDs.

But `_validation_records()` also makes `records["ok"]` depend on every observed Authority Reference having effective status `current` or `fresh`:

```python
ok = (
    validation["ok"]
    and projection["ok"]
    and tree.get("ok", False)
    and not failed
    and all(
        item.get("effective_status", item.get("status")) in {"current", "fresh"}
        for item in refs
    )
)
```

When only an Authority record causes `records["ok"] == false`, `finalize()` raises `PLAN_FULL_PREFLIGHT_FAILED` with an empty findings list. The CLI then serializes `SemanticPlanError.findings` directly because it is not `None`, producing `errors: []` and dropping the top-level error code/message.

This is independently actionable even if the same-path plan is ultimately declared invalid.

## Requirements

### R1 — Never emit an unexplained full-preflight failure

Any non-zero `knowledge-plan finalize` result must contain at least one structured error with:

- `code`;
- `path` or phase;
- actionable `message`;
- relevant Claim/Authority Reference ID when available.

If a specialized findings list is unexpectedly empty, preserve a fallback top-level error such as:

```json
{
  "code": "PLAN_FULL_PREFLIGHT_FAILED",
  "path": "full_preflight",
  "message": "full staged preflight failed without component findings"
}
```

The preferred fix is to report the actual failed component rather than rely only on this fallback.

### R2 — Include Authority observations in full-preflight findings

When an Authority Reference is not `current` or `fresh`, return a structured finding that includes at least:

- Authority Reference ID;
- referenced path;
- baseline status;
- working-tree status;
- effective status;
- expected/approved hash and observed hash when safe and available;
- whether the difference is caused by the current staged plan.

Suggested code family:

```text
PLAN_FULL_AUTHORITY_NOT_CURRENT
PLAN_AUTHORITY_STAGED_DRIFT
```

Final naming may follow existing conventions, but failure type must remain machine-readable.

### R3 — Delta and full preflight must agree on staged Authority-path overlap

Before returning `can_finalize: true`, delta must detect when a planned Authority Reference points to a path in the same plan's prospective writes.

The implementation must choose and document one policy:

1. **Reject the overlap:** return a structured delta finding and require the Claim body and Authority contract to live at distinct paths; or
2. **Support the overlap:** define whether the new Authority Reference binds to the committed before-image or staged after-image, ensure the stored approved hash matches that policy, and make full preflight/apply/rebuild observe it consistently.

Do not silently accept in delta and reject opaquely in full preflight.

The safer initial behavior is explicit rejection unless a reviewed semantic model exists for staged self-reference.

### R4 — Preserve fail-closed and governance behavior

The fix must not:

- create a Bundle after any failed full preflight;
- write formal Authority before approval/apply;
- weaken committed-baseline, worktree-dirty, fact-class, permission, provenance, exact-hash, or transaction checks;
- encourage direct Markdown/registry edits, Python APIs, low-level manifests, or compatibility mode.

### R5 — Keep schema examples and runtime keys consistent

During diagnosis, verify the Authority Reference registry key contract. Repository assets currently show both:

```json
{"schema_version": 1, "authority_refs": []}
```

and:

```json
{"schema_version": 1, "refs": []}
```

The semantic-plan implementation reads and writes `refs`. If `authority_refs` is a supported alias, normalize and test it explicitly. If not, update installation/operator examples so a newly configured project starts with the canonical key. This inconsistency did not by itself prove the reported finalize failure, but it increases diagnosis and adoption cost.

## Acceptance criteria

1. Add a regression test at the real `knowledge-plan finalize` CLI seam, not only a helper-unit seam.
2. The neutral same-path reproduction has one explicitly documented outcome:
   - delta rejects it with a non-empty structured finding; or
   - delta and finalize both succeed under a defined staged-hash policy.
3. A forced Authority freshness failure during full preflight returns non-empty `errors` containing the responsible Authority Reference/path/status.
4. A defensive test proves no `SemanticPlanError` can serialize as `ok:false` with `errors:[]`.
5. On failure:
   - candidate Bundle count remains 0;
   - formal Authority remains unchanged;
   - plan remains inspectable and abandonable;
   - worktree remains unchanged.
6. Existing semantic-plan provenance, delta/full budget, approval/apply, recovery, and repository-contract tests remain green.
7. Build a non-editable wheel from the fixed exact commit and validate the original consumer workflow without `PYTHONPATH` or source-checkout leakage.
8. Report fixed commit, version, wheel SHA-256, test commands, and whether the original real project reaches immutable Bundle creation. Do not approve or apply the consumer Bundle as part of tool verification.

## Out of scope

- Deciding the business semantics of the consumer Claim.
- Approving or applying any consumer Bundle.
- Migrating additional legacy Nodes or Claims.
- Weakening Authority freshness to make the reproduction pass.
- Treating synthetic fixture success as proof that the real consumer is fixed.

## Resolution

PKC uses the safer rejection policy. A new Authority Reference remains bound to the committed before-image; if its path is also present in the current plan's prospective writes, delta returns `PLAN_AUTHORITY_STAGED_DRIFT` with the Authority Reference ID, Claim IDs, path, and `staged_by_current_plan: true`. It does not define or infer staged after-image approval.

Full preflight now emits structured non-current Authority findings with reference/path/status/hash fields, and CLI serialization preserves a top-level fallback error if specialized findings are unexpectedly empty. The registry's canonical key is `refs`; `authority_refs` is a read-compatible alias normalized by the next governed semantic-plan write, while conflicting dual keys fail closed.

## Consumer recovery after a fix

After a fixed wheel is available:

1. use the PKC Project Operator upgrade flow to resolve the exact fixed commit and wheel hash;
2. install a parallel non-editable runtime and switch the consumer lock only after reviewed L2 approval;
3. abandon or retain the old open plan as diagnostic history according to the tool contract;
4. create a fresh plan from the new committed consumer baseline;
5. run delta and finalize once;
6. stop at the immutable Bundle and request independent L3 human review.
