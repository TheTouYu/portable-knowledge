# Operator Mode Contract 0.1

This reference supplies exact operating boundaries. The Skill remains the natural-language router; `scripts/pkc_operator.py` handles deterministic installation mechanics; the installed PKC CLI handles knowledge semantics and transactions.

## Modes

| Mode | Default risk | Purpose | Default mutation |
|---|---:|---|---|
| inspect | L0 | Detect project/runtime/Memory/Skill state | none |
| install | L1→L2 | Plan, review, then apply technical integration | reviewed plan only |
| first-use | L1→L3 | Bounded discovery and first real knowledge candidates | no automatic authority |
| query | L0 | Memory + L1/L2, targeted L3 | projection only if needed |
| intake | L1→L2 | Preserve and classify real input | reviewed raw-material save |
| capture | L1→L3 | Produce governed knowledge candidates | exact-hash Bundle only |
| memory | L0→L2 | Maintain current/recovery/log; propose high-risk changes | reviewed file diff/proposal |
| maintain | L0→L3 | Find stale/conflict/lifecycle work | diagnosis by default |
| doctor | L0→L4 | Diagnose and repair by reversibility | only R1 automatic |
| upgrade | L1→L2 | Exact-commit parallel runtime switch | reviewed plan only |
| uninstall | L1→L4 | Remove one explicitly selected layer | no authority deletion by default |
| status | L0 | Compact installation/authority/lifecycle status | none |
| approve-apply | L3 | Apply exactly human-reviewed Bundle hash | exact hash only |

## Technical install outputs

A reviewed install plan may create only its declared paths, normally:

```text
.local/pkc/runtimes/<source-commit>/
tools/pkc-lock.json
tools/pkc.py
project-intelligence.json
memory/OPERATING.md
memory/CURRENT.md
memory/DECISIONS.md
data/knowledge/registry.json
data/knowledge/actors.json
data/knowledge/authority-refs.json
data/knowledge/{evidence,proposals,sources}/<writer>.jsonl
knowledge/
skills/<project-id>-knowledge-adapter/SKILL.md
.agents/skills/<project-id>-knowledge-adapter
```

Existing files are preserved unless their exact prior hash and replacement are present in the reviewed plan. For a degraded existing instance with `project-intelligence.json` but no lock, `plan-adopt` may plan only `tools/pkc-lock.json`, `tools/pkc.py`, and the parallel ignored runtime; it preserves configured Memory, Adapter, authority, knowledge, JSONL history, and Bundles. The first implementation does not automatically edit an existing root `AGENTS.md`; it reports the trigger snippet for human placement. This avoids silently changing a project's highest-precedence operating contract.

The neutral initial authority is empty. Do not copy the example Claim into a real project. A novice “install a knowledge tree” request covers technical installation plus an immediate guided first-use offer; it does not authorize invented Claims. Report four independent readiness states: technical install, chosen initial shape, first governed capture, and representative retrieval evaluation.

## Novice natural-language flow

The human does not need to name modes or PKC objects:

- “帮我安装知识树” routes to `install`, then guided `first-use` after reviewed apply.
- “帮我添加知识” routes to `intake`/`capture`; identify pasted material, named committed files, or a commit/range, and ask one concrete input question only when none is identifiable.
- Translate `Claim` as a stable reusable assertion, `Authority Ref` as the committed source that supports it, `Bundle` as the reviewable draft, and `content_hash` as that draft's exact fingerprint. Show canonical names and full hashes at the review gate, but lead with plain language.

Installation creates a minimal default Context and empty authority so it never guesses business facts. Guided first-use proposes 2–3 project-specific tree shapes from the goal, next task, committed truth sources, and privacy boundaries. After a shape is chosen, all real knowledge still enters through exact-hash governed capture. Once real Claims exist, propose 3–5 representative questions and configure retrieval evaluation through a separately reviewed project change; never use synthetic cases as real-project proof.

## Adapter proposal after first use

After first-use confirmation, prepare the project-specific Adapter as ordinary reviewed Markdown, then create a deterministic, read-only proposal:

