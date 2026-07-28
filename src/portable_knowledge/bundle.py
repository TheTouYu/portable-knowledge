"""Immutable Semantic Change Bundles and atomic authority application."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

BUNDLE_TYPES = {"source_evidence", "claim_create", "claim_revise", "authority_maintenance", "knowledge_structure_change", "knowledge_refactor", "permission_expansion", "lifecycle_change", "node_boundary_change", "memory_change"}
RISK_LEVELS = {"low", "medium", "high"}
LIFECYCLE_EVENTS = {"bundle_failed", "bundle_abandoned", "bundle_superseded", "bundle_rolled_back"}


class BundleError(Exception): pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def overlay_digest(actions: list[dict[str, Any]]) -> str:
    """Hash the exact ordered after-images (including deletions) validated before approval."""
    return digest([{"operation": action["operation"], "path": action["path"], "new_hash": action["new_hash"]} for action in actions])


def seal_preflight(bundle: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Add the successful staged-validation contract and refresh immutable identity."""
    if findings:
        raise BundleError("cannot seal a failed preflight")
    body = {key: value for key, value in bundle.items() if key not in {"bundle_id", "content_hash", "preflight"}}
    body["preflight"] = {
        "ok": True,
        "validator": "staged-authority-v1",
        "validated_content_hash": overlay_digest(body["actions"]),
        "checks": ["schema", "authority_ref", "authority_fact_coverage", "claim", "events"],
    }
    content_hash = digest(body)
    return {**body, "bundle_id": f"bnd_{content_hash[:26]}", "content_hash": content_hash}


