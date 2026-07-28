# Portable Knowledge Core (PKC)

Portable Knowledge Core is a deterministic, local-first knowledge authority, validation, retrieval, and transaction engine for existing projects. It stores authoritative assets as reviewable JSON, JSONL, and Markdown in each project; SQLite under `.local/` is only a disposable projection.

PKC is designed for humans and AI agents that need bounded retrieval and auditable semantic changes without hidden conversation context.

## Start here

### For an AI model

Read these files in order and do not infer missing commands:

1. [`AGENTS.md`](AGENTS.md) — operating and safety contract.
2. [`INSTALL.md`](INSTALL.md) — non-editable installation and verification.
3. [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — configure and query a neutral project.
4. [`docs/SEMANTIC-CHANGES.md`](docs/SEMANTIC-CHANGES.md) — governed write workflow.

### For a human

Requirements:

- Python 3.11 or newer
- Git (Authority references and committed-baseline checks use Git)
- No runtime Python dependencies outside the standard library

Install from a clone into an isolated virtual environment:

```bash
git clone <repository-url> portable-knowledge
cd portable-knowledge
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/pkc capabilities
```

On Windows PowerShell, replace `.venv/bin/...` with `.venv\Scripts\...`.

Then copy the neutral project example and validate it:

```bash
cp -R examples/minimal-project /tmp/my-pkc-project
cd /tmp/my-pkc-project
git init
git add .
git commit -m "Initialize PKC project"
/path/to/portable-knowledge/.venv/bin/pkc validate
/path/to/portable-knowledge/.venv/bin/pkc rebuild
/path/to/portable-knowledge/.venv/bin/pkc query "deterministic lookup" --level 2
```

See [`INSTALL.md`](INSTALL.md) for production installation and Windows instructions.

## What PKC provides

- Project instance and bounded Project Memory contracts
- Git-owned Node, Topic, Claim, Source, Evidence, and Authority Reference assets
- Disposable local SQLite search projection
- L1/L2/L3 query and claim inspection
- Context-scoped progressive retrieval
- Immutable Semantic Change Bundles
- High-level typed `knowledge-plan` operations
- Delta validation, full preflight, exact-hash approval, transactional apply, and recovery
- Fact-free Domain Packs for existing personal-brand and software projects

Run `pkc capabilities` to inspect the installed runtime's machine-readable capability set.

## Authority and generated state

Commit these in the project that uses PKC:

- `project-intelligence.json`
- configured Project Memory files
- configured knowledge Markdown
- configured JSON/JSONL authority store
- approved Blueprints and Profiles when used

Do **not** commit:

- `.local/`
- SQLite databases
- transaction scratch state
- caches, reports, model transcripts, or unapproved temporary plans

A local search result is not proof that something does not exist across the whole repository. Permission and lifecycle filters always apply.

## Development

```bash
python3 -m unittest discover -s tests -p 'test*.py'
python3 -m build
```

If the `build` module is unavailable, create a disposable build environment or install the build frontend there; PKC itself has no third-party runtime dependencies.

## Project status

Current version: `0.2.0rc1` (release candidate).

This repository currently has **no declared open-source license**. Source availability does not grant redistribution or modification rights. Add an explicit license before public distribution.
