# Governed Semantic Changes

Use this workflow for normal production Claim and Authority Reference ingestion. It is designed to keep semantics, provenance, validation, approval, and application auditable.

## Non-negotiable rules

- Use only the installed `pkc` CLI.
- Use `knowledge-plan`; there is no `semantic-plan` alias.
- Do not use Python APIs, shell-generated JSON manifests, direct Markdown/registry writes, SQLite, `bundle-create --manifest`, or compatibility mode.
- Preserve uncommitted work and require Authority paths to exist in the committed baseline.
- Add all intended Claims and Authority Refs before the delta check.
- Run delta once after the plan is complete, then finalize once.
- Approval authorizes only the displayed immutable 64-character content hash.
- Changed content invalidates approval.
- Installation or synthetic validation is not real-project evidence.

## Typed CLI contract

Global options go before `knowledge-plan`:

```bash
pkc --root /path/to/project knowledge-plan ...
```

Initialize:

```bash
pkc knowledge-plan init --intent "Describe the bounded semantic change" --risk medium
```

Add a Claim:

```bash
pkc knowledge-plan add-claim PLAN_ID \
  --node NODE_ID \
  --topic-id TOPIC_ID \
  --topic-path domain/topics/topic.md \
  --title "Claim title" \
  --statement "One stable, atomic assertion." \
  --boundary "When this claim applies and what it does not prove." \
  --permission internal \
  --fact-class runtime_behavior
```

`--topic-path` may be omitted when the Topic already exists. Repeat `--fact-class` when the Claim requires multiple controlled fact classes.

To atomically create a distinct Topic with its first Claim, provide complete Topic metadata and explicitly acknowledge the distinct semantic boundary:

```bash
pkc knowledge-plan add-claim PLAN_ID \
  --node EXISTING_NODE_ID \
  --topic-id NEW_TOPIC_ID \
  --topic-path knowledge/existing-node/new-topic.md \
  --topic-title "New Topic" \
  --topic-summary "Bounded routing summary" \
  --topic-keyword routing \
  --duplicate-resolution create_distinct_with_boundary \
  --title "First Claim" \
  --statement "One stable, atomic assertion." \
  --boundary "When this claim applies and what it does not prove." \
  --permission internal \
  --fact-class documented_contract
```

To create a Node, its first Topic, and its first Claim as one governed operation, additionally provide `--node-name`, `--node-path`, and `--node-boundary`; `--node-keyword` is repeatable. A new Topic path must remain under its Node path. Node or Topic metadata supplied for an existing object is rejected rather than silently ignored. Empty Nodes and Topics are not created independently.

Revise an existing Claim without changing its ID, Topic, permission, Authority links, or history:

```bash
pkc knowledge-plan revise-claim PLAN_ID \
  --claim-id CLAIM_ID \
  --title "Corrected bounded title" \
  --statement "Corrected atomic assertion." \
  --boundary "Exact scope and exclusions." \
  --semantic-declaration correct \
  --reason "Verified evidence narrows the former wording"
```

Declarations are `clarify`, `correct`, `narrow`, or `expand`. `correct` and `expand` fail closed without Authority fact-class coverage; `expand` should use high risk. Revision appends a `claim_revised` event with before/after hashes.

Move an existing Topic and all of its stable-ID Claims to an existing Node:

```bash
pkc knowledge-plan move-topic PLAN_ID \
  --topic-id EXISTING_TOPIC \
  --to-node TARGET_NODE \
  --to-path knowledge/target/existing-topic.md \
  --reason "The Topic has a distinct lifecycle and Authority boundary"
```

If the target Node does not exist, the same operation may create it atomically by also supplying complete `--node-name`, `--node-path`, `--node-boundary`, and optional repeatable `--node-keyword` metadata. `--to-path` is always explicit and must remain under the target Node path. The old Markdown path is deleted in the same transaction; Topic ID, Claim IDs, Authority References, and prior events are preserved. Empty source Nodes are warned about, not implicitly deleted.

Add an Authority Reference:

```bash
pkc knowledge-plan add-authority-ref PLAN_ID \
  --claim-id CLAIM_ID \
  --path src/module.py \
  --locator "function:run" \
  --role current_implementation \
  --change-policy invalidate_on_change \
  --fact-class runtime_behavior
```

Valid Authority roles:

- `design_intent`
- `current_implementation`
- `documented_contract`
- `external_environment_behavior`

Valid fact classes:

- `runtime_behavior`
- `public_type_surface`
- `cli_behavior`
- `documented_contract`
- `external_game_evidence`
- `transform_defaults`
- `writeback_behavior`
- `evidence_scope`

A role classifies what proposition the reference can establish; a fact class names the specific machine/evidence surface covered. Do not substitute one vocabulary for the other.

