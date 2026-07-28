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

Then run the smallest required inspection. Ordinary mechanical edits that do not involve project intelligence do not trigger this Skill.

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
python scripts/pkc_operator.py apply-plan --plan /tmp/pkc-install-plan.json --plan-hash EXACT_HASH --human-reviewed
python scripts/pkc_operator.py status --target /path/to/project
python scripts/pkc_operator.py doctor --target /path/to/project
python scripts/pkc_operator.py check-update --target /path/to/project
```

`plan-install` may fetch the public remote, resolve `main` to an exact commit, and build/cache a wheel outside the target project. `plan-adopt` does the same for an existing instance that already has `project-intelligence.json` and authority but no project lock; it may plan only the lock, canonical wrapper, and parallel runtime while preserving the existing instance, Memory, Adapter, authority, and history. Neither planning command may change the target project. Present the complete summary and `plan_hash`; only then may `apply-plan` run. Environment or file drift must fail closed and require a new plan.

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

Use `python tools/pkc.py ...`, never a global/system `pkc`. A bounded miss is not repository-wide absence. Ordinary mechanical work defaults to no query.

## Intake and capture

Before distillation: sensitive-data precheck → permission for save/internal reuse/remote processing/publication → deduplicate → preserve raw material or external locator → delegate to a project-declared handler → retrieve existing knowledge → classify exactly one primary result:

```text
discard | source-only | evidence | new claim | revise
```

Unknown permission stops. Unsupported formats do not produce partial archives. `source-only` and `discard` are successful closures. Keep raw material, Evidence, Claim, Authority Reference, and Project Memory in separate truth sources.

For Domain Knowledge use only installed high-level PKC `knowledge-plan` operations. Use `add-claim` for new knowledge, `revise-claim` to correct/clarify an existing proposition, and `move-topic` to change an existing Topic's Node/path while preserving IDs, Authority links, and history. These operations may share one immutable refactor Bundle. Multi-Bundle orchestration (`bundle_migration_plan`, historically `migration_plan`) is not knowledge structure migration. No Python APIs, shell manifests, direct JSON/Markdown authority writes, SQLite, `bundle-create --manifest`, or compatibility mode. Follow the exact workflow in the repository's `docs/SEMANTIC-CHANGES.md` or [the mode contract](references/MODES.md).

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

`check-update` may fetch and compare remote `main` read-only. Upgrade must resolve an exact new commit, build/hash a wheel, create a parallel runtime, show compatibility and project file plan, obtain review, switch the lock, and run validate/rebuild/representative queries/tests. Preserve the old runtime for rollback. When signed/tagged Release wheels exist, prefer them; until then record `remote-commit`. Never auto-track latest.

## Uninstall

Disambiguate:

1. `remove-runtime`: reviewed deletion of disposable selected runtime/projection only.
2. `disable-project-integration`: reviewed tracked diff; preserve Memory/authority.
3. `remove-global-operator`: remove discovery projections/manifest; preserve checkout, projects, and authority.
4. `archive-or-delete-authority`: separate destructive L4 operation with inventory/export option and explicit review.

Plain “uninstall PKC” defaults to proposing only runtime/projection removal. Never delete tracked knowledge or history by default.

## Task end

Run a lightweight value gate. Show at most 1–3 independent candidates only for a stable method, real evidence, human rule correction, architecture/governance decision, or invalidated knowledge. Default is no write. Report what changed, what did not, review status, runtime commit/hash, tests, unresolved limitations, and whether commit/push occurred.

Current release status: operator contract `0.1`, intended for early real-project testing. Do not claim full cross-platform or full lifecycle verification until corresponding real evidence exists.
