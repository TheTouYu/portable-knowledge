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

Check and finalize:

```bash
pkc knowledge-plan check PLAN_ID --mode delta
pkc knowledge-plan finalize PLAN_ID
pkc knowledge-plan inspect PLAN_ID
```

Finalize performs full staged preflight and creates one immutable candidate Bundle only if all checks pass.

## Before approval

Inspect the Bundle:

```bash
pkc bundle-inspect BUNDLE_ID --format json
```

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
pkc bundle-status --format json
```

`bundle-status` takes no positional Bundle ID. Use `bundle-inspect BUNDLE_ID` for one Bundle.

## Fail-closed outcomes

Expected structured rejections include:

- duplicate Claim;
- incomplete Claim fact-class coverage;
- Authority path absent from the committed baseline;
- Authority path also modified by the current plan (`PLAN_AUTHORITY_STAGED_DRIFT`);
- non-current full-preflight Authority status with reference/path/hash diagnostics;
- stale/tampered Bundle hash;
- missing successful full preflight;
- missing approval;
- permission or lifecycle violation.

Treat these as safety results. Do not bypass them with direct files or low-level manifests. Fix the actual input/baseline or abandon the plan:

```bash
pkc knowledge-plan abandon PLAN_ID --reason "Explain why this plan will not continue"
```

## Provenance and no-op checks

A valid production Bundle records Core-generated provenance for each authority-changing action (`add_claim`, `add_authority_ref`, `revise_claim`, or `move_topic`). Bundle type is derived from the operation set: `claim_create`, `claim_revise`, `knowledge_structure_change`, or mixed `knowledge_refactor`. Final review should confirm:

- provenance coverage is complete;
- no unexpected action or changed file exists;
- no no-op action was used to pad a plan;
- Topic relocation contains both the target after-image and old-path deletion;
- `migration_plan` is the deprecated ambiguous name for non-atomic multi-Bundle orchestration; use `bundle_orchestration_plan`/`bundle_migration_plan`. It is not knowledge structure refactoring. `knowledge_structure_refactor` reports the typed move capability;
- prospective changes match the semantic intent;
- pre-apply formal authority is unchanged;
- post-apply changes occur only through the authorized transaction.
