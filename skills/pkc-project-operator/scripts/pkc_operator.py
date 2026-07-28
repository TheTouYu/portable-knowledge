#!/usr/bin/env python3
"""Deterministic mechanical installer/doctor for PKC Project Operator contract 0.1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import sysconfig
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_REMOTE = "https://github.com/TheTouYu/portable-knowledge.git"
CONTRACT = "0.1"
CACHE = Path.home() / ".local" / "share" / "portable-knowledge"


class OperatorError(Exception):
    pass


def run(command: list[str], *, cwd: Path | None = None, check: bool = True,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode:
        raise OperatorError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr.strip()}")
    return result


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str | None:
    return digest_bytes(path.read_bytes()) if path.is_file() else None


def plan_hash(plan: dict[str, Any]) -> str:
    return digest_bytes(canonical({k: v for k, v in plan.items() if k != "plan_hash"}).encode())


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def git_root(target: Path) -> Path:
    result = run(["git", "-C", str(target), "rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip()).resolve()


def git_state(root: Path) -> dict[str, Any]:
    return {
        "head": run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip(),
        "branch": run(["git", "-C", str(root), "branch", "--show-current"], check=False).stdout.strip(),
        "status": run(["git", "-C", str(root), "status", "--porcelain=v1"]).stdout.splitlines(),
    }


def safe_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return value or "project"


def resolve_commit(remote: str, ref: str) -> str:
    candidates = [ref, f"refs/heads/{ref}", f"refs/tags/{ref}"]
    output = run(["git", "ls-remote", remote, *candidates]).stdout.splitlines()
    if not output:
        raise OperatorError(f"remote ref not found: {remote} {ref}")
    commits = {line.split()[0] for line in output}
    if len(commits) != 1:
        raise OperatorError(f"remote ref is ambiguous: {ref}")
    return commits.pop()


def _source_commit(repository: str, commit: str) -> tuple[str, list[str]]:
    source = Path(repository).expanduser()
    if source.exists():
        root = git_root(source)
        resolved = run(["git", "-C", str(root), "rev-parse", f"{commit}^{{commit}}"]).stdout.strip()
        dirty = run(["git", "-C", str(root), "status", "--porcelain=v1"]).stdout.splitlines()
        return resolved, dirty
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise OperatorError("remote source commit must be an exact 40-character Git object ID")
    return commit.lower(), []


def build_environment() -> dict[str, Any]:
    python = Path(sys.executable).resolve()
    uv = shutil.which("uv")
    pip = run([str(python), "-m", "pip", "--version"], check=False)
    venv = run([str(python), "-m", "venv", "--help"], check=False)
    return {"python": str(python), "python_version": sys.version.split()[0],
            "abi": sysconfig.get_config_var("SOABI") or "unknown", "uv": uv,
            "pip_available": pip.returncode == 0, "venv_available": venv.returncode == 0,
            "builder": "uv" if uv else "unavailable"}


def ensure_wheel_provenance(repository: str, commit: str) -> dict[str, Any]:
    commit, source_dirty = _source_commit(repository, commit)
    environment = build_environment()
    if environment["builder"] == "unavailable":
        raise OperatorError("no usable wheel builder: install uv outside the project runtime; "
                            f"python={environment['python']} pip_available={environment['pip_available']}")
    identity = digest_bytes(canonical({"repository": str(repository), "commit": commit,
                                       "abi": environment["abi"], "builder": environment["builder"]}).encode())[:16]
    wheel_dir = CACHE / "wheels" / commit / identity
    metadata_path = wheel_dir / "metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        wheel = wheel_dir / metadata["filename"]
        if (wheel.is_file() and digest_file(wheel) == metadata.get("sha256")
                and metadata.get("source_commit") == commit):
            return {**metadata, "wheel": str(wheel), "source_worktree_dirty": source_dirty,
                    "build_environment": environment, "cache_reused": True}
    wheel_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pkc-build-") as directory:
        checkout = Path(directory) / "source"
        run(["git", "clone", "--quiet", "--no-checkout", repository, str(checkout)])
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", commit])
        if run(["git", "-C", str(checkout), "status", "--porcelain"]).stdout.strip():
            raise OperatorError("exact-commit build export is not clean")
        output = Path(directory) / "dist"
        timestamp = run(["git", "-C", str(checkout), "show", "-s", "--format=%ct", commit]).stdout.strip()
        env = os.environ.copy(); env["SOURCE_DATE_EPOCH"] = timestamp
        run([environment["uv"], "build", "--wheel", "--out-dir", str(output)], cwd=checkout, env=env)
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1:
            raise OperatorError("expected exactly one wheel")
        target = wheel_dir / wheels[0].name
        shutil.copy2(wheels[0], target)
        sha = digest_file(target)
        match = re.fullmatch(r"portable_knowledge-([^-]+)-.+\.whl", target.name)
        if not sha or not match:
            raise OperatorError("built wheel name or distribution is invalid")
        metadata = {"filename": target.name, "sha256": sha, "version": match.group(1),
                    "distribution": "portable-knowledge", "source_repository": str(repository),
                    "source_commit": commit, "python": environment["python"],
                    "python_version": environment["python_version"], "abi": environment["abi"],
                    "builder": environment["builder"]}
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return {**metadata, "wheel": str(target), "source_worktree_dirty": source_dirty,
                "build_environment": environment, "cache_reused": False}


def ensure_wheel(remote: str, commit: str) -> tuple[Path, str, str]:
    provenance = ensure_wheel_provenance(remote, commit)
    return Path(provenance["wheel"]), provenance["sha256"], provenance["version"]


def inspect_target(target: Path) -> dict[str, Any]:
    root = git_root(target)
    state = git_state(root)
    lock_path = root / "tools" / "pkc-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else None
    config = root / "project-intelligence.json"
    skill_dirs = [p.as_posix() for base in ("skills", ".agents/skills", ".pi/skills", ".claude/skills", ".codex/skills")
                  for p in [root / base] if p.exists()]
    return {"ok": True, "command": "inspect", "operator_contract": CONTRACT, "root": str(root),
            "project_state": "configured" if lock and config.is_file() else "degraded" if lock or config.is_file() else "unconfigured",
            "git": state, "lock": lock, "instance_config": config.is_file(), "skill_roots": skill_dirs,
            "runtime_exists": bool(lock and (root / lock.get("runtime", "")).exists()), "errors": []}


def text_write(root: Path, rel: str, content: str) -> dict[str, Any]:
    path = root / rel
    return {"path": rel, "expected_sha256": digest_file(path), "content": content,
            "new_sha256": digest_bytes(content.encode()), "action": "replace" if path.exists() else "create"}


def initial_assets(root: Path, project_id: str, commit: str, remote: str, wheel: Path, sha: str, version: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    runtime_rel = f".local/pkc/runtimes/{commit}"
    writer = "human-review-channel"
    config = {
        "schema_version": 1, "instance": {"id": project_id, "name": root.name},
        "pkc": {"version": version, "projection_path": ".local/pkc/projection"},
        "authority": {"registry": "data/knowledge/registry.json", "actors": "data/knowledge/actors.json", "store": "data/knowledge", "knowledge": "knowledge", "authority_refs": "data/knowledge/authority-refs.json"},
        "identities": {"principal": {"id": "human-reviewer"}, "executor": {"id": "agent"},
                       "workspace": {"id": f"{project_id}-workspace", "path": "."}, "writer": {"id": writer}},
        "compatibility": {"v1_actor_map": {writer: "human-reviewer"}},
        "memory": {"roles": [
            {"role": "operating_entry", "path": "memory/OPERATING.md", "mutation_policy": "reference"},
            {"role": "current_recovery", "path": "memory/CURRENT.md", "mutation_policy": "replace"},
            {"role": "decision_entry", "path": "memory/DECISIONS.md", "mutation_policy": "supersede"}],
            "contexts": [{"id": "default", "default": True, "lifecycle": "active", "goal": "Maintain project intelligence", "recovery_role": "current_recovery", "validation_gate": "python tools/pkc.py validate"}],
            "startup_budget": {"max_files": 4, "max_characters": 12000}, "applies_to": {"workspace": ".", "branches": ["*"]}}
    }
    lock = {"schema_version": 1, "operator_contract": CONTRACT, "version": version, "release_channel": "remote-commit",
            "source_repository": remote, "source_ref": "main", "source_commit": commit, "wheel_sha256": sha,
            "wheel_cache": str(wheel), "runtime": runtime_rel, "python_requirement": ">=3.11"}
    wrapper = '''#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "tools/pkc-lock.json").read_text(encoding="utf-8"))
runtime = root / lock["runtime"]
exe = runtime / ("Scripts/pkc.exe" if os.name == "nt" else "bin/pkc")
if not exe.is_file():
    raise SystemExit("locked PKC runtime is missing; invoke global pkc-project-operator doctor")
env = os.environ.copy(); env.pop("PYTHONPATH", None)
raise SystemExit(subprocess.run([str(exe), "--root", str(root), *sys.argv[1:]], env=env).returncode)
'''
    adapter = f'''---
name: {project_id}-knowledge-adapter
description: Route complex project tasks through bounded Project Memory and PKC. Use for architecture, historical constraints, cross-file judgment, real evidence, permissions, knowledge query/intake/capture, or maintenance in {root.name}.
metadata:
  operator-contract: "{CONTRACT}"
---

# {root.name} Knowledge Adapter

Read `project-intelligence.json`, then configured operating/current/decision roles. Use `python tools/pkc.py` as the only PKC entry. Delegate installation, repair, upgrade, intake orchestration, and general lifecycle work to global `pkc-project-operator`. Ordinary mechanical work does not query. Never self-review a tracked, authority, runtime, Git, or remote mutation.
'''
    operating = "# Knowledge Operating Entry\n\nUse the project Adapter and `python tools/pkc.py`. Read CURRENT and DECISIONS before complex work. Human review is required for tracked/runtime changes; exact-hash review is required for knowledge authority.\n"
    current = "# Current Recovery\n\nPrimary Context: `default`\n\nGoal and next action require project-owner confirmation during first-use.\n"
    decisions = "# Decision Entry\n\nNo project-specific knowledge-system decisions recorded yet.\n"
    registry = {"schema_version": 1, "nodes": [], "topics": [], "relationships": []}
    actors = {"schema_version": 1, "actors": [{"id": writer, "name": "Human review channel", "status": "active", "roles": ["owner", "business_reviewer"]}]}
    refs = {"schema_version": 1, "refs": []}
    contents = {
        "tools/pkc-lock.json": json.dumps(lock, ensure_ascii=False, indent=2) + "\n", "tools/pkc.py": wrapper,
        "project-intelligence.json": json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        f"skills/{project_id}-knowledge-adapter/SKILL.md": adapter,
        "memory/OPERATING.md": operating, "memory/CURRENT.md": current, "memory/DECISIONS.md": decisions,
        "data/knowledge/registry.json": json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        "data/knowledge/actors.json": json.dumps(actors, ensure_ascii=False, indent=2) + "\n",
        "data/knowledge/authority-refs.json": json.dumps(refs, ensure_ascii=False, indent=2) + "\n",
        f"data/knowledge/evidence/{writer}.jsonl": "", f"data/knowledge/proposals/{writer}.jsonl": "",
        f"data/knowledge/sources/{writer}.jsonl": "", "knowledge/.gitkeep": "",
    }
    gitignore = root / ".gitignore"
    old = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if ".local/" not in old.splitlines():
        contents[".gitignore"] = old + ("" if not old or old.endswith("\n") else "\n") + ".local/\n"
    writes = [text_write(root, rel, content) for rel, content in contents.items()]
    links = [{"path": f".agents/skills/{project_id}-knowledge-adapter", "target": f"../../skills/{project_id}-knowledge-adapter"}]
    return writes, links


def adoption_assets(root: Path, commit: str, remote: str, wheel: Path, sha: str, version: str) -> list[dict[str, Any]]:
    runtime_rel = f".local/pkc/runtimes/{commit}"
    lock = {"schema_version": 1, "operator_contract": CONTRACT, "version": version, "release_channel": "remote-commit",
            "source_repository": remote, "source_ref": "main", "source_commit": commit, "wheel_sha256": sha,
            "wheel_cache": str(wheel), "runtime": runtime_rel, "python_requirement": ">=3.11"}
    wrapper = '''#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "tools/pkc-lock.json").read_text(encoding="utf-8"))
runtime = root / lock["runtime"]
exe = runtime / ("Scripts/pkc.exe" if os.name == "nt" else "bin/pkc")
if not exe.is_file():
    raise SystemExit("locked PKC runtime is missing; invoke global pkc-project-operator doctor")
env = os.environ.copy(); env.pop("PYTHONPATH", None)
raise SystemExit(subprocess.run([str(exe), "--root", str(root), *sys.argv[1:]], env=env).returncode)
'''
    return [text_write(root, "tools/pkc-lock.json", json.dumps(lock, ensure_ascii=False, indent=2) + "\n"),
            text_write(root, "tools/pkc.py", wrapper)]


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    existing = inspect_target(root)
    if existing["project_state"] != "unconfigured":
        raise OperatorError("target already has partial/full PKC configuration; use plan-adopt for an existing unlocked instance, otherwise use doctor or upgrade")
    commit = resolve_commit(args.remote, args.ref)
    wheel, sha, version = ensure_wheel(args.remote, commit)
    project_id = safe_id(args.project_id or root.name)
    writes, links = initial_assets(root, project_id, commit, args.remote, wheel, sha, version)
    conflicts = [item["path"] for item in writes if item["expected_sha256"] is not None and item["path"] != ".gitignore"]
    if conflicts:
        raise OperatorError(f"initialization paths already exist; map them in a reviewed custom plan instead of overwriting: {conflicts}")
    state = git_state(root)
    plan = {"schema_version": 1, "operator_contract": CONTRACT, "kind": "pkc-install", "target_root": str(root),
            "project_id": project_id, "created_from": {"head": state["head"], "status": state["status"]},
            "source": {"repository": args.remote, "ref": args.ref, "commit": commit, "version": version,
                       "wheel": str(wheel), "wheel_sha256": sha}, "runtime": f".local/pkc/runtimes/{commit}",
            "writes": writes, "links": links, "excluded": ["existing project source/docs except declared writes", "Git commit/push", "business Claims/Topics/Nodes", "authority apply"],
            "verification": ["capabilities", "validate", "rebuild", "validate"], "human_reviewed": False}
    plan["plan_hash"] = plan_hash(plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "command": "plan-install", "plan_file": str(args.output), "plan_hash": plan["plan_hash"],
            "target": str(root), "source": plan["source"], "runtime": plan["runtime"],
            "writes": [{k: x[k] for k in ("path", "action", "expected_sha256", "new_sha256")} for x in writes],
            "links": links, "excluded": plan["excluded"], "next": "show this plan to a human; apply only after review", "errors": []}


def command_plan_adopt(args: argparse.Namespace) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    existing = inspect_target(root)
    if not existing["instance_config"] or existing["lock"] is not None:
        raise OperatorError("plan-adopt requires exactly one existing project-intelligence.json and no project lock")
    for rel in ("tools/pkc-lock.json", "tools/pkc.py"):
        if (root / rel).exists():
            raise OperatorError(f"adoption path already exists: {rel}")
    commit = resolve_commit(args.remote, args.ref)
    wheel, sha, version = ensure_wheel(args.remote, commit)
    writes = adoption_assets(root, commit, args.remote, wheel, sha, version)
    state = git_state(root)
    plan = {"schema_version": 1, "operator_contract": CONTRACT, "kind": "pkc-adopt", "target_root": str(root),
            "created_from": {"head": state["head"], "status": state["status"]},
            "source": {"repository": args.remote, "ref": args.ref, "commit": commit, "version": version,
                       "wheel": str(wheel), "wheel_sha256": sha},
            "runtime": f".local/pkc/runtimes/{commit}", "writes": writes, "links": [],
            "preserved": ["project-intelligence.json", "configured Project Memory and Adapter",
                          "configured authority and knowledge assets", "historical JSONL and Bundles"],
            "excluded": ["existing project files except declared writes", "Git commit/push",
                         "business Claims/Topics/Nodes", "authority apply", "legacy adapter removal"],
            "verification": ["capabilities", "validate", "rebuild", "validate"], "human_reviewed": False}
    plan["plan_hash"] = plan_hash(plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "command": "plan-adopt", "plan_file": str(args.output), "plan_hash": plan["plan_hash"],
            "target": str(root), "source": plan["source"], "runtime": plan["runtime"],
            "writes": [{k: x[k] for k in ("path", "action", "expected_sha256", "new_sha256")} for x in writes],
            "preserved": plan["preserved"], "excluded": plan["excluded"],
            "next": "show this plan to a human; apply only after review", "errors": []}


def command_plan_upgrade(args: argparse.Namespace) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    existing = inspect_target(root)
    if existing["project_state"] != "configured":
        raise OperatorError("plan-upgrade requires a configured project with a lock and canonical runtime")
    current = existing["lock"]
    provenance = ensure_wheel_provenance(args.source_repository, args.source_commit)
    commit = provenance["source_commit"]
    if commit == current.get("source_commit"):
        raise OperatorError("target source commit is already selected")
    wheel = Path(provenance["wheel"])
    new_lock = {"schema_version": 1, "operator_contract": CONTRACT, "version": provenance["version"],
                "release_channel": "remote-commit", "source_repository": str(args.source_repository),
                "source_ref": commit, "source_commit": commit, "wheel_sha256": provenance["sha256"],
                "wheel_cache": str(wheel), "runtime": f".local/pkc/runtimes/{commit}",
                "python_requirement": ">=3.11"}
    write = text_write(root, "tools/pkc-lock.json", json.dumps(new_lock, ensure_ascii=False, indent=2) + "\n")
    state = git_state(root)
    verification = ["capabilities", "module-origin", "validate", "rebuild", "validate"]
    config = json.loads((root / "project-intelligence.json").read_text(encoding="utf-8"))
    if (config.get("evaluation") or {}).get("cases_path"):
        verification.append("knowledge-check")
    plan = {"schema_version": 1, "operator_contract": CONTRACT, "kind": "pkc-upgrade",
            "target_root": str(root), "created_from": {"head": state["head"], "status": state["status"]},
            "current": {"version": current.get("version"), "source_commit": current.get("source_commit"),
                        "runtime": current.get("runtime"), "lock_sha256": digest_file(root / "tools/pkc-lock.json")},
            "source": {"repository": str(args.source_repository), "commit": commit,
                       "version": provenance["version"], "wheel": str(wheel),
                       "wheel_sha256": provenance["sha256"], "provenance": provenance},
            "runtime": new_lock["runtime"], "rollback_runtime": current.get("runtime"),
            "writes": [write], "links": [], "verification": verification,
            "representative_queries": args.representative_query, "project_checks": args.project_check,
            "excluded": ["formal knowledge authority", "Git commit/push", "old runtime deletion"],
            "human_reviewed": False}
    plan["plan_hash"] = plan_hash(plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "command": "plan-upgrade", "plan_file": str(args.output),
            "plan_hash": plan["plan_hash"], "current": plan["current"], "target": plan["source"],
            "runtime": plan["runtime"], "rollback_runtime": plan["rollback_runtime"],
            "writes": [{k: write[k] for k in ("path", "action", "expected_sha256", "new_sha256")}],
            "verification": verification, "target_worktree_dirty": state["status"],
            "next": "show this exact plan hash to a human; apply only after review", "errors": []}


def create_link(root: Path, item: dict[str, str]) -> None:
    path = root / item["path"]
    target = item["target"]
    if path.exists() or path.is_symlink():
        raise OperatorError(f"discovery path already exists: {item['path']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    source = (path.parent / target).resolve()
    if os.name == "nt":
        shutil.copytree(source, path)
    else:
        path.symlink_to(target, target_is_directory=True)


def command_apply(args: argparse.Namespace) -> dict[str, Any]:
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    actual = plan_hash(plan)
    if plan.get("plan_hash") != actual or args.plan_hash != actual:
        raise OperatorError("plan hash mismatch")
    if not args.human_reviewed:
        raise OperatorError("a real human must review the displayed plan before apply")
    root = Path(plan["target_root"]).resolve()
    state = git_state(root)
    if state["head"] != plan["created_from"]["head"] or state["status"] != plan["created_from"]["status"]:
        raise OperatorError("target Git state changed after planning; create a new plan")
    for item in plan["writes"]:
        path = root / item["path"]
        if digest_file(path) != item["expected_sha256"]:
            raise OperatorError(f"planned file changed: {item['path']}")
    wheel = Path(plan["source"]["wheel"])
    if digest_file(wheel) != plan["source"]["wheel_sha256"]:
        raise OperatorError("cached wheel hash mismatch")
    if plan.get("kind") == "pkc-upgrade":
        planned = plan["source"].get("provenance", {}).get("build_environment", {})
        current = build_environment()
        for key in ("python", "python_version", "abi", "builder"):
            if planned.get(key) != current.get(key):
                raise OperatorError(f"upgrade environment drift: {key}; create a new plan")
    runtime = root / plan["runtime"]
    if runtime.exists():
        raise OperatorError("planned runtime already exists")
    run([sys.executable, "-m", "venv", str(runtime)])
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    pip_check = run([str(python), "-m", "pip", "--version"], check=False)
    if pip_check.returncode == 0:
        run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
    elif shutil.which("uv"):
        run([shutil.which("uv"), "pip", "install", "--python", str(python), "--no-deps", str(wheel)])
    else:
        raise OperatorError("new runtime has no pip and uv is unavailable; canonical selection was not changed")
    written: list[str] = []
    previous = {item["path"]: (root / item["path"]).read_bytes() if (root / item["path"]).is_file() else None
                for item in plan["writes"]}
    try:
        for item in plan["writes"]:
            path = root / item["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item["content"], encoding="utf-8")
            written.append(item["path"])
        for item in plan["links"]:
            create_link(root, item)
        wrapper = [sys.executable, str(root / "tools/pkc.py")]
        results = []
        for command in (["capabilities"], ["validate"], ["rebuild"], ["validate"]):
            result = run([*wrapper, *command], cwd=root)
            results.append(json.loads(result.stdout))
        if "knowledge-check" in plan.get("verification", []):
            result = run([*wrapper, "knowledge-check", "--format", "json"], cwd=root)
            results.append(json.loads(result.stdout))
        origin = run([str(python), "-c", "import portable_knowledge; print(portable_knowledge.__file__)"], cwd=root).stdout.strip()
        if not Path(origin).resolve().is_relative_to(runtime.resolve()):
            raise OperatorError(f"module origin escaped target runtime: {origin}")
        for query in plan.get("representative_queries", []):
            result = run([*wrapper, "query", query, "--level", "2", "--format", "json"], cwd=root)
            results.append(json.loads(result.stdout))
        for check_command in plan.get("project_checks", []):
            result = subprocess.run(check_command, cwd=root, shell=True, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise OperatorError(f"reviewed project check failed ({result.returncode}): {check_command}\n{result.stderr.strip()}")
            results.append({"command": "project-check", "value": check_command, "ok": True})
    except Exception as exc:
        for rel, content in previous.items():
            path = root / rel
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise OperatorError(f"post-switch verification failed; prior selection restored; both runtimes preserved: {exc}") from exc
    return {"ok": True, "command": "apply-plan", "plan_hash": actual, "target": str(root),
            "runtime": plan["runtime"], "written": written, "links": [x["path"] for x in plan["links"]],
            "verification": results, "git_status": git_state(root)["status"],
            "next": "human reviews tracked diff; offer first-use; commit/push remain separate", "errors": []}


def wrapper_status(root: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    lock_path = root / "tools/pkc-lock.json"
    if not lock_path.is_file():
        return None, []
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    wrapper = root / "tools/pkc.py"
    checks = []
    for command in (["capabilities"], ["validate"]):
        result = run([sys.executable, str(wrapper), *command], cwd=root, check=False) if wrapper.is_file() else None
        checks.append({"command": command[0], "ok": bool(result and result.returncode == 0),
                       "output": result.stdout.strip() if result else "wrapper missing", "error": result.stderr.strip() if result else ""})
    return lock, checks


def command_status(args: argparse.Namespace, doctor: bool = False) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    inspected = inspect_target(root)
    lock, checks = wrapper_status(root)
    issues = []
    if inspected["project_state"] != "configured": issues.append("PKC integration is absent or partial")
    if lock and not inspected["runtime_exists"]: issues.append("locked runtime is missing")
    issues.extend(f"{x['command']} failed" for x in checks if not x["ok"])
    payload = {"ok": not issues, "command": "doctor" if doctor else "status", "root": str(root),
               "project_state": inspected["project_state"], "git": inspected["git"], "lock": lock,
               "checks": checks, "issues": issues, "repair_level": "R0 diagnosis only" if issues else "none",
               "errors": [] if not issues else [{"code": "OPERATOR_DEGRADED", "message": x} for x in issues]}
    return payload


def command_update(args: argparse.Namespace) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    lock_path = root / "tools/pkc-lock.json"
    if not lock_path.is_file(): raise OperatorError("project lock is missing")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    latest = resolve_commit(lock["source_repository"], args.ref)
    return {"ok": True, "command": "check-update", "current_commit": lock["source_commit"], "remote_commit": latest,
            "update_available": latest != lock["source_commit"], "automatic_upgrade": False,
            "next": "create and review a new exact-commit install/upgrade plan" if latest != lock["source_commit"] else "none", "errors": []}


def command_install_global(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source.resolve()
    skill = source / "skills/pkc-project-operator"
    if not (skill / "SKILL.md").is_file(): raise OperatorError(f"operator Skill not found: {skill}")
    commit = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.strip()
    if run(["git", "-C", str(source), "status", "--porcelain"]).stdout.strip():
        raise OperatorError("source repository must be clean before global Skill installation")
    roots = args.skill_root or [Path.home() / ".agents" / "skills", Path.home() / ".pi" / "agent" / "skills"]
    installed = []
    for root in roots:
        root = root.expanduser().resolve(); root.mkdir(parents=True, exist_ok=True)
        dest = root / "pkc-project-operator"
        if dest.is_symlink() and dest.resolve() == skill: installed.append(str(dest)); continue
        if dest.exists() or dest.is_symlink(): raise OperatorError(f"global Skill destination already exists: {dest}")
        if os.name == "nt": shutil.copytree(skill, dest); projection = "managed-copy"
        else: dest.symlink_to(skill, target_is_directory=True); projection = "symlink"
        installed.append(str(dest))
    manifest = {"schema_version": 1, "operator_contract": CONTRACT, "source_repository": str(source),
                "source_commit": commit, "skill_source": str(skill), "projections": installed,
                "projection_type": "managed-copy" if os.name == "nt" else "symlink"}
    path = CACHE / "operator-install.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "command": "install-global", "manifest": str(path), "installed": installed,
            "source_commit": commit, "note": "restart/rescan Agent harness to discover the Skill", "errors": []}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("inspect", "status", "doctor", "check-update"):
        child = sub.add_parser(name); child.add_argument("--target", type=Path, required=True)
        if name == "check-update": child.add_argument("--ref", default="main")
    plan = sub.add_parser("plan-install"); plan.add_argument("--target", type=Path, required=True); plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--remote", default=DEFAULT_REMOTE); plan.add_argument("--ref", default="main"); plan.add_argument("--project-id")
    adopt = sub.add_parser("plan-adopt"); adopt.add_argument("--target", type=Path, required=True); adopt.add_argument("--output", type=Path, required=True)
    adopt.add_argument("--remote", default=DEFAULT_REMOTE); adopt.add_argument("--ref", default="main")
    upgrade = sub.add_parser("plan-upgrade"); upgrade.add_argument("--target", type=Path, required=True)
    upgrade.add_argument("--source-repository", required=True); upgrade.add_argument("--source-commit", required=True)
    upgrade.add_argument("--output", type=Path, required=True)
    upgrade.add_argument("--representative-query", action="append", default=[])
    upgrade.add_argument("--project-check", action="append", default=[])
    apply = sub.add_parser("apply-plan"); apply.add_argument("--plan", type=Path, required=True); apply.add_argument("--plan-hash", required=True); apply.add_argument("--human-reviewed", action="store_true")
    global_install = sub.add_parser("install-global"); global_install.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[3]); global_install.add_argument("--skill-root", type=Path, action="append")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect": payload = inspect_target(args.target)
        elif args.command == "plan-install": payload = command_plan(args)
        elif args.command == "plan-adopt": payload = command_plan_adopt(args)
        elif args.command == "plan-upgrade": payload = command_plan_upgrade(args)
        elif args.command == "apply-plan": payload = command_apply(args)
        elif args.command == "status": payload = command_status(args)
        elif args.command == "doctor": payload = command_status(args, True)
        elif args.command == "check-update": payload = command_update(args)
        elif args.command == "install-global": payload = command_install_global(args)
        else: raise OperatorError(f"unsupported command: {args.command}")
    except (OperatorError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "command": getattr(args, "command", "unknown"), "errors": [{"code": "OPERATOR_ERROR", "message": str(exc)}]}
    return emit(payload)


if __name__ == "__main__":
    raise SystemExit(main())