```bash
python skills/pkc-project-operator/scripts/pkc_operator.py plan-adapter \
  --target /path/to/project \
  --candidate /tmp/reviewed-candidate-SKILL.md \
  --context CONTEXT_ID --node NODE_ID --topic TOPIC_ID \
  --path docs/OPERATING.md \
  --output /tmp/pkc-adapter-plan.json
```

Repeat the reference options as needed. The command validates only declared concrete Context, Node, Topic, and project-path references, the configured Adapter identity, the canonical `python tools/pkc.py` wrapper, and direct mutation prohibitions. It writes only the requested proposal outside the target project. The proposal contains the complete candidate, current/candidate hashes, target Git baseline, `plan_hash`, and `evaluation_status: not_evaluated`; it does not embed a rendered diff. `apply-plan` deliberately rejects this proposal kind. Render and show the exact diff between the configured Adapter and the proposal's complete candidate, show the plan hash to a human, then apply only that reviewed proposal:

```bash
python skills/pkc-project-operator/scripts/pkc_operator.py apply-adapter \
  --plan /tmp/pkc-adapter-plan.json \
  --plan-hash EXACT_PLAN_HASH \
  --human-reviewed
```

`apply-adapter` fails closed on proposal hash, Git state, configured path, current-file hash, or candidate hash drift and replaces only the configured Adapter file. It leaves `evaluation_status: not_evaluated`, evaluation, Git commit/push, Authority, Memory, runtime, and other files separate. Runtime/global-Skill upgrades never replace a project Adapter.

## Coverage-gap proposal after feedback

Convert one explicit, reproducible feedback gap into an external review proposal without changing the owning project:

```bash
python skills/pkc-project-operator/scripts/pkc_operator.py propose-evaluation-case \
  --target /path/to/project \
  --feedback /tmp/feedback-gap.json \
  --output /tmp/evaluation-case-proposal.json \
  --review-output /tmp/evaluation-case-review.txt
```

The schema-version-1 feedback object supplies `gap_id`, `query`, at least one bounded `expected_topic_ids`, `expected_claim_ids`, or `forbidden_claim_ids` assertion, and an optional evidence boundary (`mechanism_only`, `synthetic_fixture`, or `real_project_feedback`). The deterministic proposal remains `not_evaluated`, stays outside the target project, and has no apply or evaluate command. Its proposal hash is a review aid, never a Bundle approval credential. A human separately decides whether to add the case to the owning project's configured evaluation cases. Synthetic fixtures prove mechanism only; proposal generation, static validation, or a generic runner success is not real-project, production, game, or compiler evidence.

After application, a human may separately agree an exact case file containing at least one `capability` and one `boundary` case. Each case must define a task and explicit `final_contains` and/or `final_excludes` assertions. Run the cases in fresh contexts with the exact reviewed case hash:

```bash
python skills/pkc-project-operator/scripts/pkc_operator.py evaluate-adapter \
  --plan /tmp/pkc-adapter-plan.json \
  --plan-hash EXACT_PLAN_HASH \
  --cases /tmp/pkc-adapter-cases.json \
  --cases-hash EXACT_CASES_SHA256 \
  --human-reviewed \
  --provider aijws --model gpt-5.6-luna --thinking medium \
  --output /tmp/pkc-adapter-evaluation.json
```

`evaluate-adapter` requires the exact applied candidate, unchanged planning HEAD, no workspace changes other than that applied Adapter, an output outside the target project, and the human-reviewed case hash. It delegates every case to `isolated-model-evaluator` with only `read,bash`, the Operator and target Adapter explicitly loaded, and `--assert-no-changes`. The independent evaluation record includes case results, tool errors, cost, latency, workspace-change status, Adapter hash, case hash, and model profile. Its status is `evaluated` only when every agreed case exits successfully, the runner reports `ok`, no tool errors or workspace changes occur, and all explicit final-answer assertions pass; otherwise it remains `not_evaluated`. The immutable proposal itself remains `not_evaluated`.

This label proves only that the exact Adapter hash passed the exact isolated cases with the exact model profile. Static validation, successful application, a synthetic fixture, generic runner `ok`, or one model answer is not real-project, production, game, compiler, or other real-environment evidence. Do not add an Adapter DSL, infer project facts, update root `AGENTS.md`, mutate Authority or Memory, run evaluation during proposal/application, or commit traces by default.

