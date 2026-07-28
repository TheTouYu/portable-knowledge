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

Existing files are preserved unless their exact prior hash and replacement are present in the reviewed plan. The first implementation does not automatically edit an existing root `AGENTS.md`; it reports the trigger snippet for human placement. This avoids silently changing a project's highest-precedence operating contract.

The neutral initial authority is empty. Do not copy the example Claim into a real project.

## Project wrapper

Only the tracked wrapper is canonical in a configured project:

```bash
python tools/pkc.py capabilities
python tools/pkc.py validate
python tools/pkc.py rebuild
python tools/pkc.py query "question" --level 2
```

It resolves the project root, reads `tools/pkc-lock.json`, verifies runtime location/version, removes source-checkout `PYTHONPATH`, and forwards arguments. It never downloads, upgrades, or falls back to a system runtime.

## Exact semantic change flow

```bash
python tools/pkc.py knowledge-plan init --intent "..." --risk medium
python tools/pkc.py knowledge-plan add-claim PLAN_ID \
  --node NODE --topic-id TOPIC --topic-path knowledge/topic.md \
  --title "..." --statement "..." --boundary "..." \
  --permission internal --fact-class current_implementation
python tools/pkc.py knowledge-plan add-authority-ref PLAN_ID \
  --claim-id CLAIM_ID --path src/module.py --locator "function:name" \
  --role implementation --change-policy invalidate_on_change \
  --fact-class current_implementation
python tools/pkc.py knowledge-plan check PLAN_ID --mode delta
python tools/pkc.py knowledge-plan finalize PLAN_ID
python tools/pkc.py bundle-inspect BUNDLE_ID --format json
```

Stop and show the full immutable hash. After a real human confirms that exact hash:

```bash
python tools/pkc.py bundle-approve BUNDLE_ID --content-hash HASH --apply
python tools/pkc.py bundle-apply BUNDLE_ID --content-hash HASH --apply
python tools/pkc.py rebuild
python tools/pkc.py validate
python tools/pkc.py query "representative question" --level 2
python tools/pkc.py bundle-inspect BUNDLE_ID --format json
```

Valid Authority roles are `implementation`, `test`, `schema`, `contract`, and `verification`. `bundle-status` has no positional Bundle ID. Query text is positional; there is no `--text` option.

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
