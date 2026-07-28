# Bug / optimization: `knowledge-check` and `knowledge-plan` use divergent evaluation contracts

Status: open

Reported: 2026-07-29

Priority: high — production knowledge ingestion fails closed, but only after repeated plan reconstruction and misleading green checks

Observed consumer runtime: `portable-knowledge 0.2.0rc3`

Current PKC source inspected at report time: commit `cfff9bf98745508cd577d9dc07e69b4934530e4b`

## Summary

A real consumer project followed the governed write workflow:

```text
knowledge-plan init
→ revise two Claims
→ add one Claim and Authority Reference
→ one delta check
→ finalize
```

The project-level evaluation command reported all 12 cases passing, and the semantic plan delta check reported `can_finalize: true`. Nevertheless, `knowledge-plan finalize` rejected the plan because full preflight reported evaluation failures.

This is not merely a ranking fluctuation. Source inspection shows that PKC currently has two different evaluation loaders and two different evaluation executors:

- `portable_knowledge.experience.load_evaluation_cases()` / `evaluate_cases()` power the project experience check;
- `portable_knowledge.semantic_plan._evaluation_cases()` / `_affected_cases()` / `_run_cases()` power semantic-plan delta and full preflight.

They do not implement the same schema aliases, query construction, defaults, assertions, or affected-case routing. Therefore a project can obtain contradictory verdicts from the same configured fixture.

The safety property held: no Bundle was created and formal Authority was not changed. The usability and governance problem is that the documented preflight sequence gives a false green delta, then blocks only at finalize, after an operator has already spent substantial effort rebuilding plans.

## Real-consumer evidence

The consumer project had a committed Authority baseline and a 12-case retrieval/refusal fixture. Before the semantic plan:

```text
Knowledge health: PASS
Retrieval cases: 12/12 (Topic@3, Claim@5)
```

The intended semantic change was bounded to one existing Topic:

1. correct an outdated Claim about explicit static-assembly color and public typed configuration;
2. expand an existing static GIL assembly Claim with a newly committed real-environment verification boundary;
3. add one safe real-writeback workflow Claim with a committed Authority Reference.

### First failure: schema alias mismatch

The real fixture used the earlier documented camelCase spelling:

```json
{
  "schemaVersion": 1,
  "defaults": {
    "topicTopN": 3,
    "claimTopN": 5
  },
  "cases": [
    {
      "id": "example",
      "query": "...",
      "searchTerms": ["..."],
      "expectedTopicIds": ["topic-id"],
      "expectedClaimIds": ["claim-id"]
    }
  ]
}
```

`knowledge-check` accepted this fixture and passed 12/12. In contrast, semantic-plan delta rejected it before evaluating any case:

```json
{
  "code": "PLAN_EVALUATION_SCHEMA",
  "path": "data/knowledge/evaluation/retrieval-cases.json",
  "message": "evaluation cases must use schema_version 1"
}
```

This contradicts `docs/QUICKSTART.md`, which states:

> Both snake_case Core names and the earlier camelCase fixture spelling are accepted.

It also contradicts the current implementation in `experience.load_evaluation_cases()`, which explicitly accepts both `schema_version` and `schemaVersion`.

### Second failure: field alias mismatch

After adding `schema_version` while retaining `schemaVersion`, delta passed because no cases were recognized as affected. Full preflight then failed all 12 cases because semantic-plan evaluation did not recognize camelCase `expectedTopicIds`.

The consumer temporarily added snake_case aliases alongside the existing camelCase fields. This made semantic-plan full preflight understand the expected Topic IDs, but exposed the deeper execution mismatch below. This compatibility edit was a diagnosis step, not a recommended consumer workaround.

### Third failure: execution and assertion mismatch

With dual spellings present, the same fixture produced:

```text
knowledge-check: 12/12 PASS
knowledge-plan check --mode delta: PASS, affected_case_ids=[]
knowledge-plan finalize: FAIL, 6 cases failed
```

Failed cases:

```text
clockwise-semantics
orientation-counting
animation-lock
exact-transform
asset-static-assembly-capability
evidence-layers-refusal
```

Plan state remained safe and inspectable:

```text
state: open
operations: 4
claims: 1
authority refs: 1
delta checks: 1
candidate Bundles: 0
formal authority written: false
finalized_bundle_id: null
```