def build_migration_plan(children: list[dict[str, Any]], *, dependencies: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Build a read-only hierarchical approval manifest; it does not apply children."""
    if not children:
        raise BundleError("migration plan needs child Bundles")
    dependencies = dependencies or {}
    child_ids = [child["bundle_id"] for child in children]
    if len(child_ids) != len(set(child_ids)):
        raise BundleError("migration plan child Bundles must be unique")
    for child in children:
        verify_bundle(child)
    for child_id, requirements in dependencies.items():
        if child_id not in child_ids or any(required not in child_ids for required in requirements):
            raise BundleError("migration plan dependency references an unknown child")
        if any(child_ids.index(required) >= child_ids.index(child_id) for required in requirements):
            raise BundleError("migration plan dependencies must point to earlier children")
    body = {"schema_version": 1, "children": [{"bundle_id": child["bundle_id"], "content_hash": child["content_hash"], "risk": child["risk"],
                                                 "permission_effect": child.get("permission_effect", "none"), "depends_on": dependencies.get(child["bundle_id"], [])}
                                                for child in children],
            "cross_phase_atomic": False, "failure_policy": "stop", "recovery": "forward_or_compensating_rollback",
            "permission_expansion_requires_independent_approval": True}
    content_hash = digest(body)
    return {**body, "plan_id": f"mig_{content_hash[:26]}", "content_hash": content_hash}


def verify_migration_plan(plan: dict[str, Any], bundles: dict[str, dict[str, Any]]) -> None:
    body = {key: value for key, value in plan.items() if key not in {"plan_id", "content_hash"}}
    actual = digest(body)
    if plan.get("content_hash") != actual or plan.get("plan_id") != f"mig_{actual[:26]}":
        raise BundleError("migration plan content hash mismatch")
    for child in plan.get("children", []):
        bundle = bundles.get(child["bundle_id"])
        if not bundle or bundle.get("content_hash") != child["content_hash"]:
            raise BundleError(f"migration plan child hash mismatch: {child['bundle_id']}")
        verify_bundle(bundle)


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and "\\" not in value and not path.is_absolute() and ".." not in path.parts and not value.startswith(".local/")


def _controlled_authority_path(path: str) -> bool:
    lower = path.casefold()
    return ("registry" in PurePosixPath(path).name.casefold() or "authority-ref" in lower or
            lower.endswith(".md") or "/routes" in lower or "evaluation" in lower)


def _provenance_for(action: dict[str, Any], *, path: str, new_hash: str) -> dict[str, Any] | None:
    value = action.get("provenance")
    required = {"plan_id", "operation_id", "operation_type", "operation_digest", "core_version"}
    if not isinstance(value, dict) or set(value) < required:
        return None
    descriptor = {"plan_id": value["plan_id"], "operation_type": value["operation_type"],
                  "core_version": value["core_version"], "path": path, "new_hash": new_hash}
    actual = digest(descriptor)
    if value["operation_digest"] != actual or value["operation_id"] != f"op_{actual[:26]}":
        raise BundleError("action provenance does not match canonical action content")
    return {key: value[key] for key in sorted(required)}


def enforce_production_provenance(bundle: dict[str, Any]) -> None:
    for action in bundle.get("actions", []):
        if _controlled_authority_path(action.get("path", "")) and not action.get("provenance"):
            raise BundleError("controlled authority action requires Core semantic-plan provenance; use explicit compatibility mode only for maintainer fixtures/recovery")


def build_bundle(root: Path, manifest: dict[str, Any], identities: dict[str, Any], *, compatibility_mode: bool = False) -> dict[str, Any]:
    """Normalize a manifest and lock its semantic content to authority hashes."""
    bundle_type = manifest.get("bundle_type")
    if bundle_type not in BUNDLE_TYPES: raise BundleError("bundle_type must be one controlled semantic class")
    if manifest.get("risk") not in RISK_LEVELS: raise BundleError("invalid risk")
    actions = manifest.get("actions")
    if not isinstance(actions, list) or not actions: raise BundleError("actions are required")
    normalized = []
    for action in actions:
        path = action.get("path", "")
        if action.get("operation") not in {"replace", "append", "delete"} or not _safe_path(path): raise BundleError(f"invalid action: {path}")
        target = root / path
        existed = target.exists()
        before = target.read_bytes() if existed else b""
        supplied = action.get("content")
        if action["operation"] == "delete":
            if not existed:
                raise BundleError(f"cannot delete missing authority: {path}")
            after = None
        else:
            if not isinstance(supplied, str): raise BundleError("action content must be UTF-8 text")
            addition = supplied.encode("utf-8")
            after = addition if action["operation"] == "replace" else before + addition
        new_hash = hashlib.sha256(after).hexdigest() if after is not None else None
        provenance = _provenance_for(action, path=path, new_hash=new_hash)
        if _controlled_authority_path(path) and provenance is None and not compatibility_mode:
            raise BundleError("controlled authority action requires Core semantic-plan provenance; use explicit compatibility mode only for maintainer fixtures/recovery")
        normalized_action = {"operation": action["operation"], "path": path, "expected_hash": hashlib.sha256(before).hexdigest() if existed else None,
                             "before": base64.b64encode(before).decode("ascii"),
                             "content": base64.b64encode(after).decode("ascii") if after is not None else None,
                             "new_hash": new_hash}
        if provenance is not None:
            normalized_action["provenance"] = provenance
        normalized.append(normalized_action)
    body = {"schema_version": 1, "bundle_type": bundle_type, "intent": manifest.get("intent"), "semantic_diff": manifest.get("semantic_diff"),
            "evidence_refs": manifest.get("evidence_refs", []), "authority_refs": manifest.get("authority_refs", []),
            "permission_effect": manifest.get("permission_effect", "none"), "actions": normalized,
            "expected_changed_files": sorted(a["path"] for a in normalized), "risk": manifest["risk"],
            "principal": identities["principal"]["id"], "executor": identities["executor"]["id"],
            "workspace": identities["workspace"]["id"], "writer": identities["writer"]["id"]}
    if not body["intent"] or not body["semantic_diff"]: raise BundleError("intent and semantic_diff are required")
    content_hash = digest(body)
    return {**body, "bundle_id": f"bnd_{content_hash[:26]}", "content_hash": content_hash}


def capture_bundle_draft(root: Path, request: dict[str, Any], identities: dict[str, Any], preflight: Callable[[dict[str, Any]], dict[str, Any]] | None = None, *, compatibility_mode: bool = False) -> dict[str, Any]:
    """Run required intake declarations and return an immutable Bundle draft without writing it."""
    required = {"duplicate", "conflict", "authority", "scope", "repository_state", "deletion_test"}
    checks = request.get("capture_checks")
    if not isinstance(checks, dict) or required - set(checks) or any(checks.get(key) in {None, "", "not_checked"} for key in required):
        raise BundleError("capture_checks must declare duplicate, conflict, authority, scope, repository_state, and deletion_test")
    # Compatibility construction permits complete read-only staged diagnostics first.
    # A successful normal-mode draft is still rejected before any Bundle write.
    bundle = build_bundle(root, request, identities, compatibility_mode=True)
    if preflight is not None:
        bundle = preflight(bundle)
    if not compatibility_mode:
        enforce_production_provenance(bundle)
    return {"ok": True, "command": "capture", "draft_only": True, "approved": False, "applied": False,
            "checks": {key: checks[key] for key in sorted(required)}, "preflight": bundle.get("preflight"), "bundle_id": bundle["bundle_id"],
            "content_hash": bundle["content_hash"], "expected_changed_files": bundle["expected_changed_files"],
            "bundle": bundle, "errors": []}


def verify_bundle(bundle: dict[str, Any]) -> None:
    claimed = bundle.get("content_hash")
    body = {k: v for k, v in bundle.items() if k not in {"bundle_id", "content_hash"}}
    actual = digest(body)
    if claimed != actual or bundle.get("bundle_id") != f"bnd_{actual[:26]}": raise BundleError("bundle content hash mismatch")
    if sorted(a["path"] for a in bundle.get("actions", [])) != bundle.get("expected_changed_files"): raise BundleError("changed file declaration mismatch")


def bundle_paths(root: Path, bundle_id: str) -> tuple[Path, Path, Path]:
    base = root / "data/knowledge/bundles"
    return base / f"{bundle_id}.json", base / f"{bundle_id}.approval.json", base / f"{bundle_id}.applied.json"


def lifecycle_path(root: Path, bundle_id: str) -> Path:
    return root / "data/knowledge/bundles" / f"{bundle_id}.lifecycle.jsonl"


def lifecycle_projection(bundle: dict[str, Any], *, approved: bool, applied: bool, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Project state from immutable files and ordered append-only lifecycle events."""
    state = "applied" if applied else ("approved" if approved else "draft")
    result: dict[str, Any] = {"state": state, "failure_phase": None, "superseded_by": None, "reason": None, "transaction_id": None}
    for event in events:
        event_type = event.get("event_type")
        if event_type not in LIFECYCLE_EVENTS or event.get("bundle_id", bundle["bundle_id"]) != bundle["bundle_id"]:
            continue
        if event_type == "bundle_failed":
            result.update(state="failed", failure_phase=event.get("failure_phase"), reason=event.get("reason"), transaction_id=event.get("transaction_id"))
        elif event_type == "bundle_abandoned":
            result.update(state="abandoned", reason=event.get("reason"))
        elif event_type == "bundle_superseded":
            result.update(state="superseded", superseded_by=event.get("superseded_by"), reason=event.get("reason"))
        elif event_type == "bundle_rolled_back":
            result.update(state="rolled_back", reason=event.get("reason"), transaction_id=event.get("transaction_id"))
    return result


def approval(bundle: dict[str, Any], principal: str) -> dict[str, Any]:
    verify_bundle(bundle)
    preflight = bundle.get("preflight", {})
    if not preflight.get("ok") or preflight.get("validator") != "staged-authority-v1" or preflight.get("validated_content_hash") != overlay_digest(bundle.get("actions", [])):
        raise BundleError("bundle lacks a valid successful staged preflight")
    if principal != bundle["principal"]: raise BundleError("only the configured principal may approve")
    body = {"schema_version": 1, "bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"], "principal": principal}
    return {**body, "approval_hash": digest(body)}


