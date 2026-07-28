# Portable Knowledge Core (PKC)

Portable Knowledge Core is a deterministic, local-first knowledge authority, validation, retrieval, and transaction engine for existing projects. It stores authoritative assets as reviewable JSON, JSONL, and Markdown in each project; SQLite under `.local/` is only a disposable projection.

PKC is designed for humans and AI agents that need bounded retrieval and auditable semantic changes without hidden conversation context.

For easy cross-project installation and ongoing operation, this repository also ships the global [`pkc-project-operator`](skills/pkc-project-operator/SKILL.md) Skill. It covers technical installation, first use, query, intake, capture, Project Memory, maintenance, diagnosis, upgrade, exact-hash review/apply, and safe removal while delegating deterministic semantics to PKC Core.

The repository also includes [`isolated-model-evaluator`](skills/isolated-model-evaluator/SKILL.md), which launches a fresh Pi model context with only explicitly selected Skills and records traces, correctness signals, tool errors, workspace changes, usage, latency, and cost for repeatable model-facing workflow evaluation.

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
git clone https://github.com/TheTouYu/portable-knowledge.git
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
- One offline, read-only `knowledge-check` command with project-configured retrieval/refusal regressions and Authority/upstream freshness warnings
- Optional `knowledge-index` and `knowledge-search --semantic` hybrid retrieval with ignored model+input-hash cache and explicit lexical fallback
- Immutable Semantic Change Bundles
- High-level typed `knowledge-plan` operations for creation, Claim revision, and Topic refactoring
- Stable-ID Topic moves with atomic destination-Node creation and exact-path relocation
- Delta validation, full preflight, exact-hash approval, transactional apply/rollback, and recovery
- Fact-free Domain Packs for existing personal-brand and software projects

Run `pkc capabilities` to inspect the installed runtime's machine-readable capability set.

## Evaluate with a fresh model context

Use the repository-local evaluator to test whether a model can operate PKC without hidden conversation context:

```bash
python3 skills/isolated-model-evaluator/scripts/evaluate.py \
  --skill skills/pkc-project-operator \
  --task-file /tmp/pkc-eval-task.md \
  --assert-no-changes \
  --output-dir /tmp/pkc-isolated-eval
```

The evaluator defaults to the cost-effective `aijws / gpt-5.6-luna / medium` profile. Keep provider, model, thinking level, task, fixture, and tools fixed when comparing iterations. Raw traces and reports belong outside Git by default. Process success alone is not semantic correctness; define and inspect task-specific acceptance criteria. See the [Skill contract](skills/isolated-model-evaluator/SKILL.md) and [report contract](skills/isolated-model-evaluator/references/report-contract.md).

## Install the global Operator Skill

From a clean checkout of this repository:

```bash
python3 skills/pkc-project-operator/scripts/pkc_operator.py install-global --source .
```

This creates managed discovery projections in `~/.agents/skills/` and `~/.pi/agent/skills/` and records their source commit. Restart or rescan your Agent harness, then invoke `pkc-project-operator` naturally—for example, “给这个项目安装知识树” or “检查并维护这个项目的知识系统”. The Operator always plans tracked/runtime changes first and requires a real human review before applying them.

Operator contract `0.1` is an early real-project testing release. Linux/Pi is the first tested target; other platform/Agent claims remain explicitly limited until real-environment validation.

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

A local search result is not proof that something does not exist across the whole repository. Permission, lifecycle, conflict, and Authority status filters apply before knowledge-search output. Vector similarity is a ranking signal, never evidence or confirmation.

## Development

```bash
python3 -m unittest discover -s tests -p 'test*.py'
python3 -m build
```

If the `build` module is unavailable, create a disposable build environment or install the build frontend there; PKC itself has no third-party runtime dependencies.

## Project status

Current version: `0.2.0rc4` (release candidate).

This public repository currently has **no declared open-source license**. Public source visibility does not grant redistribution or modification rights. An explicit license must be chosen before representing PKC as open-source software.