## Project wrapper

Only the tracked wrapper is canonical in a configured project:

```bash
python tools/pkc.py capabilities
python tools/pkc.py validate
python tools/pkc.py rebuild
python tools/pkc.py query "question" --level 2
```

It resolves the project root, reads `tools/pkc-lock.json`, verifies runtime location/version, removes source-checkout `PYTHONPATH`, and forwards arguments. It never downloads, upgrades, or falls back to a system runtime.

## Exact upgrade flow

Install initializes an unconfigured project; adopt locks an existing unlocked instance; upgrade changes an already locked project's exact runtime selection. They are not substitutes.

```bash
python skills/pkc-project-operator/scripts/pkc_operator.py plan-upgrade \
  --target /path/to/project \
  --source-repository /path/or/url/to/portable-knowledge \
  --source-commit EXACT_40_CHARACTER_COMMIT \
  --representative-query "bounded project question" \
  --project-check "project test command" \
  --output /tmp/pkc-upgrade-plan.json
python skills/pkc-project-operator/scripts/pkc_operator.py apply-plan \
  --plan /tmp/pkc-upgrade-plan.json --plan-hash EXACT_HASH --human-reviewed
```

Planning may build/cache a wheel from a clean export of the exact commit but does not change the target. The reviewed upgrade updates the lock and synchronizes only `project-intelligence.json.pkc.version` when its declared version differs; all other instance configuration and the project Adapter remain unchanged. Builder preflight reports `uv`, or the fallback requirements `venv` + `pip` + `build`, and fails actionably before target changes when neither backend is usable. Wheel provenance comes from inspected `dist-info/METADATA`, an isolated install's package version and capabilities, the exact source commit, and SHA-256—not the filename alone. Its payload identifies current/target commit and version, source dirtiness, interpreter/ABI/builder, wheel and SHA-256, current/target capabilities and their deterministic difference, lock before/after hashes, parallel and rollback runtimes, checks, exclusions, and plan hash. Apply fails on drift or runtime-version mismatch and installs non-editably. After a post-switch failure it restores the prior lock selection, preserves the rollback runtime, moves the failed candidate under ignored `.local/pkc/failed-runtimes/` without overwriting earlier diagnostics, and records the actual retained paths in an actionable receipt under `.local/pkc/operator-receipts/`. Releasing the canonical target path lets a newly reviewed plan rebuild from the verified wheel instead of trusting a partially verified runtime. For the narrow bootstrap case where the stricter target runtime is required to refresh pre-existing invalid Authority References, add `--defer-knowledge-check-for-authority-maintenance`: planning fails unless the target advertises `authority_ref_refresh_plan`, records `knowledge-check` as deferred, and requires an immediate reviewed Authority-maintenance Bundle followed by that check. Other technical verification remains mandatory. Runtime/config review remains separate from knowledge Bundle and Git review.

## Exact semantic change flow

