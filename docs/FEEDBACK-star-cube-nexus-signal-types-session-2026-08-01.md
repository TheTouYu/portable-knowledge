# Feedback Record

Copy file before any work starts, including work that is expected to happen immediately. Keep one record per feedback item. This record is a source-only workflow record, not a Claim, Authority Reference, Memory entry, Bundle, or projection.

## Control Fields

```yaml
feedback_id: feedback_star_cube_nexus_signal_types_session
source: Star Cube Nexus project (game project, signal-type verification session 2026-08-01)
affected_system: Portable Knowledge Core CLI / knowledge-plan workflow
processing_state: received
validation_state: none
promotion_decision: not_promoted
```

## Original Feedback

Record original input separately and preserve it verbatim. Do not replace or rewrite it when adding interpretation, actions, or validation. Corrections and clarifications are appended as dated notes.

- Reported at: 2026-08-01
- Original source link or reference: Star Cube Nexus session (handoff 10 → v11 sample + global VarType table); user statement delivered verbally in Chinese
- User intent: reduce the number of blocked steps a governed-capture session hits; fix the remaining CLI contract gaps; have the PKC team optimize the maintenance skill/workflow

> 刚刚看到你遇到了不少阻碍，有没有可以优化的地方？比如让知识库项目的负责人对维护技能做一下优化，或者给他们提一些关于知识库知识的建议。你可以写一个反馈或需求文档，提交到知识库项目（它也在加目录）。

## Interpretation

Working interpretation. This is interpretation, not part of the original feedback, and must not be presented as confirmed project fact.

- Session context: one governed-capture session with 2 revise-claim, 1 add-claim, 3 add-authority-ref, 2 refresh-authority-ref, 1 bundle approve+apply, 2 commits. Prior feedback (feedback_star_cube_nexus_knowledge_plan_cli_friction, F1–F6) is tracked in OPTIMIZATION-PLAN-v2 WS-A and partly fixed in the locked runtime (verified below). This record reports only what this session still hit after those fixes.
- WS-A verification against locked runtime `e580617ecf740674d5fbc0c0d0cd2685edd7b324` (2026-08-01):
  - F1 (dry-run unnoticed): help now shows mutually exclusive `--apply | --dry-run`; not re-tested end-to-end. Partly fixed.
  - F2 (fact-class enum not surfaced): `add-claim --help` now shows `--fact-class`, but the 8 allowed values still do not appear in help or in the validation error. Partly fixed.
  - F4 (check --mode enum): `--mode {delta}` now enumerated in help. Fixed.
  - F3/F5/F6: not re-tested this session (not hit).
- New friction points observed this session (not in F1–F6):

| # | Friction | Evidence |
| --- | --- | --- |
| N1 | `PLAN_STALE_BASELINE` kills a whole open plan with no recovery path: committing the authority document after `init` (which the canonical flow implicitly requires, because `add-authority-ref` rejects uncommitted authority paths) invalidates the plan baseline; every subsequent mutation fails with "committed baseline changed since plan init", and the only way out is `abandon` + re-`init` + replaying all operations. | After commit `d958fa2` (docs), `add-claim` failed `PLAN_STALE_BASELINE`; the error message names no remedy. Replayed 2 revise + 1 add-claim + 3 refs + 2 refreshes in a fresh plan. |
| N2 | `add-authority-ref` accepts only claims added inside the plan; for claims modified via `revise-claim` it fails `PLAN_CLAIM_MISSING` with no hint that the correct tool is `refresh-authority-ref` on the existing ref id. | First `add-authority-ref` on `clm_B334BFA5…` (revised claim) failed; the fix (refresh the pre-existing `aref_…`) was found by reading `semantic_plan.py` source. |
| N3 | `finalize` full-preflight reports invalidated authority refs in batches: after refreshing the first two, a second `finalize` revealed two more, then a third revealed one more (AGENTS.md ref invalidated by an earlier commit). Each round needs check → finalize → read errors → refresh → repeat. | Three successive `finalize` runs each failed with 1–2 new `PLAN_FULL_AUTHORITY_NOT_CURRENT` entries; the final set (5 refs) could not be enumerated in advance. |
| N4 | `knowledge-plan inspect --format text` prints only `OK: knowledge-plan inspect`; the JSON shape also omits claim/ref/operation details, so the only way to see what a plan holds is reading `.local/knowledge/semantic-plans/<plan_id>.json` by hand. | `inspect --format text` produced no fields; plan JSON file had to be parsed directly to list claims, operations, and refs. |

