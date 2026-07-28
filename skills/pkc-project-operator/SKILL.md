---
name: pkc-project-operator
description: Install, initialize, use, maintain, repair, upgrade, and safely remove Portable Knowledge Core in existing projects. Use when a user asks to install or configure a project knowledge tree/PKC, query project knowledge, save and distill material, capture reusable knowledge, maintain Project Memory, inspect stale/conflicting knowledge, diagnose PKC, upgrade it, review/apply a knowledge Bundle, run first-use setup, or remove an installation without deleting project authority.
compatibility: Python 3.11+, Git, and an Agent Skills-compatible harness. Linux/Pi is initially verified; Windows, macOS, Claude Code, and Codex support is designed but requires real-environment verification.
metadata:
  operator-contract: "0.1"
  pkc-repository: "https://github.com/TheTouYu/portable-knowledge.git"
---

# PKC Project Operator

Be the single human-facing operator for a project's Portable Project Intelligence lifecycle. Installation is one mode, not the product. Delegate deterministic knowledge semantics, validation, permissions, immutable Bundles, and transactions to the installed PKC Core; never reimplement them in this Skill or a project Adapter.

Resolve all relative paths from this Skill directory. For mechanical operations use `scripts/pkc_operator.py`. Read [the mode contract](references/MODES.md) for any mode beyond a simple read-only status/query. Read the target repository's own operating rules before proposing changes.

## Start every invocation

Declare, in one compact block:

```text
mode: inspect | install | first-use | query | intake | capture | memory | maintain | doctor | upgrade | uninstall | status | approve-apply
risk: L0 | L1 | L2 | L3 | L4
project_state: unconfigured | configured | degraded | unknown
```

Then run the smallest required inspection. Declare this block before the first project tool call. Ordinary mechanical edits that do not involve project intelligence do not trigger this Skill.

## Human Review Gate

Do not build an identity bureaucracy. One real human review is sufficient, but a model may never review its own proposal.

- **L0:** read-only inspect/query/status/diagnosis; proceed.
- **L1:** generate projection, immutable plan, candidate Bundle, or recommendation; do not alter tracked authority.
- **L2:** install/repair runtime, save material, or change tracked configuration; first show exact files/source/hash and obtain human confirmation.
- **L3:** change formal knowledge authority; show semantic diff and full immutable Bundle hash, then require human confirmation of that exact hash.
- **L4:** Git commit/push, remote/release, destructive deletion, or publication; require separate explicit confirmation.

A prior installation, material, or Git approval never authorizes a later knowledge Bundle. Changed plan or Bundle content invalidates review.

## Canonical mechanical interface

```bash
python scripts/pkc_operator.py inspect --target /path/to/project
python scripts/pkc_operator.py plan-install --target /path/to/project --output /tmp/pkc-install-plan.json
python scripts/pkc_operator.py plan-adopt --target /path/to/project --output /tmp/pkc-adopt-plan.json
python scripts/pkc_operator.py plan-upgrade --target /path/to/project \
  --source-repository /path/or/url/to/portable-knowledge --source-commit EXACT_COMMIT \
  --output /tmp/pkc-upgrade-plan.json
python scripts/pkc_operator.py apply-plan --plan /tmp/pkc-install-plan.json --plan-hash EXACT_HASH --human-reviewed
python scripts/pkc_operator.py status --target /path/to/project
python scripts/pkc_operator.py doctor --target /path/to/project
python scripts/pkc_operator.py check-update --target /path/to/project
```

`plan-install` initializes an unconfigured project. `plan-adopt` adds a lock and wrapper to an existing unlocked instance while preserving its Memory, Adapter, authority, and history. `plan-upgrade` is the only upgrade planner for an already locked project; install/adopt are not upgrade substitutes. It exports the requested exact commit, records build environment and wheel provenance, proposes a parallel runtime and lock-only switch, names the rollback runtime and post-switch checks, and reports dirty source bytes without including them. Planning may cache a wheel outside the target but may not change the target project. Present the complete summary and `plan_hash`; only then may `apply-plan` run. Environment, wheel, target-file, Git-state, or plan drift must fail closed and require a new plan.

Default remote:

```text
https://github.com/TheTouYu/portable-knowledge.git
```

Never install a moving `main` without recording the resolved commit. Never use editable installs, `PYTHONPATH`, a system fallback, or an unverified wheel. Project runtime belongs under ignored `.local/pkc/runtimes/<commit>/`; tracked `tools/pkc-lock.json` records source commit and wheel SHA-256; tracked `tools/pkc.py` is the canonical project entry.

## Install / initialize

Use two stages:

1. **L1 inspect and plan:** protect dirty work, detect existing PKC/Memory/Skill systems, map existing operating/current/decision docs in place, list every write/link/exclusion, resolve exact remote commit, cache wheel, and show plan hash.
2. **L2 reviewed apply:** apply only that plan hash, install a non-editable project runtime, create lock/wrapper/thin Adapter and only missing minimal authority/Memory assets, then run capabilities, validate, rebuild, validate, and report tracked diff. Never commit.