```bash
python tools/pkc.py knowledge-plan init --intent "..." --risk medium
python tools/pkc.py knowledge-plan add-claim PLAN_ID \
  --node NODE --topic-id TOPIC --topic-path knowledge/topic.md \
  --title "..." --statement "..." --boundary "..." \
  --permission internal --fact-class runtime_behavior
# For a new Topic, also provide its title/summary/keywords and explicitly use:
#   --duplicate-resolution create_distinct_with_boundary
# For a new Node + first Topic + first Claim, additionally provide complete:
#   --node-name ... --node-path knowledge/node --node-boundary ... [--node-keyword ...]
# Existing knowledge maintenance can instead/additionally use:
python tools/pkc.py knowledge-plan revise-claim PLAN_ID \
  --claim-id CLAIM_ID --title "Corrected title" \
  --statement "Corrected assertion." --boundary "Exact boundary." \
  --semantic-declaration correct --reason "Verified reason"
python tools/pkc.py knowledge-plan move-topic PLAN_ID \
  --topic-id TOPIC_ID --to-node TARGET_NODE \
  --to-path knowledge/target/topic.md --reason "Lifecycle boundary changed"
# For atomic target-Node creation, move-topic also requires complete
# --node-name, --node-path, and --node-boundary metadata.
python tools/pkc.py knowledge-plan update-topic PLAN_ID \
  --topic-id TOPIC_ID --title "Retuned title" \
  --summary "Bounded routing summary" --keyword schema --alias 契约 \
  --reason "Improve retrieval without rewriting Claims"
python tools/pkc.py knowledge-plan add-authority-ref PLAN_ID \
  --claim-id CLAIM_ID --path src/module.py --locator "function:name" \
  --role current_implementation --change-policy invalidate_on_change \
  --fact-class runtime_behavior
python tools/pkc.py knowledge-plan update-authority-ref PLAN_ID \
  --authority-ref-id AREF_ID --path src/new-file.py --locator "function:name" \
  --reason "The rule moved to a new file"
python tools/pkc.py knowledge-plan refresh-authority-ref PLAN_ID --all-stale \
  --reason "Committed sources changed and were reviewed"
python tools/pkc.py knowledge-plan check PLAN_ID --mode delta
python tools/pkc.py knowledge-plan finalize PLAN_ID
python tools/pkc.py knowledge-plan finalize PLAN_ID --defer-evaluation CASE_ID  # escape hatch for a known-failing case
python tools/pkc.py bundle-inspect BUNDLE_ID --format json
```

Inspect and show the Bundle ID without abbreviation, the complete immutable 64-character `content_hash`, semantic difference, Authority/evidence basis, exclusions, permission effect, risk, and exact changed files. Stop. A generic “continue/agree” is not approval; only a real human confirmation naming that exact displayed hash authorizes approval and application. `--content-hash` on approve/apply is optional: it auto-resolves from the verified immutable Bundle (verify_bundle recomputes the canonical hash, so it cannot be weakened); a supplied hash must still match exactly or the operation fails closed. After that confirmation:

```bash
python tools/pkc.py bundle-approve BUNDLE_ID --apply
python tools/pkc.py bundle-apply BUNDLE_ID --apply
python tools/pkc.py rebuild
python tools/pkc.py validate
python tools/pkc.py tree --format text
python tools/pkc.py query "representative question" --level 2
# Run the target project's configured retrieval evaluation/knowledge-check.
python tools/pkc.py knowledge-check --eval-coverage
python tools/pkc.py bundle-inspect BUNDLE_ID --format json
git diff --check
git status --short --branch
```

Post-apply checks prove Bundle lifecycle, text authority, projection, routing, and configured retrieval expectations only. Report evidence as separate layers: current source implementation; automated tests; generated/decoded GIA or equivalent artifact; editor import/loading; writeback/injection; and in-game behavior. Never promote one layer as proof of a later layer.

Use `add-claim` for new knowledge, `revise-claim` for correction, `move-topic` for ownership/path refactoring, and `update-topic` to retune Topic retrieval metadata without rewriting Claim bodies. A finalized-but-not-applied plan whose committed baseline advanced can be recovered with `knowledge-plan rebase PLAN_ID --reason ...` (operations and Claim identity are preserved, the stale candidate Bundle is discarded, then re-check/re-finalize); a plan with an approval or apply record stays immutable. Batch capture (`capture --file DRAFT.json`) supports Markdown drafts (`--draft-format markdown`) and `--preview-only` to show the exact candidate semantic_diff without finalizing; the field-level DRAFT schema with a minimal example is `references/capture-draft-format.md`. Topic metadata (`topic_title`/`topic_summary`/`topic_keywords`) is only valid when creating a new topic — for a second claim on the same topic pass only `topic_id`. Multi-Bundle orchestration (`bundle_migration_plan`, formerly the ambiguous `migration_plan`) is non-atomic across phases and is not structure migration.

Valid Authority roles are `design_intent`, `current_implementation`, `documented_contract`, and `external_environment_behavior`. Valid fact classes are `runtime_behavior`, `public_type_surface`, `cli_behavior`, `documented_contract`, `external_game_evidence`, `transform_defaults`, `writeback_behavior`, and `evidence_scope`. A role and a fact class are different controlled vocabularies. `bundle-status [bundle-id]` supports aggregate or single-Bundle status. Query text is positional; there is no `--text` option.