Common change policies:

- `existence_only`
- `review_on_change`
- `invalidate_on_change`
- `manual_review`

The path must exist in the committed baseline. Use the Claim ID returned by `add-claim`; do not invent one. An Authority Reference may not point to a path also modified by the same plan: delta rejects this as `PLAN_AUTHORITY_STAGED_DRIFT`. New references bind only to committed-baseline hashes; PKC does not infer a staged self-reference or silently approve an after-image.

The Authority Reference registry's canonical array key is `refs`. The legacy `authority_refs` key is accepted as an input alias and normalized to `refs` on the next governed write. Registries containing both keys with different values fail closed as `AUTHORITY_REFS_SCHEMA`.

Refresh an existing change-sensitive Authority Reference after its governed source changes:

```bash
pkc knowledge-plan refresh-authority-ref PLAN_ID \
  --authority-ref-id AUTHORITY_REF_ID \
  --reason "The committed implementation changed and the linked Claims were reviewed"
```

Refresh preserves the Ref ID, path, locator, Claim links, role, fact classes, baseline state, and change policy. The path must exist in the plan's committed baseline and the worktree bytes must exactly match that baseline. The operation fails on a no-op. Its immutable audit event and Bundle diff record the old and new approved hashes and affected Claim IDs. A refreshed Ref participates in the same atomic Bundle as Claim additions/revisions and other typed operations.

Retire a Ref that no longer applies:

```bash
pkc knowledge-plan retire-authority-ref PLAN_ID \
  --authority-ref-id OLD_AUTHORITY_REF_ID \
  --replacement-authority-ref-id NEW_AUTHORITY_REF_ID \
  --reason "The new contract is now the canonical Authority"
```

Use `--replacement-claim-id CLAIM_ID` instead when a replacement Claim, rather than another Ref, owns the new boundary. Exactly one replacement kind may be supplied. PKC requires an explicit reason and an existing, distinct replacement. The active registry removes the retired Ref, while an immutable `authority_ref_retired` event retains its complete before-image, affected Claim IDs, reason, and replacement link. Delta validation still enforces fact-class coverage after retirement.

Check and finalize:

```bash
pkc knowledge-plan check PLAN_ID --mode delta
pkc knowledge-plan finalize PLAN_ID
pkc knowledge-plan inspect PLAN_ID
```

Finalize performs full staged preflight and creates one immutable candidate Bundle only if all checks pass. Delta and full preflight share the configured evaluation normalizer and evaluator. Delta runs unscoped cases conservatively and may defer only explicitly scoped, non-intersecting cases; its JSON artifact records selected/deferred cases and reasons. Full preflight runs every case. Evaluation failures expose a bounded artifact path containing normalized inputs, ranked Topic/Claim results, limits, permission, forbidden hits, and failed assertion categories.

## File-driven batch capture

For reusable, one-command Claim intake, `knowledge-plan capture --file DRAFT.json` runs the exact same typed pipeline — `init`, every `add-claim` and `add-authority-ref`, one delta `check`, one `finalize` — and stops with an immutable draft Bundle for human review. It never approves, applies, or commits anything, and it never uses `bundle-create --manifest`, compatibility mode, or direct authority writes. One command covers any number of Claims and Authority Refs.

Draft contract (`schema_version` must be `1`):

```json
{
  "schema_version": 1,
  "intent": "Describe the bounded semantic change",
  "risk": "medium",
  "claims": [
    {
      "id": "schema",
      "node": "software-core",
      "topic_id": "topic-schema",
      "topic_path": "knowledge/software-core/schema.md",
      "topic_title": "Schema Contract",
      "topic_summary": "Bounded routing summary",
      "topic_keywords": ["schema"],
      "node_name": "Software Core", "node_path": "knowledge/software-core", "node_boundary": "...",
      "node_keywords": ["core"],
      "title": "Schema input is explicit",
      "statement": "One stable, atomic assertion.",
      "boundary": "When this claim applies and what it does not prove.",
      "permission": "internal",
      "duplicate_resolution": "cancel",
      "fact_classes": ["documented_contract"],
      "authority_refs": [
        {
          "claim_id": "schema",
          "path": "src/module.py",
          "locator": "function:run",
          "role": "current_implementation",
          "change_policy": "invalidate_on_change",
          "fact_classes": ["runtime_behavior"]
        }
      ]
    }
  ]
}
```

- `claims[].id` is an optional local alias used by `authority_refs[].claim_id`; without either, a Ref binds to its enclosing Claim. Duplicate ids and unknown `claim_id` references are draft errors.
- Topic/Node metadata fields (`topic_path`, `topic_title`, `topic_summary`, `topic_keywords`, `node_name`, `node_path`, `node_boundary`, `node_keywords`) are optional and only valid when atomically creating that object, exactly as in `add-claim`.
- Ref `fact_classes` must be declared by the target Claim; `role`, `change_policy`, `permission`, and `duplicate_resolution` use the same controlled vocabularies as the typed CLI. Unknown fields are rejected so typos fail loudly.
- Authority documents must be committed before capture (same committed-baseline rule as `init`).