If multiple Skill truth sources, instance configs, or same-name Adapters conflict, stop. Existing projects are supported. For true Greenfield projects create only a readiness proposal; do not invent Nodes, Topics, Claims, goals, or business facts.

After technical installation, offer `first-use`; do not start it automatically.

## First use

Confirm project goal, one primary production task, real truth sources, sensitive-data boundaries, and mapped Memory roles. Read bounded entry files, propose 2–3 non-authoritative structures, and let the human choose. Empty Domain Knowledge is valid. Do not scan the whole repository or copy facts from examples/Domain Packs. Any real Claim/Authority change follows `capture` and L3 exact-hash review.

## Query and task routing

For complex diagnosis, architecture/domain changes, historical constraints, cross-file judgments, real-environment evidence, permissions, or knowledge maintenance:

```text
project operating/current/decision entries
→ choose one Primary Context
→ project wrapper capabilities/validate
→ bounded Memory
→ Knowledge L1/L2
→ L3/show-claim only for exact boundaries
```

In a configured project, use a fixed bounded startup—do not run `find`, `rg --files`, or directory scans to discover entries:

1. read root `AGENTS.md` and `project-intelligence.json` directly;
2. read exactly the actual paths listed by `memory.roles` (one role may map to multiple paths), once each;
3. read the configured project Adapter only when the task triggers it;
4. use the project wrapper for validate and retrieval.

Never guess conventional paths such as `memory/OPERATING.md`, `memory/CURRENT.md`, or `memory/DECISIONS.md`. Do not read generic README, navigation, source, output, or historical files unless a bounded result explicitly requires one. For a direct business query, stop retrieval when L1 routes to the relevant Topic and L2 supplies enough Claims and boundaries. Use `show-claim` only when exact Authority/evidence status is needed; do not issue adjacent exploratory queries unless the result is insufficient, and explain that expansion.

Use `python tools/pkc.py ...`, never a global/system `pkc`. A bounded miss is not repository-wide absence. Ordinary mechanical work defaults to no query.

## Intake and capture

Before distillation: sensitive-data precheck → permission for save/internal reuse/remote processing/publication → deduplicate → preserve raw material or external locator → delegate to a project-declared handler → retrieve existing knowledge → classify exactly one primary result:

```text
discard | source-only | evidence | new claim | revise
```

Unknown permission stops. Unsupported formats do not produce partial archives. `source-only` and `discard` are successful closures. Keep raw material, Evidence, Claim, Authority Reference, and Project Memory in separate truth sources.

For Domain Knowledge use only installed high-level PKC `knowledge-plan` operations. Use `add-claim` for new knowledge, `revise-claim` to correct/clarify an existing proposition, and `move-topic` to change an existing Topic's Node/path while preserving IDs, Authority links, and history. Every new or semantically expanded Claim needs fact-class coverage: use `add-authority-ref` with the Claim ID returned by the plan before the final delta. It is valid for that purpose-scoped Ref to use a source path already used by another Ref when its Claim link, locator, or fact boundary is distinct; do not omit required coverage merely to avoid a shared path. `refresh-authority-ref PLAN_ID --authority-ref-id ID --reason REASON` only re-approves a changed committed source and deliberately preserves the existing Ref's identity and Claim links—it does not attach a new Claim. Use `retire-authority-ref PLAN_ID --authority-ref-id ID (--replacement-authority-ref-id ID | --replacement-claim-id ID) --reason REASON` when a Ref no longer applies. These operations may share one immutable Bundle. Execute mutations of one plan serially; concurrent commands against the same plan are unsupported. Run exactly one final `check PLAN_ID --mode delta`, then `finalize PLAN_ID`; full staged preflight can identify additional non-current Refs that delta intentionally did not inspect. Review those findings rather than bypassing them or blindly refreshing unrelated Authority.

The target repository may not contain PKC's maintainer-only `docs/SEMANTIC-CHANGES.md`; do not guess or attempt to read that path when absent. This Skill and [the mode contract](references/MODES.md) are the portable operator contract. Multi-Bundle orchestration (`bundle_migration_plan`, historically `migration_plan`) is not knowledge structure migration. No Python APIs, shell manifests, direct JSON/Markdown authority writes, SQLite, `bundle-create --manifest`, or compatibility mode.

