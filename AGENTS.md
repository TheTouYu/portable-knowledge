# PKC Agent Operating Contract

This is the canonical entry for an AI model configuring or operating Portable Knowledge Core from a fresh context.

## Read order

1. `README.md`
2. `INSTALL.md`
3. `docs/QUICKSTART.md`
4. Read `docs/SEMANTIC-CHANGES.md` only if a write is requested.
5. In a target project, read its configured `operating_entry`, `current_recovery`, and `decision_entry` roles before complex work.

Do not begin by reading all tests, all source files, Git history, `.local/`, SQLite, model traces, or every knowledge document.

## Installation contract

- Use Python 3.11 or newer.
- Install PKC non-editably into a project-owned or tool-owned virtual environment.
- Do not set `PYTHONPATH` to a source checkout in production.
- Verify `pkc capabilities`, distribution version, and module origin as described in `INSTALL.md`.
- The target project's `project-intelligence.json` is instance authority. Do not copy business facts from examples or Domain Packs.

## Canonical CLI

The only command entry is `pkc`.

Discover commands with:

```bash
pkc --help
pkc capabilities
pkc knowledge-plan --help
pkc knowledge-check --help
pkc knowledge-search --help
```

Do not guess unsupported forms such as `pkc --version`, `pkc semantic-plan`, or `pkc query --text ...`.

Global options precede the command:

```bash
pkc --root /path/to/project --config project-intelligence.json validate
```

Inside the target project, `--root` and `--config` normally use their defaults.

## Safety boundaries

- Git text assets are authoritative; `.local/` and SQLite are disposable projections.
- Never read or modify SQLite directly.
- Never assemble JSON manifests in shell, use Python APIs, or call `bundle-create --manifest` for normal production knowledge ingestion.
- Use high-level `knowledge-plan` operations for Claim and Authority Reference changes.
- Do not use compatibility/maintainer mode unless a human explicitly requests recovery work.
- Git commits of small, self-contained changes you have verified (docs/tools/skills/knowledge) are allowed: stage exact paths, run `git diff --check`, never sweep unrelated changes. `push`, branch switch, merge/rebase, reset/clean/checkout, and overwriting unexplained tree changes still require an explicit human request.
- Preserve existing working-tree changes.
- Working-tree-only observations cannot become stable authority.
- Do not weaken permission, lifecycle, Authority coverage, provenance, staged validation, or exact-hash checks.

## Read workflow

```text
validate/rebuild if projection is absent or stale
→ tree or progressive-query for bounded routing
→ query at L1/L2
→ show-claim or L3 only for exact evidence/Authority boundaries
```

A limited query cannot justify a repository-wide absence statement.

## Write workflow

Use the exact contract in `docs/SEMANTIC-CHANGES.md`:

```text
knowledge-plan init
→ add all Claims and Authority Refs
→ one delta check
→ finalize (full staged preflight)
→ inspect immutable Bundle and exact content hash
→ stop for explicit human approval
→ approve that exact hash
→ apply that same exact hash
→ rebuild → validate → representative query → lifecycle inspection
```

Before approval, report semantic difference, evidence/Authority basis, exclusions, permission effect, expected changed files, risk, and the full content hash. Changed content invalidates approval.

Never treat installation success, a neutral example, synthetic fixture, or local automated test as real-project evidence.


## 沟通规则（用户全局要求）

- 所有项目工作中一律用中文回复；代码、命令、文件名、技术术语可以保留英文原文。
- 风格通俗易懂：先给结论、再讲原因；少堆术语，多用具体例子。
- 除非用户明确要求英文，否则不要用英文回复。