Change-policy semantics (2026-08-29 real hit): `manual_review` Refs are **permanently non-current** — a plan that touches their linked Claims is always blocked at finalize by `PLAN_FULL_AUTHORITY_NOT_CURRENT (plan_affected)`, so never use `manual_review` for a freshly committed document; use `review_on_change` or `invalidate_on_change`. `progressive-query` returns its matches under the `claims` key (the `results` key exists only on `knowledge-search`/`query`). After applying a runtime upgrade with `apply-plan`, smoke-test the exact commands the batch will run next (e.g. `update-topic --keyword`, `capture --preview-only`) — capabilities/validate/rebuild/knowledge-check do not cover feature-level regressions (2026-08-29: update-topic keyword-only crash shipped past the upgrade checks).

## Evaluation fixture governance (R11, 2026-08-29)

Evaluation failures (`PLAN_EVALUATION_FAILED` / `PLAN_FULL_EVALUATION_FAILED` / `PLAN_POST_APPLY_EVALUATION_FAILED`) now carry per-case detail in the finding: `query`, `returned_topics` (rank + score), `returned_topic_ids`, `expected_topic_ids` / `expected_claim_ids`, `topic_top_n` / `claim_top_n`, and `failed_assertions`. Read that detail first — it names exactly which topic was returned at which rank and what the top-N assertion expected, so the fix choice is evidence-based instead of guesswork.

When new knowledge legally changes the retrieval landscape (semantic overlap: the new claim is itself a legitimate answer to the case's query), the fix ladder is, in order:

1. **Topic metadata** (`update-topic`: keywords to de-compete) — the official lever;
2. **Claim title wording** (`revise-claim`: clarify the declaration, never its body semantics);
3. **Evaluation fixture update** (`expected_topic_ids` gains the new legitimate topic) — the last resort.

Fixtures are tracked config, so a fixture change goes through the same governed path as any knowledge change: build it as a Bundle (e.g. the real 2026-08-29 case `bnd_253802ff`), show the exact before/after `expected_topic_ids` diff for the affected case, get human L3 approval on the Bundle's exact content hash, then apply and confirm with a full `knowledge-check` run (all cases green). Semantic assertions stay unchanged — only the top-N membership grows. Never delete or weaken a claim's body to satisfy retrieval; that trades governed knowledge for a green case.

Post-apply gate scope note (R10): after a Bundle applies, every configured case runs, but only cases whose `affected_by` intersects the plan's touched nodes/topics/claims can block; disjoint failures surface as non-blocking `PLAN_EVALUATION_NON_BLOCKING` warnings. A post-apply failure still reports the transaction state (applied, not rolled back) — `exit 1 ≠ transaction failed`; verify with `bundle-status` and fix with the ladder above, never by redoing the apply.

## Human review language

A valid review names the object shown immediately before it:

- install/config repair/upgrade: plan hash;
- Domain Knowledge: Bundle ID and exact content hash;
- Memory: listed paths and shown diff;
- Git: staged paths and destination;
- deletion: inventory and selected layer.

A generic “do everything” is not durable authorization for future objects. The operator should ask for one compact confirmation, not introduce role/ACL bureaucracy.

## Existing vs Greenfield

Existing Project readiness:

- project goal exists;
- one primary production task can be named;
- at least one real truth source exists;
- Memory roles can be mapped or minimally supplied;
- sensitive/remote-processing boundaries can be stated.

If these are absent, produce a Greenfield readiness checklist only. Do not initialize business authority.

## Intake handler contract

A project Adapter may declare handlers for transcripts, screenshots, documents, pasted text, or other domain formats. The Operator invokes an existing handler; it does not pretend to support a format. Before remote model use or persistence, separate permission for save, internal reuse, remote processing, and publication.

## Verification labels

Use only:

- `designed`
- `locally_tested`
- `real_environment_verified`
- `unsupported`

As of contract 0.1, Arch Linux + Pi may be tested first. Do not upgrade Windows/macOS/Claude/Codex labels without actual evidence.