A vague request to "record/add this batch" does not imply that the input is new raw material. When it names a Node or batch and current/recovery Memory identifies a pending legacy-to-governed migration, treat committed legacy Knowledge as the saved input. Use `tree` to resolve the Node path, list only tracked direct files there, and inspect the smallest set that forms one coherent Topic; do not use a README/navigation link or shared Node membership to pull in an adjacent independent subject. Run L1→L2 deduplication, then determine the complete Claim set, matching Authority Refs, roles/fact classes/change policies, and required `add-claim` options before initializing the plan. Add every Claim and Ref serially, run exactly one delta check, finalize once, inspect the Bundle, and stop for its exact-hash review. Do not scan or enumerate `materials/`, `outputs/`, or the repository for another input unless the named scope and Memory cannot identify one; if still ambiguous, ask the human. Pre-existing tracked or untracked dirty paths are protected parallel work, not implicit intake input. At startup record only their path names and baseline status; do not enumerate a dirty directory or read its contents. A vague named Node/batch request does not authorize dirty-file access: only the human prompt or recovery Memory explicitly naming that dirty path may do so. Their presence never overrides an identified Node/batch scope, whose input comes from the tracked configured Knowledge path. A working-tree-only file cannot become Authority: preserve it and request a committed baseline rather than bypassing the Authority gate.

Do not pass `status` to the project PKC wrapper: use `scripts/pkc_operator.py status` for project/runtime state and `python tools/pkc.py bundle-status` for Bundle lifecycle.

## Memory

Operate Project Memory and Domain Knowledge through one entry but separate candidates and review:

- current phase/next action/blocker → current/recovery;
- completed milestone → project log;
- future operating choice → Decision proposal;
- reusable bounded judgment → Domain Claim;
- machine truth → Authority Reference;
- durable observation → Source/Evidence;
- temporary observation → working note only.

Routine recorded facts may use a reviewed file diff. Context lifecycle, project goal/scope, important Decision, Memory role, permission policy, or history deletion requires an independent Memory proposal. Never use a Decision or status note as proof of current implementation/external behavior.

## Maintain and doctor

When invoked, cheaply inspect runtime/lock/wrapper consistency, module origin, `PYTHONPATH`, config/Memory roles, validate/projection, stale/conflicting Authority, and Bundle lifecycle. Offer deeper maintenance; do not silently scan everything.

- R0 read-only diagnosis: automatic.
- R1 rebuild disposable `.local` or managed discovery projections: allowed, then report.
- R2 reinstall the already locked runtime: reviewed repair plan.
- R3 tracked config/Adapter changes: reviewed exact file plan/diff.
- R4 authority or transaction recover/rollback: inspect first, independent human review, then rebuild/validate/query.

Never guess business facts or overwrite unrecognized work.

## Upgrade

`check-update` may fetch and compare remote `main` read-only. For a selected commit run `plan-upgrade` with `--source-repository`, the full `--source-commit`, and `--output`; optionally repeat `--representative-query` and `--project-check`. Review current/target versions and commits, interpreter/ABI/builder preflight, inspected wheel metadata plus importable package version, wheel SHA-256/cache, current/target capability diff, exact lock diff, parallel runtime, rollback runtime, source-worktree dirtiness, checks, and `plan_hash`. L2 apply installs non-editably, switches only reviewed files, verifies runtime version/module origin/capabilities/validate/rebuild/validate and configured checks, and restores the prior selection on failure while retaining both runtimes and writing an ignored rollback receipt under `.local/pkc/operator-receipts/`. Preserve the old runtime for rollback. When signed/tagged Release wheels exist, prefer them; until then record `remote-commit`. Never auto-track latest.

## Uninstall

Disambiguate:

1. `remove-runtime`: reviewed deletion of disposable selected runtime/projection only.
2. `disable-project-integration`: reviewed tracked diff; preserve Memory/authority.
3. `remove-global-operator`: remove discovery projections/manifest; preserve checkout, projects, and authority.
4. `archive-or-delete-authority`: separate destructive L4 operation with inventory/export option and explicit review.

Plain “uninstall PKC” defaults to proposing only runtime/projection removal. Never delete tracked knowledge or history by default.

## Isolated usability evaluation

Use `isolated-model-evaluator` when a Skill/Operator contract, CLI command, permission/refusal/lifecycle default, project Adapter/Context, or model-facing documentation changes, or when before/after usability is an acceptance criterion. Keep task, fixture, provider/model/thinking, tools, and external oracle fixed; run read-only checks with `--assert-no-changes`; inspect the trace for the first error, guessed commands, unnecessary reads, final answer, and workspace changes.

Do not add isolated evaluation to routine Claim creation, Authority refresh, real-map validation, or an already documented Bundle application merely because those operations occurred. Project semantic/runtime/external evidence and fresh-model usability evidence are separate layers. Evaluation never approves/applies authority or authorizes Git mutation.

## Task end

Run a lightweight value gate. Show at most 1–3 independent candidates only for a stable method, real evidence, human rule correction, architecture/governance decision, or invalidated knowledge. Default is no write. Report what changed, what did not, review status, runtime commit/hash, tests, unresolved limitations, and whether commit/push occurred.

Current release status: operator contract `0.1`, intended for early real-project testing. Do not claim full cross-platform or full lifecycle verification until corresponding real evidence exists.