The exact consumer plan and local `.local` artifacts are intentionally not authority and are not required to understand the source-level contract split.

## Confirmed implementation divergence

### 1. Top-level schema aliases differ

`experience.load_evaluation_cases()` accepts both:

```python
schema = fixture.get("schema_version", fixture.get("schemaVersion"))
```

`semantic_plan._evaluation_cases()` accepts only:

```python
if value.get("schema_version") != 1:
    _fail("PLAN_EVALUATION_SCHEMA", ...)
```

### 2. Case-field aliases differ

The experience path accepts both spellings for:

- `expected_topic_ids` / `expectedTopicIds`;
- `expected_claim_ids` / `expectedClaimIds`;
- `must_not_claim_ids` / `mustNotClaimIds`;
- `search_terms` / `searchTerms`.

The semantic-plan path uses a separate partial vocabulary:

- affected-case routing reads `topic_ids`, `node_ids`, and `claim_ids` only;
- execution reads `expected_topic_ids`, falling back to `topic_ids`;
- it does not consume `expectedTopicIds`, `expected_claim_ids`, `expectedClaimIds`, `must_not_claim_ids`, `mustNotClaimIds`, `search_terms`, or `searchTerms`.

### 3. Query execution differs

The experience path:

- combines `query` with optional alternate search terms;
- uses configured permission;
- retrieves enough results for configured Topic@N and Claim@N checks;
- evaluates Topic and Claim expectations;
- evaluates forbidden Claims;
- verifies permission/lifecycle/conflict filters.

The semantic-plan path:

```python
core.query_command(staging, case["query"], level, limit, 0, "internal")
```

It:

- ignores alternate search terms;
- hard-codes `internal` permission;
- defaults to `limit=5`, independently of `topicTopN`/`claimTopN`;
- passes a case when any returned Topic intersects expected Topics;
- ignores expected Claim IDs;
- ignores forbidden Claim IDs;
- does not enforce the same refusal/filter assertions.

Consequently, full preflight is neither equivalent to `knowledge-check` nor a strict, clearly documented superset of it.

### 4. Delta affected-case routing can produce a false green

The consumer fixture identifies expected results using `expectedTopicIds` / `expectedClaimIds`, as supported by `knowledge-check` and current Quickstart documentation. `_affected_cases()` instead looks for separate scope fields:

```python
case.get("topic_ids", [])
case.get("node_ids", [])
case.get("claim_ids", [])
```

Because those fields were absent, delta reported:

```json
{
  "affected_case_ids": [],
  "failed_case_ids": [],
  "can_finalize": true
}
```

Full preflight then evaluated all cases and failed later. This defeats the practical purpose of delta as an early semantic regression gate.

## User impact

1. Operators receive contradictory PASS/FAIL evidence from the same configured evaluation fixture.
2. The documented “run exactly one delta, then finalize once” workflow becomes difficult to follow: discovering a Core contract mismatch after delta forces plan abandonment and reconstruction from a new committed baseline.
3. Consumers may modify fixtures merely to satisfy an internal parser, accidentally changing tracked authority-adjacent evaluation assets without improving knowledge quality.
4. A green delta can be meaningless when `affected_case_ids=[]` due only to field-vocabulary mismatch.
5. Full preflight failures provide only case IDs, not returned Topic/Claim IDs, ranks, expected values, query mode, limit, or terms, making legitimate retrieval regressions expensive to diagnose.
6. Because finalization is fail-closed, no unauthorized knowledge is written; however, high-friction false or opaque blocking discourages use of the governed workflow.

## Requirements

### R1 — One canonical evaluation schema and normalizer

Implement one shared loader/normalizer used by both `knowledge-check` and semantic-plan validation.

It must:

- accept the documented snake_case names;
- accept the earlier camelCase aliases for backward compatibility, or perform an explicit versioned migration with actionable diagnostics;
- normalize once into one internal representation;
- reject conflicting dual fields when both are present with different values;
- provide path- and case-specific structured schema errors.

Do not maintain duplicate alias logic in `experience.py` and `semantic_plan.py`.

### R2 — One canonical evaluator

Use the same deterministic evaluation engine for:

- project `knowledge-check`;
- semantic-plan delta against staged projection;
- semantic-plan full preflight against staged projection.

The staged root/projection may differ, but these semantics must not:

- query and alternate search-term handling;
- permission;
- Topic@N and Claim@N limits;
- expected Topic and Claim assertions;
- forbidden Claim assertions;
- lifecycle/conflict/permission filters;
- result ranking interpretation.

If full preflight intentionally adds stricter checks, document and report them as additional named checks rather than silently replacing the project evaluator with a weaker/different implementation.

### R3 — Define affected-case scope explicitly

Do not infer mutation scope from expected result fields unless that policy is intentional and documented.

Prefer explicit optional scope fields such as:

```json
{
  "affected_by": {
    "node_ids": [],
    "topic_ids": [],
    "claim_ids": []
  }
}
```

Requirements:

- normalize supported legacy scope aliases;
- distinguish “case is unaffected” from “case has no scope metadata”;
- choose a safe fallback for unscoped cases, such as running all cases or reporting that delta coverage is conservative;
- never return an unexplained `affected_case_ids=[]` green result when touched Claims/Topics could influence global lexical ranking;
- report why each case was selected or skipped when requested in JSON diagnostics.

Because adding or revising one Claim can alter rankings for queries outside its expected Topic, a purely ID-intersection delta may be unsound. Evaluate whether all retrieval cases should run by default for small fixtures, with explicit safe optimization only for large suites.

### R4 — Make delta and finalize verdicts coherent

Given an unchanged plan, baseline, fixture, runtime, and deterministic projection:

- a successful delta should not be followed by a full-preflight failure caused solely by schema parsing or evaluator-contract differences;
- if finalize runs a broader suite, delta output must state that distinction clearly, including counts and the exact cases deferred to full preflight;
- full preflight must reuse the same normalized fixture and evaluation semantics.

The goal is not to guarantee that a partial delta predicts every full check; the goal is to prevent hidden semantic drift between the two paths.

### R5 — Return actionable evaluation failure records

For each failed case, return at least:

- case ID;
- normalized query and whether alternate terms were used;
- mode and permission;
- Topic/Claim limits;
- expected Topic IDs and returned Topic IDs with ranks;
- expected Claim IDs and returned Claim IDs with ranks;
- forbidden Claim IDs encountered;
- which assertion(s) failed;
- whether the case ran in delta, full preflight, or both.

Keep bounded summaries in normal JSON output; detailed records may live in the staged preflight artifact, but the CLI must expose the artifact path.

### R6 — Preserve governance and fail-closed behavior

The fix must not:

- create a Bundle after any failed required evaluation;
- alter formal Authority before exact-hash approval/apply;
- weaken committed-baseline, Authority, fact-class, permission, provenance, staged validation, or transaction checks;
- encourage direct registry/Markdown edits or fixture weakening;
- treat a project `knowledge-check` PASS as real-environment evidence.

### R7 — Improve operator recovery

When schema/evaluator incompatibility is detected before a Bundle exists:

- recommend abandoning and rebuilding only when the baseline or plan content must change;
- distinguish tool-contract failure from actual retrieval regression;
- avoid telling operators to add duplicate camelCase and snake_case fields;
- include the runtime version and evaluator contract version in diagnostics.

## Acceptance criteria

1. Add a neutral CLI-level regression fixture using camelCase only. The same fixture is accepted by `knowledge-check`, delta, and finalize.
2. Add an equivalent snake_case-only fixture. Its normalized form and all verdicts match the camelCase fixture.
3. A fixture containing both spellings with different values fails with a structured conflict error naming the field and case/path.
4. A fixture with `searchTerms` required to retrieve the expected Claim passes identically in `knowledge-check` and staged full preflight.
5. A fixture with a required expected Claim and a forbidden Claim is enforced identically in both paths.
6. Permission, lifecycle, conflict, Topic@N, and Claim@N defaults are identical in both paths.
7. Delta does not silently report `affected_case_ids=[]` merely because the fixture uses expected-result fields rather than legacy scope fields.
8. If delta intentionally runs fewer cases than finalize, output explicitly lists selected, skipped, and deferred cases with reasons.
9. A deliberately broken staged Claim produces the same failed assertion category and comparable ranked diagnostics in project evaluation and semantic full preflight.
10. On any evaluation failure:
    - candidate Bundle count remains 0;
    - formal Authority remains unchanged;
    - plan remains inspectable and abandonable;
    - worktree remains unchanged.
