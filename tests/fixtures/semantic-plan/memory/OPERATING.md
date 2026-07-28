# Operating Entry

Use the configured deterministic CLI named by the loaded PKC Skill. This fixture is a neutral semantic-plan contract, not real-project evidence.

## Minimal discovery contract

- Use root help once to confirm the exact high-level CLI entry `knowledge-plan`, then its help once to see the available plan operations. “Semantic plan” is the workflow concept, not a command name: there is no `semantic-plan` alias. Do not probe aliases or unsupported global flags such as `--version`; use `capabilities` only when runtime capability/version evidence is required.
- The task supplies the existing Topic IDs and committed Authority paths. Do not query the projection to rediscover them. `tree` is the read-only fallback when Topic discovery is actually required; normal `query` requires a rebuilt projection and is not part of pre-approval planning.
- When an authorized post-apply verification requires `query`, pass the query text as the positional argument shown by help; there is no `--text` option.
- This operating entry completely specifies the stable arguments needed by the neutral fixture workflow. After root help and `knowledge-plan` help confirm the entry, do not read each nested command's help. If a required argument is genuinely absent from both this contract and the task, stop and report that documentation gap instead of probing or guessing. Reuse IDs directly from the immediately preceding CLI JSON response; do not inspect merely to recover an ID already returned.

## Compact typed argument contract

The public high-level plan interface uses these stable argument shapes; root and `knowledge-plan` help are sufficient capability confirmation, and per-command nested help is unnecessary for this fixture:

- initialize: named options `--intent <text>` and `--risk <low|medium|high>`; use the risk specified by the task, or `medium` when the neutral-fixture task omits one;
- Claim operation: positional plan ID plus named options `--node`, `--topic-id`, `--title`, `--statement`, `--boundary`, optional `--permission`, and repeatable `--fact-class`; creating a Topic additionally requires `--topic-path`, complete Topic metadata, and `--duplicate-resolution create_distinct_with_boundary`; atomically creating its Node also requires complete Node name/path/boundary metadata;
- Authority Reference operation: positional plan ID plus named options `--claim-id`, `--path`, `--locator`, `--role`, `--change-policy`, and repeatable `--fact-class`; allowed roles for this fixture are exactly `documented_contract` and `current_implementation`. `documented_contract` is a role and may also be its supporting fact class; do not substitute a fact-class label such as `fact_class` for `--role`.
- affected-scope check: positional plan ID plus named option `--mode delta`;
- finalize: positional plan ID;
- inspect: positional plan ID.

Every successful JSON response returns the plan ID and current counts; Claim creation also returns its Claim ID. Reuse those returned IDs directly. Finalize returns the Bundle ID, exact content hash, expected changed files, lifecycle summary, and cost counters.

For an explicitly authorized lifecycle transaction, the stable shapes are:

- inspect one immutable Bundle: positional Bundle ID with `bundle-inspect`;
- approve: positional Bundle ID plus required named option `--content-hash <exact-64-char-hash>` and `--apply`; optional actor options are only needed when the task requires an override;
- apply: positional Bundle ID plus required named option `--content-hash <same-exact-hash>` and `--apply`; omitting `--apply` is only a dry-run and does not satisfy an authorized transaction;
- inspect aggregate lifecycle: `bundle-status` takes no positional Bundle ID; use `bundle-inspect <bundle-id>` for one Bundle.

## Semantic-plan execution contract

- Use one plan. Add every requested Claim, then every requested Authority Reference, before running the affected-scope delta check.
- For each Claim, add all Authority References needed to cover every declared fact class. An incomplete set must not be sent to delta as a discovery technique.
- Run delta once after all typed operations are complete, finalize once, then use high-level inspect once to verify the single candidate Bundle and lifecycle.
- Finalize never authorizes approval or apply. Without an exact hash authorization, stop with the Bundle unapproved and unapplied.

Never create orchestration scripts or manifests, use compatibility/maintainer mode, access SQLite or authority files directly, or run Git mutations.
