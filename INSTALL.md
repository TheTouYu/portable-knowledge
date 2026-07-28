# Installation Guide

This guide is intentionally executable by a human or a fresh AI model without prior conversation context.

## 1. Prerequisites

Required:

- Python `>=3.11`
- Git
- a clone of this repository

Recommended:

- one dedicated virtual environment per PKC runtime version
- a clean, committed Git baseline in every target project before governed writes

PKC has no third-party runtime dependencies. Build frontends such as `build` or `uv` are development tools, not runtime dependencies.

## 2. Clone

```bash
git clone https://github.com/TheTouYu/portable-knowledge.git
cd portable-knowledge
```

Verify the configured remote before installing:

```bash
git remote get-url origin
# https://github.com/TheTouYu/portable-knowledge.git
```

## 3. Install non-editably

### Linux and macOS

With standard `venv` and pip:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
```

Or with uv:

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python .
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

Do not use `pip install -e .` for a production/project runtime. Do not set `PYTHONPATH` to this source checkout.

## 4. Verify the runtime

### Linux and macOS

```bash
.venv/bin/pkc capabilities
.venv/bin/python - <<'PY'
import importlib.metadata
import os
import portable_knowledge

print("distribution:", importlib.metadata.version("portable-knowledge"))
print("runtime:", portable_knowledge.__version__)
print("module:", portable_knowledge.__file__)
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
PY
```

### Windows PowerShell

```powershell
.\.venv\Scripts\pkc.exe capabilities
.\.venv\Scripts\python.exe -c "import importlib.metadata, os, portable_knowledge; print('distribution:', importlib.metadata.version('portable-knowledge')); print('runtime:', portable_knowledge.__version__); print('module:', portable_knowledge.__file__); print('PYTHONPATH:', os.environ.get('PYTHONPATH'))"
```

Expected for this revision:

- distribution/runtime version: `0.2.0rc5`
- `pkc capabilities` returns JSON with `"ok": true`
- module path is inside `.venv` site-packages, not this repository's `src/`
- `PYTHONPATH` does not point to a PKC source checkout

`pkc --version` is not a supported command. Use `pkc capabilities` and package metadata.

## 5. Build and install a locked wheel (recommended for multiple projects)

Using uv without modifying the runtime environment:

```bash
uv build --wheel --out-dir dist
sha256sum dist/portable_knowledge-0.2.0rc5-py3-none-any.whl
uv venv /absolute/path/to/pkc-runtime --python 3.11
uv pip install --python /absolute/path/to/pkc-runtime/bin/python \
  dist/portable_knowledge-0.2.0rc5-py3-none-any.whl
```

On Windows, calculate the hash with:

```powershell
Get-FileHash .\dist\portable_knowledge-0.2.0rc5-py3-none-any.whl -Algorithm SHA256
```

Record the wheel filename, SHA-256, PKC version, and source commit in the consuming project's installation documentation. Do not silently replace a locked wheel with a source checkout.

## 6. Configure a project

Copy [`examples/minimal-project`](examples/minimal-project) to a new or existing project and adapt:

- `project-intelligence.json`
- configured identity IDs
- Memory role paths
- authority store and knowledge paths
- Context goal and validation gate

Examples and Domain Packs are fact-free scaffolds. They are never authority for your project.

The project should ignore `.local/`:

```gitignore
.local/
__pycache__/
*.py[cod]
```

Commit the initial text authority before adding Authority References because semantic plans validate paths against the committed baseline.

Continue with [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

## 7. Upgrade

1. Read the new release notes and capability output.
2. Build or obtain a wheel and verify its SHA-256.
3. Install it into a new virtual environment; do not mutate the known-good runtime in place.
4. Run against a disposable project copy first:

```bash
pkc validate
pkc rebuild
pkc validate
pkc query "representative query" --level 2
```

5. Run the consuming project's tests.
6. Switch its canonical wrapper/runtime only after all checks pass.

Never rewrite historical JSONL merely to upgrade PKC.

Capability compatibility: `migration_plan` remains as a deprecated ambiguous field for old clients and means non-atomic multi-Bundle orchestration. New clients should read `bundle_orchestration_plan` or `bundle_migration_plan`. Governed Topic relocation is advertised separately as `knowledge_structure_refactor`; governed existing-Claim correction as `claim_revision_plan`.

## 8. Uninstall

Remove the dedicated virtual environment. Project authority remains in Git-owned text assets. `.local/` can be deleted and rebuilt at any time:

```bash
rm -rf .local
pkc rebuild
pkc validate
```

On PowerShell:

```powershell
Remove-Item -Recurse -Force .local
pkc rebuild
pkc validate
```

## Troubleshooting

### `local projection is missing or invalid`

Run:

```bash
pkc validate
pkc rebuild
pkc validate
```

Do not query SQLite directly.

### Authority path is not committed

Commit the target project's intended baseline through the normal human-approved Git workflow. Do not weaken the check or fabricate a diagnostic hash.

### Wrong runtime or source leakage

Recreate the virtual environment, install a non-editable wheel, unset `PYTHONPATH`, and repeat the verification in section 4.

### Permission or lifecycle filtering hides a result

Inspect the Claim with an authorized permission level. Do not infer repository-wide absence from a bounded result.