Output (JSON and text) reports plan ID, Bundle ID, the exact 64-character content hash, semantic diff, expected changed files, risk, permission effect, and every validation failure. Draft errors name the exact field (`claims[2].authority_refs[0].role`). Any failure after plan creation abandons the plan with a stated reason and never leaves a partial Bundle; the `retained_plan` field reports the abandoned plan id, state, and reason. Re-running the same draft after a successful capture replays the identical Bundle.

Inspect the Bundle and stop for exact-hash human review exactly as for interactive plans:

```bash
pkc bundle-inspect BUNDLE_ID --format json
```

## Before approval

Inspect the Bundle:

```bash
pkc bundle-inspect BUNDLE_ID --format json
```

For compatibility, JSON inspection always returns Bundle records under `bundles`; inspecting one ID uses `bundles[0]`. Each record separates immutable action targets in `expected_changed_files` from the Bundle, approval, and application receipt paths in `lifecycle_files`.

Present to the human:

- semantic difference;
- evidence and Authority basis;
- exclusions and unverified facts;
- permission effect;
- expected changed files;
- risk;
- Bundle ID;
- full exact content hash;
- whether it is currently approved or applied.

Stop. Do not approve or apply without explicit authorization for that exact hash.

## Exact-hash approval and apply

After explicit authorization:

```bash
pkc bundle-approve BUNDLE_ID --content-hash EXACT_64_CHAR_HASH --apply
pkc bundle-apply BUNDLE_ID --content-hash EXACT_64_CHAR_HASH --apply
```

Then verify:

```bash
pkc rebuild
pkc validate
pkc query "representative question" --level 2 --format json
pkc bundle-inspect BUNDLE_ID --format json
pkc bundle-status BUNDLE_ID --format json
```

`bundle-status [BUNDLE_ID]` supports either aggregate lifecycle listing or one Bundle. `bundle-inspect BUNDLE_ID` remains the richer semantic review surface.

`knowledge-plan inspect` classifies non-current Authority References as `plan_affected` or `historical`. Refs affected by the current plan (staged paths or touched Claims) remain fail-closed blockers. Unrelated historical refs are reported as non-blocking maintenance warnings: finalize still completes while the preview lists their IDs, status, and hashes and recommends a dedicated `authority_maintenance` plan. After that Bundle is exact-hash approved and applied, a human must authorize committing the maintenance, then abandon and rebuild plans that depended on the old Authority snapshot; uncommitted maintenance is never accepted as a baseline.

## Fail-closed outcomes

Expected structured rejections include:

- duplicate Claim;
- incomplete Claim fact-class coverage;
- Authority path absent from the committed baseline;
- Authority path also modified by the current plan (`PLAN_AUTHORITY_STAGED_DRIFT`);
- non-current full-preflight Authority status for plan-affected References (staged paths or touched Claims) with reference/path/hash diagnostics — unrelated historical non-current References are non-blocking warnings;
- stale/tampered Bundle hash;
- missing successful full preflight;
- missing approval;
- permission or lifecycle violation.

Treat these as safety results. Do not bypass them with direct files or low-level manifests. Fix the actual input/baseline or abandon the plan:

```bash
pkc knowledge-plan abandon PLAN_ID --reason "Explain why this plan will not continue"
```

## Provenance and no-op checks

A valid production Bundle records Core-generated provenance for each authority-changing action (`add_claim`, `add_authority_ref`, `refresh_authority_ref`, `retire_authority_ref`, `revise_claim`, or `move_topic`). Bundle type is derived from the operation set: `claim_create`, `claim_revise`, `knowledge_structure_change`, or mixed `knowledge_refactor`. Authority-only maintenance uses the controlled `authority_maintenance` Bundle type; mixed plans retain the Claim/structure-derived envelope while typed semantic diff and action provenance identify refresh/retirement precisely. Final review should confirm:

- provenance coverage is complete;
- no unexpected action or changed file exists;
- no no-op action was used to pad a plan;
- Topic relocation contains both the target after-image and old-path deletion;
- `migration_plan` is the deprecated ambiguous name for non-atomic multi-Bundle orchestration; use `bundle_orchestration_plan`/`bundle_migration_plan`. It is not knowledge structure refactoring. `knowledge_structure_refactor` reports the typed move capability;
- prospective changes match the semantic intent;
- pre-apply formal authority is unchanged;
- post-apply changes occur only through the authorized transaction.