- Process-order confusion (documentation, not CLI): `docs/knowledge-capture-canonical-flow.md` says "in the same plan: add-claim → add-authority-ref" but does not state that authority documents must be committed **before** `init`; this is exactly what caused N1. The flow doc was updated in the consumer project; PKC-side QUICKSTART could state it explicitly.

## Work Items

Track each action independently. Keep completed and remaining work visible; do not delete an item that is deferred, blocked, or rejected.

| ID | Work item | Status | Evidence or reason |
| --- | --- | --- | --- |
| W7 | `PLAN_STALE_BASELINE` error should state the remedy (abandon + re-init + replay, or a future plan rebase) and ideally offer a non-destructive way to re-baseline an open plan instead of forcing replay. | remaining | N1 |
| W8 | `add-authority-ref` `PLAN_CLAIM_MISSING` should distinguish "no such claim id" from "claim was revised, not added — use refresh-authority-ref on the existing ref" and point to the plan JSON path. | remaining | N2 |
| W9 | `finalize` full-preflight should enumerate **all** invalidated/stale authority refs in one pass (with claim ids and expected-vs-observed hashes), not stop at the first few. | remaining | N3 |
| W10 | `knowledge-plan inspect --format text` should print a summary (state, baseline, claims with titles, operations, refs) instead of an empty OK line; JSON output should include the same detail. | remaining | N4 |
| W11 | Surface the 8 `--fact-class` allowed values in `add-claim`/`add-authority-ref` help and validation errors (completion of F2). | remaining | F2 partial fix |
| W12 | State in PKC-side QUICKSTART (or canonical flow) that authority documents must be committed before `knowledge-plan init`, and that git commits inside an open plan invalidate it. | remaining | N1 root cause |

## Validation And Outcome

- Completed evidence: none (feedback record only; no CLI changes made).
- Remaining work: W7–W12 above, to be triaged by the PKC team.
- Validation note: this record reports observed CLI behavior from one consumer session against locked runtime `e580617…`; it does not assert root causes or prescribe implementation details beyond the suggested changes. WS-A fixes (F4, partial F1/F2) were observed live in the locked runtime and are noted as verification, not as completed work items.
- Artifact links: `docs/FEEDBACK-star-cube-nexus-knowledge-plan-cli-friction-2026-07-31.md` (F1–F6, complementary), `docs/OPTIMIZATION-PLAN-v2.md` (WS-A tracks F1–F6), `docs/QUICKSTART.md`.
- Outcome reason: none (received).

## Closeout Checklist

- [x] Every work item has a status; completed, remaining, deferred, rejected work is visible.
- [x] Remaining work is not `none`; W7–W12 are outstanding by design (consumer cannot fix PKC CLI).
- [x] `local_passed` is not treated as user production validation; no validation claimed.
- [ ] Deferred, blocked, rejected work reason and next action explicit; N/A, no such items.
- [x] Completed evidence artifact links recorded, limits stated; none completed.
- [x] `promotion_decision` remains `not_promoted`; no separate governed workflow requested.
- [x] No Claim, Authority Ref, Memory, Bundle, projection, or Git state changed by this record.

## Promotion Decision

- Decision: `not_promoted`
- Reason: feedback remains a workflow record; state and evidence review is needed by the PKC team before any future promotion.