11. Existing semantic-plan provenance, exact-hash approval/apply, recovery, Authority freshness, and experience-contract tests remain green.
12. Build a non-editable wheel from the fixed exact commit and verify the original consumer flow reaches immutable Bundle creation without editing the dual-schema fixture or weakening cases. Do not approve/apply the consumer Bundle as part of tool verification.

## Suggested implementation direction

1. Move fixture loading and normalization into a shared module, for example `portable_knowledge.evaluation_contract`.
2. Define a normalized typed structure for defaults, case assertions, and affected-by scope.
3. Make `experience.evaluate_cases()` operate on normalized cases.
4. Replace `semantic_plan._evaluation_cases()` and `_run_cases()` with the shared loader/evaluator against the staged root.
5. Either run all cases during delta by default or introduce an explicit, tested conservative scope selector.
6. Store one structured evaluation receipt shape for `knowledge-check`, delta artifacts, and full-preflight artifacts.
7. Keep presentation differences at the CLI layer only; do not fork semantics again.

## Minimal regression design

A compact test should include at least three Claims across two Topics:

- one expected Claim retrieved only when an alternate search term is used;
- one tempting but forbidden Claim;
- one unrelated Claim whose ranking changes after a staged revision.

Run the same fixture through:

```text
knowledge-check on committed root
knowledge-plan check --mode delta on staged root
knowledge-plan finalize full preflight on staged root
```

Assert normalized case identity, query inputs, limits, returned rankings, assertion outcomes, and failure diagnostics—not only process exit codes.

## Out of scope

- Changing the consumer project's business Claims.
- Approving or applying the consumer Bundle.
- Weakening retrieval cases to make finalization pass.
- Treating all ranking changes as bugs in retrieval quality; this report concerns evaluator-contract consistency and diagnostics.
- Replacing deterministic lexical retrieval with embeddings.

## Prompt for the PKC developer / coding agent

```text
You are working in the Portable Knowledge Core repository.

Diagnose and fix the divergence between project `knowledge-check` evaluation and `knowledge-plan` delta/full-preflight evaluation. Read `AGENTS.md`, `README.md`, `INSTALL.md`, `docs/QUICKSTART.md`, `docs/SEMANTIC-CHANGES.md`, and `docs/BUG-knowledge-plan-evaluation-contract-drift.md` completely before modifying code. Preserve unrelated dirty work, especially any pre-existing untracked requirement documents. Do not commit unless separately authorized.

Build a tight CLI-level red/green reproduction first. The reproduction must prove all of these current symptoms:

1. camelCase fixture fields are accepted by `knowledge-check` but rejected or misread by semantic-plan evaluation;
2. `knowledge-plan check --mode delta` can return `can_finalize: true` with `affected_case_ids=[]` because `_affected_cases()` uses a different field vocabulary;
3. `knowledge-plan finalize` can fail cases that `knowledge-check` passes because `_run_cases()` ignores alternate search terms, expected Claim IDs, forbidden Claim IDs, configured Top-N defaults, and permission/filter semantics;
4. failures remain fail-closed: no Bundle and no formal Authority mutation.

Do not patch the two evaluators independently. Introduce one canonical evaluation schema normalizer and one canonical deterministic evaluator shared by `experience` and `semantic_plan`. Support documented snake_case and legacy camelCase aliases; reject conflicting dual values with structured errors. Define explicit affected-case scope and a conservative policy for unscoped cases. Ensure delta output cannot silently imply coverage when no cases were selected due to schema mismatch.

Full preflight may be broader than delta, but it must use identical normalized case semantics and must explicitly report deferred cases. Return actionable ranked diagnostics for expected/returned Topic and Claim IDs, forbidden hits, limits, permission, terms, and failed assertion categories.

Write regression tests before the fix at the real CLI seam. Include cases where alternate terms are load-bearing, expected and forbidden Claims are both asserted, and staged ranking changes affect an apparently unrelated query. Then implement the fix and run targeted tests, the complete test suite, build/package checks, and `git diff --check`.

Preserve all governance guarantees: failed evaluation creates no Bundle, formal Authority remains unchanged before exact-hash approval/apply, and committed-baseline/Authority/fact-class/provenance/transaction checks are not weakened.

Finally build a non-editable wheel from the exact fixed commit and report: root cause, semantic contract chosen, changed files, regression tests, full commands/results, version, source commit, wheel SHA-256, and remaining limitations. Do not approve or apply any real consumer Bundle during verification.
```
