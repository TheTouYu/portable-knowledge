# Feedback Record

Copy file before any work starts, including work that is expected to happen immediately. Keep one record per feedback item. This record is a source-only workflow record, not a Claim, Authority Reference, Memory entry, Bundle, or projection.

## Control Fields

```yaml
feedback_id: feedback_star_cube_nexus_knowledge_plan_cli_friction
source: Star Cube Nexus project (game project, second governed-capture session 2026-07-31)
affected_system: Portable Knowledge Core CLI / knowledge-plan workflow
processing_state: received
validation_state: none
promotion_decision: not_promoted
```

## Original Feedback

Record original input separately and preserve it verbatim. Do not replace or rewrite it when adding interpretation, actions, or validation. Corrections and clarifications are appended as dated notes.

- Reported at: 2026-07-31
- Original source link or reference: Star Cube Nexus session; user statement delivered verbally in Chinese
- User intent: make the next knowledge-capture session smoother; have the PKC team address the friction

> 这边我还希望你做一些事情。我感觉你刚刚把知识录入到我们知识库的流程稍微有些复杂，相信你也感觉到了一些阻力。知识库是我们这边的另外一个项目，你能写一点反馈，写到他们项目的文档里面去，新增一个反馈。我会统一安排人手去处理，这样子下次你再录知识的时候就会变得更加顺手了。

## Interpretation

Working interpretation. This is interpretation, not part of the original feedback, and must not be presented as confirmed project fact.

- Observation: A real governed-capture session (3 operations: 2 add-claim, 1 revise-claim, 2 add-authority-ref, 1 refresh-authority-ref, 2 Bundles, 2 approvals, 4 commits) hit repeated CLI discoverability and feedback-quality problems. None blocked the final result, but each required reading PKC source code or plan JSON internals to proceed. The governance model itself (exact-hash approval, committed-baseline authority, dirty-path rejection) worked correctly and should not be weakened; the friction is in how the CLI surfaces its own contract.
- Scope: `pkc knowledge-plan` subcommands (`add-claim`, `add-authority-ref`, `check`, `finalize`, `inspect`, `abandon`), `bundle-approve`, `bundle-apply`, and `bundle-inspect`; help texts and error messages. Does not cover governance rules, Bundle immutability, or authority semantics.
- Suggested change: improve discoverability of required/valid option values and make dry-run results unmistakable; see work items.
- Open questions: whether help-text/error-message improvements should be done in the CLI layer or in `docs/QUICKSTART.md` only.

### Specific friction points observed (with exact evidence)

| # | Friction | Evidence |
| --- | --- | --- |
| F1 | `bundle-approve` defaults to dry-run but returns `ok: true`, so the caller believes approval was recorded; the follow-up `bundle-apply` then fails with `required file missing: ...approval.json`. | First run returned `{"ok": true, "applied": false, "dry_run": true}`; no visible warning; second command failed with `KNOWLEDGE_ERROR required file missing`. |
| F2 | `add-claim --fact-class` accepts a fixed enum but the error `add-claim requires valid fact classes` and `--help` never list the valid values; the enum lives only in source (`FACT_CLASSES`). | `grep` of installed `portable_knowledge/authority.py` was needed to learn the 8 values. |
| F3 | `add-authority-ref --claim-id` needs the planned claim id, which is deterministically generated at add-claim time but discoverable only by opening `.local/pkc/semantic-plans/<plan>.json`; the error `planned claim not found` gives no pointer to that path. | First attempt used a guessed id; error gave no lookup hint. |
| F4 | `knowledge-plan check` requires `--mode delta`, but `--help` does not enumerate the accepted mode values. | `check` failed with `the following arguments are required: --mode`; value `delta` was found only in source. |
| F5 | `knowledge-plan init` with the same `--intent` after `abandon` returns the same (abandoned) plan id, and the next operation fails with `PLAN_NOT_OPEN` with no hint to change the intent or that the id was reused. | `init --intent "..."` after abandon returned the same `pln_27526a77...`; subsequent add-claim failed `PLAN_NOT_OPEN`. |
| F6 | `bundle-inspect` nests the bundle under `bundles[0]` while `knowledge-plan inspect` returns top-level fields; `expected_changed_files` omits the `.applied.json`/`.approval.json` files that `bundle-apply` actually writes. | Output shape mismatch; changed list after apply included files not listed as expected. |

