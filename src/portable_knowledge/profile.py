"""Existing Project Profile and bounded discovery contracts."""
from __future__ import annotations
import hashlib, json, re
from pathlib import PurePosixPath
from typing import Any

MEMORY_MAPPING_STATES = {"mapped", "missing", "ambiguous", "scope_mismatch", "stale_candidate"}
BASELINE_STATES = {"committed_baseline", "working_tree_observation", "released_baseline", "external_environment"}
FORBIDDEN_PREFIXES = (".git/", "node_modules/", "vendor/", "dist/", "build/", ".local/")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+"),
)

class DiscoveryError(Exception): pass

def _path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts

def _report(command: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    return {"ok": not errors, "command": command, "errors": errors}

def profile_hash(profile: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def validate_profile(value: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    def fail(code: str, message: str): errors.append({"code": code, "path": "profile", "message": message})
    required = {"schema_version", "project", "primary_production_task", "machine_truth_sources", "memory_role_candidates", "input_types", "evidence_types", "state_sources", "policy", "completion_gates", "exclusions"}
    if required - set(value): fail("PROFILE_SCHEMA", f"missing: {sorted(required-set(value))}")
    project = value.get("project", {})
    if not all(project.get(k) for k in ("id", "name", "goal")) or not project.get("users"): fail("PROFILE_PROJECT", "project identity, goal, and users are required")
    if not isinstance(value.get("primary_production_task"), str) or not value.get("primary_production_task"): fail("PROFILE_TASK", "exactly one primary production task string is required")
    for source in value.get("machine_truth_sources", []):
        if not _path(source.get("path")) or source.get("state") not in BASELINE_STATES: fail("PROFILE_TRUTH_SOURCE", "truth source needs portable path and baseline state")
    for role in value.get("memory_role_candidates", []):
        if role.get("status") not in MEMORY_MAPPING_STATES: fail("PROFILE_MEMORY_ROLE", "invalid mapping status")
    states = value.get("state_sources", {})
    if set(states) != {"committed", "working", "released", "external"}: fail("PROFILE_STATES", "committed, working, released, and external sources are required")
    policy = value.get("policy", {})
    if not policy.get("permissions") or not policy.get("remote_models"): fail("PROFILE_POLICY", "permission and remote model policy are required")
    if not value.get("completion_gates") or not isinstance(value.get("exclusions"), list): fail("PROFILE_BOUNDARY", "completion gates and exclusions are required")
    return _report("validate-profile", errors)

def validate_discovery_manifest(value: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    def fail(code: str, message: str): errors.append({"code": code, "path": "discovery_manifest", "message": message})
    required = {"schema_version", "read_paths", "excluded_paths", "expansions", "working_tree", "model"}
    if required - set(value): fail("DISCOVERY_SCHEMA", f"missing: {sorted(required-set(value))}")
    for path in value.get("read_paths", []):
        if not _path(path) or path == ".env" or path.startswith(FORBIDDEN_PREFIXES): fail("DISCOVERY_PATH", f"default read is forbidden: {path}")
    for expansion in value.get("expansions", []):
        if not expansion.get("reason") or not expansion.get("paths"): fail("DISCOVERY_EXPANSION", "expanded scope needs reason and paths")
    model = value.get("model", {})
    if model.get("transfer") not in {"full_text", "local_summary"} or not model.get("provider") or not model.get("name"): fail("DISCOVERY_MODEL", "provider, model, and transfer mode are required")
    if not isinstance(value.get("working_tree"), dict): fail("DISCOVERY_WORKTREE", "working-tree state is required")
    return _report("validate-discovery", errors)

def prepare_remote_input(contents: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    """Fail closed before constructing any remote-model payload."""
    validation = validate_discovery_manifest(manifest)
    if not validation["ok"]: raise DiscoveryError(str(validation["errors"]))
    allowed = set(manifest["read_paths"])
    selected: dict[str, str] = {}
    for path, text in contents.items():
        if path == ".env" or path not in allowed: raise DiscoveryError(f"unauthorized remote input: {path}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS): raise DiscoveryError(f"secret detected before remote call: {path}")
        selected[path] = text
    return {"provider": manifest["model"]["provider"], "model": manifest["model"]["name"], "content_mode": manifest["model"]["transfer"], "paths": sorted(selected), "contents": selected}
