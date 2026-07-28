"""Project instance configuration and bounded Project Memory validation."""
from __future__ import annotations

import fnmatch
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

CONFIG_NAME = "project-intelligence.json"
MUTATION_POLICIES = {"replace", "append", "supersede", "curated_history", "reference"}
REQUIRED_ROLES = {"operating_entry", "current_recovery", "decision_entry"}
CONTEXT_STATES = {"planned", "active", "paused", "completed", "archived"}


class InstanceError(Exception):
    pass


@dataclass(frozen=True)
class Instance:
    root: Path
    config_path: Path
    raw: dict[str, Any]

    @property
    def identity(self) -> dict[str, Any]: return self.raw["instance"]
    @property
    def authority(self) -> dict[str, Any]: return self.raw["authority"]
    @property
    def identities(self) -> dict[str, Any]: return self.raw["identities"]
    @property
    def projection_path(self) -> Path: return Path(self.raw["pkc"]["projection_path"])


def _relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def load_instance(root: Path, config: Path | None = None) -> Instance:
    root = root.resolve()
    path = config.resolve() if config else root / CONFIG_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstanceError(f"invalid instance config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise InstanceError("instance config must be an object")
    return Instance(root, path, raw)


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def validate_project_memory(instance: Instance) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    raw, root = instance.raw, instance.root
    def error(code: str, path: str, message: str) -> None: errors.append({"code": code, "path": path, "message": message})
    required = {"schema_version", "instance", "pkc", "authority", "identities", "memory"}
    for key in sorted(required - set(raw)): error("INSTANCE_SCHEMA", CONFIG_NAME, f"missing {key}")
    if raw.get("schema_version") != 1: error("INSTANCE_SCHEMA", CONFIG_NAME, "schema_version must be 1")
    identity = raw.get("instance", {})
    if not all(isinstance(identity.get(k), str) and identity[k] for k in ("id", "name")): error("INSTANCE_IDENTITY", CONFIG_NAME, "instance id and name are required")
    authority = raw.get("authority", {})
    for key in ("registry", "actors", "store", "knowledge"):
        value = authority.get(key)
        if not _relative(value): error("AUTHORITY_PATH", CONFIG_NAME, f"invalid authority path: {key}")
        elif not (root / value).exists(): error("AUTHORITY_MISSING", str(value), "configured authority path does not exist")
    refs_path = authority.get("authority_refs")
    if refs_path is not None:
        if not _relative(refs_path): error("AUTHORITY_PATH", CONFIG_NAME, "invalid authority path: authority_refs")
        elif not (root / refs_path).is_file(): error("AUTHORITY_MISSING", str(refs_path), "configured authority refs file does not exist")
    identities = raw.get("identities", {})
    for key in ("principal", "executor", "workspace", "writer"):
        if not isinstance(identities.get(key), dict) or not identities[key].get("id"): error("IDENTITY_MISSING", CONFIG_NAME, f"missing {key}.id")
    principal_id = identities.get("principal", {}).get("id")
    mappings = raw.get("compatibility", {}).get("v1_actor_map", {})
    if not isinstance(mappings, dict) or any(not isinstance(v, str) or v != principal_id for v in mappings.values()):
        error("ACTOR_MAPPING", CONFIG_NAME, "v1 actors must map explicitly to the configured principal")
    memory = raw.get("memory", {})
    roles = memory.get("roles", [])
    role_names = {role.get("role") for role in roles if isinstance(role, dict)}
    for missing in sorted(REQUIRED_ROLES - role_names): error("MEMORY_ROLE_MISSING", CONFIG_NAME, f"missing role {missing}")
    for role in roles:
        path, policy = role.get("path"), role.get("mutation_policy")
        if not _relative(path): error("MEMORY_ROLE_PATH", CONFIG_NAME, f"invalid role path: {path}")
        elif not (root / path).is_file(): error("MEMORY_ROLE_FILE", str(path), "role file does not exist")
        if policy not in MUTATION_POLICIES: error("MUTATION_POLICY", CONFIG_NAME, f"invalid policy: {policy}")
    contexts = memory.get("contexts", [])
    defaults = [c for c in contexts if c.get("default")]
    if len(defaults) != 1: error("MEMORY_CONTEXT", CONFIG_NAME, "exactly one default context is required")
    for context in contexts:
        if context.get("lifecycle") not in CONTEXT_STATES: error("MEMORY_CONTEXT", CONFIG_NAME, "invalid context lifecycle")
        if not context.get("goal") or not context.get("recovery_role") or not context.get("validation_gate"): error("MEMORY_CONTEXT", CONFIG_NAME, "context needs goal, recovery_role, and validation_gate")
    budget = memory.get("startup_budget", {})
    if not isinstance(budget.get("max_files"), int) or budget.get("max_files", 0) < 1 or len(roles) > budget.get("max_files", 0): error("STARTUP_BUDGET", CONFIG_NAME, "startup max_files is missing or exceeded")
    if not isinstance(budget.get("max_characters"), int) or budget.get("max_characters", 0) < 1: error("STARTUP_BUDGET", CONFIG_NAME, "startup max_characters is invalid")
    evaluation = raw.get("evaluation", {})
    cases_path = evaluation.get("cases_path")
    if cases_path is not None:
        if not _relative(cases_path): error("EVALUATION_PATH", CONFIG_NAME, "evaluation.cases_path must be project-relative")
        elif not (root / cases_path).is_file(): error("EVALUATION_MISSING", cases_path, "configured evaluation cases file does not exist")
    experience = raw.get("experience", {})
    for key in ("current_surfaces", "count_surfaces", "upstream_locks"):
        values = experience.get(key, [])
        if not isinstance(values, list) or any(not _relative(value) for value in values):
            error("EXPERIENCE_PATH", CONFIG_NAME, f"experience.{key} must contain project-relative paths")
    markers = experience.get("stale_markers", [])
    if not isinstance(markers, list) or any(not isinstance(value, str) or not value for value in markers):
        error("EXPERIENCE_MARKER", CONFIG_NAME, "experience.stale_markers must contain non-empty strings")
    proof_boundary = experience.get("proof_boundary")
    if proof_boundary is not None and (not isinstance(proof_boundary, str) or not proof_boundary.strip()):
        error("EXPERIENCE_BOUNDARY", CONFIG_NAME, "experience.proof_boundary must be a non-empty string")
    scope = memory.get("applies_to", {})
    configured_root = scope.get("workspace", ".")
    if configured_root != ".": error("MEMORY_SCOPE", CONFIG_NAME, "workspace must identify the instance root with '.'")
    branch = _git(root, "branch", "--show-current")
    patterns = scope.get("branches", ["*"])
    if branch and not any(fnmatch.fnmatch(branch, p) for p in patterns): error("MEMORY_SCOPE", CONFIG_NAME, f"branch {branch} is outside applies_to")
    return {"ok": not errors, "command": "validate-memory", "counts": {"roles": len(roles), "contexts": len(contexts)}, "errors": sorted(errors, key=lambda x: (x["path"], x["code"]))}