## Work Items

Track each action independently. Keep completed and remaining work visible; do not delete an item that is deferred, blocked, or rejected.

| ID | Work item | Status | Evidence or reason |
| --- | --- | --- | --- |
| W1 | Make dry-run results unmistakable: `bundle-approve`/`bundle-apply` in dry-run mode should print an explicit "DRY RUN, nothing written" line and/or set `ok: false` with a distinct code, so callers cannot mistake a dry run for a recorded approval. | remaining | F1 |
| W2 | Surface the `--fact-class` enum in `add-claim --help` and in the validation error message (list allowed values). | remaining | F2 |
| W3 | On `planned claim not found`, include the plan JSON path and a hint that planned claim ids are listed under `claims` in `.local/pkc/semantic-plans/<plan_id>.json`; ideally also print the generated claim id prominently in the add-claim success output. | remaining | F3 |
| W4 | Enumerate accepted `--mode` values in `knowledge-plan check --help`. | remaining | F4 |
| W5 | After `abandon`, make `init` with the same intent either create a fresh plan or fail with an explicit message naming the abandoned plan id; never silently return the abandoned plan. | remaining | F5 |
| W6 | Unify `bundle-inspect` output shape with `knowledge-plan inspect` (or document the nesting) and list bundle lifecycle files (`*.approval.json`, `*.applied.json`) in `expected_changed_files`. | remaining | F6 |

## Validation And Outcome

- Completed evidence: none (feedback record only; no CLI changes made).
- Remaining work: W1–W6 above, to be triaged by the PKC team.
- Validation note: this record reports observed CLI behavior from one consumer session; it does not assert root causes or prescribe implementation details beyond the suggested changes.
- Artifact links: `docs/FEEDBACK-star-cube-nexus-governed-capture-2026-07-31.md` (earlier feedback on multi-Bundle orchestration, complementary), `docs/QUICKSTART.md`.
- Outcome reason: none (received).

## Closeout Checklist

- [x] Every work item has a status; completed, remaining, deferred, rejected work is visible.
- [x] Remaining work is not `none`; W1–W6 are outstanding by design (consumer cannot fix PKC CLI).
- [x] `local_passed` is not treated as user production validation; no validation claimed.
- [ ] Deferred, blocked, rejected work reason and next action explicit; N/A, no such items.
- [x] Completed evidence artifact links recorded, limits stated; none completed.
- [x] `promotion_decision` remains `not_promoted`; no separate governed workflow requested.
- [x] No Claim, Authority Ref, Memory, Bundle, projection, or Git state changed by this record.

## Promotion Decision

- Decision: `not_promoted`
- Reason: feedback remains a workflow record; state and evidence review is needed by the PKC team before any future promotion.
- Related Claim, Authority Ref, Memory, or Bundle: `none`

Do not automatically convert this feedback into a Claim or alter Claim, Authority Ref, Memory, Bundle, projection, or Git state. Any future promotion requires a separate explicit request through the governed workflow of the owning project.

## Handoff And References

If this record is handed to another agent, state the next session's main task before listing deeper references. A matching handoff should use its recovery package without re-reading original references. Read an original reference only for a named missing fact or bounded evidence gap, and state that reason.

- Next task: PKC team triages W1–W6 (CLI discoverability and dry-run clarity) and decides where to fix (CLI layer vs docs).
- Targeted reference read reason: none.
- References:
  - `docs/FEEDBACK-star-cube-nexus-governed-capture-2026-07-31.md` — earlier complementary feedback on multi-Bundle closeout orchestration; read when combining both reports into one work stream.
  - `docs/QUICKSTART.md` — where end-to-end examples live; read when deciding W2/W4 doc-vs-CLI placement.
  - `src/portable_knowledge/semantic_plan.py` — location of `FACT_CLASSES` validation and plan-id generation; read when implementing W2/W3/W5.
