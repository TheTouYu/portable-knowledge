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
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_REMOTE = "https://github.com/TheTouYu/portable-knowledge.git"
CONTRACT = "0.1"
CACHE = Path.home() / ".local" / "share" / "portable-knowledge"


class OperatorError(Exception):
    pass


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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


def ensure_wheel(remote: str, commit: str) -> tuple[Path, str, str]:
    wheel_dir = CACHE / "wheels" / commit
    metadata_path = wheel_dir / "metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        wheel = wheel_dir / metadata["filename"]
        if wheel.is_file() and digest_file(wheel) == metadata["sha256"]:
            return wheel, metadata["sha256"], metadata["version"]
    wheel_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pkc-build-") as directory:
        checkout = Path(directory) / "source"
        run(["git", "clone", "--quiet", "--no-checkout", remote, str(checkout)])
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", commit])
        if run(["git", "-C", str(checkout), "status", "--porcelain"]).stdout.strip():
            raise OperatorError("build checkout is not clean")
        output = Path(directory) / "dist"
        uv = shutil.which("uv")
        if not uv:
            raise OperatorError("uv is required to build a locked wheel from a remote commit")
        run([uv, "build", "--wheel", "--out-dir", str(output)], cwd=checkout)
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1:
            raise OperatorError("expected exactly one wheel")
        wheel = wheels[0]
        target = wheel_dir / wheel.name
        shutil.copy2(wheel, target)
        sha = digest_file(target)
        match = re.match(r"portable_knowledge-([^-]+)-", target.name)
        if not sha or not match:
            raise OperatorError("cannot identify built wheel")
        version = match.group(1)
        metadata_path.write_text(json.dumps({"filename": target.name, "sha256": sha, "version": version,
                                             "source_repository": remote, "source_commit": commit}, indent=2) + "\n", encoding="utf-8")
        return target, sha, version


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
        "authority": {"registry": "data/knowledge/registry.json", "actors": "data/knowledge/actors.json", "store": "data/knowledge", "knowledge": "knowledge"},
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
    refs = {"schema_version": 1, "authority_refs": []}
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


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = git_root(args.target.resolve())
    existing = inspect_target(root)
    if existing["project_state"] != "unconfigured":
        raise OperatorError("target already has partial/full PKC configuration; use doctor or upgrade")
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
    runtime = root / plan["runtime"]
    if runtime.exists():
        raise OperatorError("planned runtime already exists")
    run([sys.executable, "-m", "venv", str(runtime)])
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
    written: list[str] = []
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
    except Exception:
        # Preserve evidence; do not guess rollback over pre-existing files. Runtime is disposable.
        raise
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
    apply = sub.add_parser("apply-plan"); apply.add_argument("--plan", type=Path, required=True); apply.add_argument("--plan-hash", required=True); apply.add_argument("--human-reviewed", action="store_true")
    global_install = sub.add_parser("install-global"); global_install.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[3]); global_install.add_argument("--skill-root", type=Path, action="append")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect": payload = inspect_target(args.target)
        elif args.command == "plan-install": payload = command_plan(args)
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
