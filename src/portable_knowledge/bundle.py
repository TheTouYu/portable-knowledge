"""Immutable Semantic Change Bundles and atomic authority application."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

BUNDLE_TYPES = {"claim_create", "claim_revise", "permission_expansion", "lifecycle_change", "node_boundary_change", "memory_change"}
RISK_LEVELS = {"low", "medium", "high"}


class BundleError(Exception): pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and "\\" not in value and not path.is_absolute() and ".." not in path.parts and not value.startswith(".local/")


def build_bundle(root: Path, manifest: dict[str, Any], identities: dict[str, Any]) -> dict[str, Any]:
    """Normalize a manifest and lock its semantic content to authority hashes."""
    bundle_type = manifest.get("bundle_type")
    if bundle_type not in BUNDLE_TYPES: raise BundleError("bundle_type must be one controlled semantic class")
    if manifest.get("risk") not in RISK_LEVELS: raise BundleError("invalid risk")
    actions = manifest.get("actions")
    if not isinstance(actions, list) or not actions: raise BundleError("actions are required")
    normalized = []
    for action in actions:
        path = action.get("path", "")
        if action.get("operation") not in {"replace", "append"} or not _safe_path(path): raise BundleError(f"invalid action: {path}")
        target = root / path
        before = target.read_bytes() if target.exists() else b""
        supplied = action.get("content")
        if not isinstance(supplied, str): raise BundleError("action content must be UTF-8 text")
        addition = supplied.encode("utf-8")
        after = addition if action["operation"] == "replace" else before + addition
        normalized.append({"operation": action["operation"], "path": path, "expected_hash": hashlib.sha256(before).hexdigest() if target.exists() else None,
                           "before": base64.b64encode(before).decode("ascii"), "content": base64.b64encode(after).decode("ascii"), "new_hash": hashlib.sha256(after).hexdigest()})
    body = {"schema_version": 1, "bundle_type": bundle_type, "intent": manifest.get("intent"), "semantic_diff": manifest.get("semantic_diff"),
            "evidence_refs": manifest.get("evidence_refs", []), "authority_refs": manifest.get("authority_refs", []),
            "permission_effect": manifest.get("permission_effect", "none"), "actions": normalized,
            "expected_changed_files": sorted(a["path"] for a in normalized), "risk": manifest["risk"],
            "principal": identities["principal"]["id"], "executor": identities["executor"]["id"],
            "workspace": identities["workspace"]["id"], "writer": identities["writer"]["id"]}
    if not body["intent"] or not body["semantic_diff"]: raise BundleError("intent and semantic_diff are required")
    content_hash = digest(body)
    return {**body, "bundle_id": f"bnd_{content_hash[:26]}", "content_hash": content_hash}


def verify_bundle(bundle: dict[str, Any]) -> None:
    claimed = bundle.get("content_hash")
    body = {k: v for k, v in bundle.items() if k not in {"bundle_id", "content_hash"}}
    actual = digest(body)
    if claimed != actual or bundle.get("bundle_id") != f"bnd_{actual[:26]}": raise BundleError("bundle content hash mismatch")
    if sorted(a["path"] for a in bundle.get("actions", [])) != bundle.get("expected_changed_files"): raise BundleError("changed file declaration mismatch")


def bundle_paths(root: Path, bundle_id: str) -> tuple[Path, Path, Path]:
    base = root / "data/knowledge/bundles"
    return base / f"{bundle_id}.json", base / f"{bundle_id}.approval.json", base / f"{bundle_id}.applied.json"


def approval(bundle: dict[str, Any], principal: str) -> dict[str, Any]:
    verify_bundle(bundle)
    if principal != bundle["principal"]: raise BundleError("only the configured principal may approve")
    body = {"schema_version": 1, "bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"], "principal": principal}
    return {**body, "approval_hash": digest(body)}


def verify_approval(bundle: dict[str, Any], value: dict[str, Any]) -> None:
    expected = approval(bundle, value.get("principal", ""))
    if value != expected: raise BundleError("approval is invalid or stale")


def apply_bundle(root: Path, bundle: dict[str, Any], approved: dict[str, Any], replace: Callable[..., list[str]]) -> list[str]:
    verify_bundle(bundle); verify_approval(bundle, approved)
    writes: dict[str, bytes] = {}
    for action in bundle["actions"]:
        target = root / action["path"]
        old = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if old != action["expected_hash"]: raise BundleError(f"authority changed: {action['path']}")
        content = base64.b64decode(action["content"], validate=True)
        if hashlib.sha256(content).hexdigest() != action["new_hash"]: raise BundleError("action content hash mismatch")
        writes[action["path"]] = content
    return replace(root, "bundle-apply", writes)


def rollback_bundle(root: Path, bundle: dict[str, Any], replace: Callable[..., list[str]]) -> list[str]:
    verify_bundle(bundle)
    writes = {}
    for action in bundle["actions"]:
        target = root / action["path"]
        current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if current != action["new_hash"]: raise BundleError(f"cannot rollback changed authority: {action['path']}")
        writes[action["path"]] = base64.b64decode(action["before"], validate=True)
    return replace(root, "bundle-rollback", writes)