def verify_approval(bundle: dict[str, Any], value: dict[str, Any]) -> None:
    expected = approval(bundle, value.get("principal", ""))
    if value != expected: raise BundleError("approval is invalid or stale")


def apply_bundle(root: Path, bundle: dict[str, Any], approved: dict[str, Any], replace: Callable[..., list[str]]) -> list[str]:
    verify_bundle(bundle); verify_approval(bundle, approved)
    writes: dict[str, bytes | None] = {}
    for action in bundle["actions"]:
        target = root / action["path"]
        old = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if old != action["expected_hash"]: raise BundleError(f"authority changed: {action['path']}")
        if action["operation"] == "delete":
            if action.get("content") is not None or action.get("new_hash") is not None:
                raise BundleError("delete action must have a null after-image")
            writes[action["path"]] = None
            continue
        content = base64.b64decode(action["content"], validate=True)
        if hashlib.sha256(content).hexdigest() != action["new_hash"]: raise BundleError("action content hash mismatch")
        writes[action["path"]] = content
    return replace(root, "bundle-apply", writes)


def rollback_bundle(root: Path, bundle: dict[str, Any], replace: Callable[..., list[str]]) -> list[str]:
    verify_bundle(bundle)
    writes: dict[str, bytes | None] = {}
    for action in bundle["actions"]:
        target = root / action["path"]
        current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if current != action["new_hash"]: raise BundleError(f"cannot rollback changed authority: {action['path']}")
        before = base64.b64decode(action["before"], validate=True)
        writes[action["path"]] = before if action["expected_hash"] is not None else None
    return replace(root, "bundle-rollback", writes)
