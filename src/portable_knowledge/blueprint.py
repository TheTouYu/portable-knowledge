"""Candidate/Approved Blueprint validation and deterministic initialization."""
from __future__ import annotations
import hashlib, json
from pathlib import Path, PurePosixPath
from typing import Any
from .profile import MEMORY_MAPPING_STATES, profile_hash, validate_profile

class BlueprintError(Exception): pass

def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()
def _safe(path: str) -> bool:
    value = PurePosixPath(path)
    return bool(path) and "\\" not in path and not value.is_absolute() and ".." not in value.parts and not path.startswith(".local/")

def validate_candidate(value: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    def fail(code: str, message: str): errors.append({"code": code, "path": "candidate", "message": message})
    if not validate_profile(profile)["ok"]: fail("BLUEPRINT_PROFILE", "profile is invalid")
    if value.get("authority") is not False: fail("BLUEPRINT_AUTHORITY", "candidate must explicitly be non-authority")
    if value.get("production_task") != profile.get("primary_production_task"): fail("BLUEPRINT_TASK", "primary production task is not covered")
    nodes = value.get("nodes", [])
    if not 1 <= len(nodes) <= 8: fail("BLUEPRINT_SCALE", "node count must be 1..8")
    ids: list[str] = []
    topics = 0
    for node in nodes:
        ids.append(str(node.get("id", "")))
        for topic in node.get("topics", []): ids.append(str(topic.get("id", ""))); topics += 1
    if not 1 <= topics <= 20: fail("BLUEPRINT_SCALE", "topic count must be 1..20")
    if any(not item or not item.replace("-", "").isalnum() for item in ids) or len(ids) != len(set(ids)): fail("BLUEPRINT_ID", "IDs must be unique portable slugs")
    if set(value.get("include", [])) & set(value.get("exclude", [])): fail("BLUEPRINT_BOUNDARY", "include/exclude overlap")
    role_keys = set()
    for role in value.get("memory_roles", []):
        if role.get("status") not in MEMORY_MAPPING_STATES: fail("BLUEPRINT_MEMORY", "invalid memory mapping status")
        key = (role.get("role"), role.get("path"))
        if key in role_keys: fail("BLUEPRINT_DUPLICATE", "duplicate memory role mapping")
        role_keys.add(key)
    for output in value.get("files", []):
        if not _safe(output.get("path", "")) or not isinstance(output.get("content"), str): fail("BLUEPRINT_FILE", "output needs safe path and text content")
    if "claims" in value: fail("BLUEPRINT_CLAIM", "blueprints must not generate business claims")
    return {"ok": not errors, "command": "validate-blueprint", "counts": {"nodes": len(nodes), "topics": topics}, "errors": errors}

def approve_blueprint(candidate: dict[str, Any], provenance: dict[str, Any], principal: str, explicit: bool) -> dict[str, Any]:
    if not explicit: raise BlueprintError("explicit user approval is required")
    required = {"profile_hash", "pack", "model", "read_paths", "excluded_paths", "working_tree", "candidate_ids", "user_decisions"}
    if required - set(provenance): raise BlueprintError("incomplete blueprint provenance")
    if candidate.get("candidate_id") not in provenance["candidate_ids"]: raise BlueprintError("approved candidate is absent from provenance")
    body = {"schema_version": 1, "candidate": candidate, "provenance": provenance, "approved_by": principal}
    digest = _digest(body)
    return {**body, "approval_id": f"abp_{digest[:26]}", "approved_hash": digest}

def verify_approved(value: dict[str, Any]) -> None:
    body = {k: v for k, v in value.items() if k not in {"approval_id", "approved_hash"}}
    digest = _digest(body)
    if value.get("approved_hash") != digest or value.get("approval_id") != f"abp_{digest[:26]}": raise BlueprintError("approved blueprint hash mismatch")

def apply_blueprint(root: Path, approved: dict[str, Any], apply: bool = False) -> dict[str, Any]:
    verify_approved(approved)
    files = approved["candidate"].get("files", [])
    conflicts, creates, unchanged = [], [], []
    for output in sorted(files, key=lambda item: item["path"]):
        target, expected = root / output["path"], output["content"].encode()
        if target.exists():
            if target.read_bytes() == expected: unchanged.append(output["path"])
            else: conflicts.append(output["path"])
        else: creates.append(output["path"])
    if conflicts: raise BlueprintError(f"initialization would overwrite existing files: {conflicts}")
    if apply:
        for output in sorted(files, key=lambda item: item["path"]):
            target = root / output["path"]
            if not target.exists(): target.parent.mkdir(parents=True, exist_ok=True); target.write_text(output["content"], encoding="utf-8", newline="\n")
    return {"ok": True, "command": "blueprint-apply", "applied": apply, "dry_run": not apply, "created_files": creates if apply else [], "would_create": creates, "unchanged_files": unchanged, "conflicts": [], "approved_hash": approved["approved_hash"]}
