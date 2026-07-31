"""Deterministic, disposable Semantic Operation Plan overlay."""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .authority import (FACT_CLASSES, authority_refs_from_document, canonical_authority_document,
                        validate_authority_coverage, validate_authority_ref)
from .bundle import (build_bundle, canonical as bundle_bytes, digest as canonical_digest,
                     lifecycle_projection)
from .evaluation_contract import (EvaluationContractError, evaluate_normalized_cases,
                                  load_evaluation_contract, select_delta_cases)
from .instance import Instance

CORE_PLAN_VERSION = "semantic-plan-v2"
PERMISSION_RANK = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}
STDOUT_CHARACTER_BUDGET = 4096
DEFAULT_BUDGETS = {
    "max_candidate_bundles": 2,
    "max_full_preflight": 1,
    "max_tool_gap": 1,
    "max_noop_actions": 0,
}
COUNTER_KEYS = (
    "operations", "candidate_bundles", "delta_checks", "full_checks",
    "full_preflight_checks", "post_apply_full_checks", "changed_files",
    "semantic_amplification", "noop_actions", "tool_gap",
)


def _core():
    from . import core
    return core


def _fail(code: str, message: str, *, path: str = ".", **details: Any) -> None:
    core = _core()
    finding = {"code": code, "path": path, "message": message, **details}
    raise core.SemanticPlanError(code, message, [finding])


def _git(root: Path, *args: str, text: bool = False) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=text, encoding="utf-8" if text else None, check=False)


def _head(root: Path) -> str:
    result = _git(root, "rev-parse", "HEAD", text=True)
    if result.returncode:
        _fail("PLAN_GIT_BASELINE", "semantic plan requires a committed Git baseline")
    return result.stdout.strip()


def _committed_bytes(root: Path, baseline: str, path: str) -> bytes | None:
    result = _git(root, "show", f"{baseline}:{path}")
    return result.stdout if result.returncode == 0 else None


def _runtime_version() -> str:
    return _core()._runtime_version()


def _local_base(instance: Instance) -> Path:
    return instance.projection_path / "semantic-plans"


def _plan_path(root: Path, instance: Instance, plan_id: str) -> Path:
    return root / _local_base(instance) / f"{plan_id}.json"


def _artifact_rel(instance: Instance, digest: str, kind: str) -> str:
    return (_local_base(instance) / "artifacts" / f"{digest}.{kind}.json").as_posix()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _save(path: Path, plan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(_canonical(plan))
    temporary.replace(path)


def _write_artifact(root: Path, rel: str, value: Any) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value))


def _load(root: Path, instance: Instance, plan_id: str) -> tuple[Path, dict[str, Any]]:
    path = _plan_path(root, instance, plan_id)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("PLAN_NOT_FOUND", f"plan not found: {plan_id}")
    if plan.get("plan_id") != plan_id:
        _fail("PLAN_IDENTITY_MISMATCH", "plan identity does not match artifact")
    return path, plan


def _ensure_open(root: Path, plan: dict[str, Any]) -> None:
    if plan.get("state") != "open":
        _fail("PLAN_NOT_OPEN", f"plan is {plan.get('state')}")
    if _head(root) != plan["baseline_commit"]:
        _fail("PLAN_STALE_BASELINE", "committed baseline changed since plan init")


def _decode_writes(plan: dict[str, Any]) -> dict[str, bytes | None]:
    try:
        return {path: (base64.b64decode(value, validate=True) if value is not None else None) for path, value in plan.get("writes", {}).items()}
    except (ValueError, TypeError) as exc:
        _fail("PLAN_ARTIFACT_INVALID", f"invalid planned write encoding: {exc}")


def _content_digest(plan: dict[str, Any]) -> str:
    return canonical_digest({
        "plan_id": plan["plan_id"],
        "baseline_commit": plan["baseline_commit"],
        "operations": plan.get("operations", []),
        "writes": {key: (hashlib.sha256(value).hexdigest() if value is not None else None) for key, value in sorted(_decode_writes(plan).items())},
    })


def _operation(plan_id: str, operation_type: str, canonical_input: dict[str, Any]) -> dict[str, Any]:
    content = {"plan_id": plan_id, "operation_type": operation_type, "input": canonical_input, "core_version": _runtime_version()}
    operation_digest = canonical_digest(content)
    return {**content, "operation_id": f"op_{operation_digest[:26]}", "operation_digest": operation_digest}


def _with_overlay(root: Path, plan: dict[str, Any]):
    temporary = tempfile.TemporaryDirectory()
    staging = Path(temporary.name)
    for child in root.iterdir():
        if child.name in {".git", ".local"}:
            continue
        destination = staging / child.name
        shutil.copytree(child, destination) if child.is_dir() else shutil.copy2(child, destination)
    for rel, value in _decode_writes(plan).items():
        target = staging / rel
        if value is None:
            with contextlib.suppress(FileNotFoundError):
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
    return temporary, staging


def _counters(plan: dict[str, Any]) -> dict[str, int]:
    current = plan.setdefault("counters", {})
    for key in COUNTER_KEYS:
        current.setdefault(key, 0)
    current["operations"] = len(plan.get("operations", []))
    current["changed_files"] = len(plan.get("writes", {}))
    return {key: int(current[key]) for key in COUNTER_KEYS}


def _budget_findings(plan: dict[str, Any], anticipated: dict[str, int] | None = None) -> list[dict[str, Any]]:
    counters = _counters(plan); anticipated = anticipated or {}
    budgets = plan.get("budgets", DEFAULT_BUDGETS)
    checks = {
        "candidate_bundles": "max_candidate_bundles",
        "full_preflight_checks": "max_full_preflight",
        "noop_actions": "max_noop_actions",
        "tool_gap": "max_tool_gap",
    }
    return [
        {"code": "PLAN_BUDGET_EXCEEDED", "path": ".", "message": f"{counter} exceeds {budget}",
         "counter": counter, "actual": counters[counter] + anticipated.get(counter, 0), "limit": budgets[budget]}
        for counter, budget in checks.items()
        if counters[counter] + anticipated.get(counter, 0) > budgets[budget]
    ]


def _assert_budget(plan: dict[str, Any], anticipated: dict[str, int] | None = None) -> None:
    findings = _budget_findings(plan, anticipated)
    if findings:
        raise _core().SemanticPlanError("PLAN_BUDGET_EXCEEDED", "semantic plan budget exceeded", findings)


def init_plan(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    baseline = _head(root)
    identity = {"instance_id": instance.identity["id"], "baseline_commit": baseline, "principal": instance.identities["principal"]["id"],
                "executor": instance.identities["executor"]["id"], "workspace": instance.identities["workspace"]["id"],
                "writer": instance.identities["writer"]["id"], "intent": args.intent.strip(), "risk": args.risk,
                "core_version": _runtime_version()}
    if not identity["intent"]:
        _fail("PLAN_INPUT_INVALID", "intent is required")
    plan_digest = canonical_digest(identity)
    plan_id = f"pln_{plan_digest[:26]}"
    path = _plan_path(root, instance, plan_id)
    if path.exists():
        _, existing = _load(root, instance, plan_id)
        return _summary(existing, "init", artifact_path=_local_base(instance).joinpath(path.name).as_posix())
    plan = {"schema_version": 2, "plan_id": plan_id, "plan_digest": plan_digest, **identity, "state": "open",
            "operations": [], "writes": {}, "claims": {}, "existing_claim_changes": {}, "structure_changes": [],
            "authority_refs": [], "authority_ref_refreshes": [], "authority_ref_retirements": [],
            "affected_topics": [], "affected_nodes": [], "path_operations": {}, "delta": None,
            "finalized_bundle": None, "full_preflight_receipt": None, "post_apply_receipt": None,
            "budgets": dict(DEFAULT_BUDGETS), "counters": {key: 0 for key in COUNTER_KEYS}}
    _save(path, plan)
    return _summary(plan, "init", artifact_path=_local_base(instance).joinpath(path.name).as_posix())


def add_claim(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    canonical_input = {"node": args.node, "node_name": args.node_name, "node_path": args.node_path,
                       "node_boundary": args.node_boundary, "node_keywords": sorted(set(args.node_keywords)),
                       "topic_id": args.topic_id, "topic_path": args.topic_path, "topic_title": args.topic_title,
                       "topic_summary": args.topic_summary, "topic_keywords": sorted(set(args.topic_keywords)),
                       "title": args.title.strip(), "statement": args.statement.strip(), "boundary": args.boundary.strip(),
                       "permission": args.permission, "duplicate_resolution": args.duplicate_resolution,
                       "fact_classes": sorted(set(args.fact_class))}
    operation = _operation(plan["plan_id"], "add_claim", canonical_input)
    claim_id = f"clm_{canonical_digest({'plan_id': plan['plan_id'], 'baseline': plan['baseline_commit'], 'operation_digest': operation['operation_digest']})[:26].upper()}"
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "add-claim", operation_id=operation["operation_id"], claim_id=claim_id, replayed=True)
    temporary, staging = _with_overlay(root, plan)
    try:
        ns = argparse.Namespace(actor=plan["writer"], node=args.node, node_name=args.node_name,
                                node_path=args.node_path, node_boundary=args.node_boundary, node_keywords=args.node_keywords,
                                topic_id=args.topic_id, topic_path=args.topic_path, topic_title=args.topic_title,
                                topic_summary=args.topic_summary, keywords=args.topic_keywords, title=args.title,
                                statement=args.statement, boundary=args.boundary, permission=args.permission,
                                duplicate_resolution=args.duplicate_resolution)
        writes, details = _core().plan_new_claim(staging, ns, claim_id=claim_id, fact_classes=canonical_input["fact_classes"])
    except _core().SemanticPlanError:
        raise
    except _core().KnowledgeError as exc:
        message = str(exc)
        code = "PLAN_DUPLICATE" if "duplicate or highly similar" in message else ("PLAN_PERMISSION_EXPANSION" if "permission must equal" in message else "PLAN_TOPIC_INVALID")
        _fail(code, message)
    finally:
        temporary.cleanup()
    operation["claim_id"] = claim_id
    plan["operations"].append(operation); plan["claims"][claim_id] = {**canonical_input, "claim_id": claim_id}
    plan["writes"].update({rel: (base64.b64encode(value).decode("ascii") if value is not None else None) for rel, value in writes.items()})
    for rel in writes:
        plan.setdefault("path_operations", {}).setdefault(rel, []).append("add_claim")
    plan["delta"] = None
    plan["counters"]["semantic_amplification"] += int(details.get("amplification", {}).get("knowledge_markdown_character_change", 0))
    _counters(plan); _save(path, plan)
    return _summary(plan, "add-claim", operation_id=operation["operation_id"], claim_id=claim_id, replayed=False)


def revise_claim(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    canonical_input = {"claim_id": args.claim_id, "title": args.title, "statement": args.statement.strip(),
                       "boundary": args.boundary.strip(), "semantic_declaration": args.semantic_declaration,
                       "reason": args.reason.strip()}
    if not canonical_input["reason"]:
        _fail("PLAN_INPUT_INVALID", "revision reason is required")
    operation = _operation(plan["plan_id"], "revise_claim", canonical_input)
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "revise-claim", operation_id=operation["operation_id"], claim_id=args.claim_id, replayed=True)
    event_id = f"evt_{operation['operation_digest'][:26].upper()}"
    created_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    temporary, staging = _with_overlay(root, plan)
    try:
        ns = argparse.Namespace(**vars(args), actor=plan["writer"])
        writes, details = _core().plan_revise_claim(staging, ns, event_id=event_id, created_at=created_at)
    finally:
        temporary.cleanup()
    operation["claim_id"] = args.claim_id
    plan["operations"].append(operation); plan["existing_claim_changes"][args.claim_id] = {**canonical_input, **details}
    plan["writes"].update({rel: (base64.b64encode(value).decode("ascii") if value is not None else None) for rel, value in writes.items()})
    for rel in writes:
        plan.setdefault("path_operations", {}).setdefault(rel, []).append("revise_claim")
    plan["affected_topics"] = sorted(set(plan["affected_topics"] + [details["topic_id"]]))
    plan["affected_nodes"] = sorted(set(plan["affected_nodes"] + [details["node_id"]]))
    plan["delta"] = None; _counters(plan); _save(path, plan)
    return _summary(plan, "revise-claim", operation_id=operation["operation_id"], claim_id=args.claim_id,
                    before_hash=details["before_hash"], after_hash=details["after_hash"], replayed=False)


def move_topic(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    canonical_input = {"topic_id": args.topic_id, "to_node": args.to_node, "to_path": args.to_path,
                       "node_name": args.node_name, "node_path": args.node_path, "node_boundary": args.node_boundary,
                       "node_keywords": sorted(set(args.node_keywords)), "reason": args.reason.strip()}
    if not canonical_input["reason"]:
        _fail("PLAN_INPUT_INVALID", "move reason is required")
    operation = _operation(plan["plan_id"], "move_topic", canonical_input)
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "move-topic", operation_id=operation["operation_id"], topic_id=args.topic_id, replayed=True)
    event_id = f"evt_{operation['operation_digest'][:26].upper()}"
    created_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    temporary, staging = _with_overlay(root, plan)
    try:
        ns = argparse.Namespace(**vars(args), actor=plan["writer"])
        writes, details = _core().plan_move_topic(staging, ns, event_id=event_id, created_at=created_at)
    finally:
        temporary.cleanup()
    operation["topic_id"] = args.topic_id; operation["claim_ids"] = details["claim_ids"]
    plan["operations"].append(operation); plan["structure_changes"].append(details)
    plan["writes"].update({rel: (base64.b64encode(value).decode("ascii") if value is not None else None) for rel, value in writes.items()})
    for rel in writes:
        plan.setdefault("path_operations", {}).setdefault(rel, []).append("move_topic")
    plan["affected_topics"] = sorted(set(plan["affected_topics"] + [args.topic_id]))
    plan["affected_nodes"] = sorted(set(plan["affected_nodes"] + [details["from_node"], details["to_node"]]))
    plan["delta"] = None; _counters(plan); _save(path, plan)
    return _summary(plan, "move-topic", operation_id=operation["operation_id"], topic_id=args.topic_id,
                    moved_claim_ids=details["claim_ids"], node_created=details["node_created"], warning=details["warning"], replayed=False)


def add_authority_ref(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    claim = plan["claims"].get(args.claim_id)
    if not claim:
        _fail("PLAN_CLAIM_MISSING", f"planned claim not found: {args.claim_id}")
    pure = PurePosixPath(args.path)
    if not args.path or pure.is_absolute() or ".." in pure.parts or "\\" in args.path or args.path.startswith(".local/"):
        _fail("PLAN_AUTHORITY_PATH_INVALID", "authority path must be portable, project-relative, and non-local", path=args.path)
    committed = _committed_bytes(root, plan["baseline_commit"], args.path)
    if committed is None:
        _fail("PLAN_AUTHORITY_NOT_COMMITTED", "authority path does not exist in committed baseline", path=args.path)
    working = root / args.path
    if not working.is_file() or working.read_bytes() != committed:
        _fail("PLAN_AUTHORITY_WORKTREE_DIRTY", "authority path has uncommitted content; restore the committed baseline or commit it and start a new plan", path=args.path)
    facts = sorted(set(args.fact_class))
    if not facts or any(value not in FACT_CLASSES for value in facts):
        _fail("PLAN_FACT_CLASS_REQUIRED", "Authority Ref requires valid fact classes", path=args.path)
    if not set(facts).issubset(set(claim["fact_classes"])):
        _fail("PLAN_FACT_COVERAGE", "Authority Ref fact classes must be declared by the Claim", path=args.path)
    if PERMISSION_RANK[claim["permission"]] > PERMISSION_RANK["internal"]:
        _fail("PLAN_PERMISSION_EXPANSION", "semantic plan cannot expand Claim permission beyond internal", path=args.path)
    approved_hash = hashlib.sha256(committed).hexdigest()
    canonical_input = {"claim_id": args.claim_id, "path": args.path, "locator": args.locator, "role": args.role,
                       "change_policy": args.change_policy, "fact_classes": facts, "approved_hash": approved_hash}
    operation = _operation(plan["plan_id"], "add_authority_ref", canonical_input)
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "add-authority-ref", operation_id=operation["operation_id"], approved_hash=approved_hash,
                        diagnostic_hash_match=args.diagnostic_hash in {None, approved_hash}, replayed=True)
    ref = {"id": f"aref_{operation['operation_digest'][:26]}", "path": args.path, "locator": args.locator, "role": args.role,
           "baseline_state": "committed_baseline", "change_policy": args.change_policy, "approved_hash": approved_hash,
           "claim_ids": [args.claim_id], "supports_fact_classes": facts}
    validation = validate_authority_ref(ref)
    if not validation["ok"]:
        raise _core().SemanticPlanError("PLAN_AUTHORITY_REF_INVALID", "invalid Authority Ref", validation["errors"])
    refs_rel = instance.authority.get("authority_refs")
    if not refs_rel:
        _fail("PLAN_AUTHORITY_REFS_UNCONFIGURED", "instance has no authority_refs path")
    current = _decode_writes(plan).get(refs_rel)
    if current is None:
        current = _committed_bytes(root, plan["baseline_commit"], refs_rel)
        if current is None:
            _fail("PLAN_AUTHORITY_REFS_UNCOMMITTED", "authority_refs registry is not committed", path=refs_rel)
    try:
        data = canonical_authority_document(json.loads(current.decode("utf-8")))
    except ValueError as exc:
        _fail("PLAN_AUTHORITY_REFS_SCHEMA", str(exc), path=refs_rel)
    data["refs"].append(ref); data["refs"] = sorted(data["refs"], key=lambda item: item["id"])
    plan["writes"][refs_rel] = base64.b64encode((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()).decode("ascii")
    plan.setdefault("path_operations", {}).setdefault(refs_rel, []).append("add_authority_ref")
    plan["authority_refs"].append(ref); plan["operations"].append(operation); plan["delta"] = None
    _counters(plan); _save(path, plan)
    return _summary(plan, "add-authority-ref", operation_id=operation["operation_id"], authority_ref_id=ref["id"],
                    approved_hash=approved_hash, diagnostic_hash_match=args.diagnostic_hash in {None, approved_hash}, replayed=False)


def _authority_registry_overlay(root: Path, instance: Instance, plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    refs_rel = instance.authority.get("authority_refs")
    if not refs_rel:
        _fail("PLAN_AUTHORITY_REFS_UNCONFIGURED", "instance has no authority_refs path")
    current = _decode_writes(plan).get(refs_rel)
    if current is None:
        current = _committed_bytes(root, plan["baseline_commit"], refs_rel)
        if current is None:
            _fail("PLAN_AUTHORITY_REFS_UNCOMMITTED", "authority_refs registry is not committed", path=refs_rel)
    try:
        return refs_rel, canonical_authority_document(json.loads(current.decode("utf-8")))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("PLAN_AUTHORITY_REFS_SCHEMA", str(exc), path=refs_rel)


def _store_authority_registry(plan: dict[str, Any], refs_rel: str, data: dict[str, Any], operation: str) -> None:
    data["refs"] = sorted(data["refs"], key=lambda item: item["id"])
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    plan["writes"][refs_rel] = base64.b64encode(encoded).decode("ascii")
    plan.setdefault("path_operations", {}).setdefault(refs_rel, []).append(operation)


def _append_authority_event(root: Path, plan: dict[str, Any], event: dict[str, Any], operation: str) -> str:
    rel = _core().shard_rel("proposals", plan["writer"], event["created_at"])
    current = _decode_writes(plan).get(rel)
    if current is None:
        current = (root / rel).read_bytes() if (root / rel).is_file() else b""
    line = _canonical(event)
    plan["writes"][rel] = base64.b64encode(current + line).decode("ascii")
    plan.setdefault("path_operations", {}).setdefault(rel, []).append(operation)
    return rel


def refresh_authority_ref(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    reason = args.reason.strip()
    if not reason:
        _fail("PLAN_INPUT_INVALID", "Authority Ref refresh reason is required")
    replay = next((item for item in plan["operations"] if item["operation_type"] == "refresh_authority_ref"
                   and item["input"]["authority_ref_id"] == args.authority_ref_id
                   and item["input"]["reason"] == reason), None)
    if replay:
        details = next(item for item in plan.get("authority_ref_refreshes", []) if item["authority_ref_id"] == args.authority_ref_id)
        return _summary(plan, "refresh-authority-ref", operation_id=replay["operation_id"],
                        authority_ref_id=args.authority_ref_id, old_approved_hash=details["old_hash"],
                        new_approved_hash=details["new_hash"], affected_claim_ids=details["affected_claim_ids"], replayed=True)
    refs_rel, data = _authority_registry_overlay(root, instance, plan)
    matches = [item for item in data["refs"] if item.get("id") == args.authority_ref_id]
    if len(matches) != 1:
        _fail("PLAN_AUTHORITY_REF_MISSING", f"Authority Ref not found or not unique: {args.authority_ref_id}", path=refs_rel)
    old = matches[0]
    committed = _committed_bytes(root, plan["baseline_commit"], old["path"])
    if committed is None:
        _fail("PLAN_AUTHORITY_NOT_COMMITTED", "Authority path does not exist in plan committed baseline", path=old["path"])
    working = root / old["path"]
    if not working.is_file() or working.read_bytes() != committed:
        _fail("PLAN_AUTHORITY_WORKTREE_DIRTY", "Authority path differs from plan committed baseline", path=old["path"])
    old_hash = old.get("approved_hash") or old.get("fragment_hash")
    new_hash = hashlib.sha256(committed).hexdigest()
    if old_hash == new_hash:
        _fail("PLAN_STRUCTURE_NOOP", "Authority Ref already approves the committed baseline", path=old["path"])
    canonical_input = {"authority_ref_id": args.authority_ref_id, "old_approved_hash": old_hash,
                       "new_approved_hash": new_hash, "reason": reason}
    operation = _operation(plan["plan_id"], "refresh_authority_ref", canonical_input)
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "refresh-authority-ref", operation_id=operation["operation_id"],
                        authority_ref_id=args.authority_ref_id, old_approved_hash=old_hash,
                        new_approved_hash=new_hash, affected_claim_ids=old.get("claim_ids", []), replayed=True)
    refreshed = dict(old); refreshed["approved_hash"] = new_hash; refreshed.pop("fragment_hash", None)
    data["refs"][data["refs"].index(old)] = refreshed
    created_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    event = {**_core().event_identity(root, argparse.Namespace(actor=plan["writer"])),
             "event_id": f"evt_{operation['operation_digest'][:26].upper()}", "event_type": "authority_ref_refreshed",
             "authority_ref_id": args.authority_ref_id, "old_approved_hash": old_hash, "new_approved_hash": new_hash,
             "affected_claim_ids": old.get("claim_ids", []), "reason": reason, "created_at": created_at}
    _store_authority_registry(plan, refs_rel, data, "refresh_authority_ref")
    event_path = _append_authority_event(root, plan, event, "refresh_authority_ref")
    details = {"authority_ref_id": args.authority_ref_id, "old_hash": old_hash, "new_hash": new_hash,
               "affected_claim_ids": old.get("claim_ids", []), "path": old["path"], "reason": reason,
               "event_id": event["event_id"], "event_path": event_path}
    operation["authority_ref_id"] = args.authority_ref_id
    plan["operations"].append(operation); plan.setdefault("authority_ref_refreshes", []).append(details)
    plan["delta"] = None; _counters(plan); _save(path, plan)
    return _summary(plan, "refresh-authority-ref", operation_id=operation["operation_id"], authority_ref_id=args.authority_ref_id,
                    old_approved_hash=old_hash, new_approved_hash=new_hash,
                    affected_claim_ids=old.get("claim_ids", []), replayed=False)


def retire_authority_ref(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan)
    reason = args.reason.strip()
    if not reason:
        _fail("PLAN_INPUT_INVALID", "Authority Ref retirement reason is required")
    replacement_ref, replacement_claim = args.replacement_authority_ref_id, args.replacement_claim_id
    if not replacement_ref and not replacement_claim:
        _fail("PLAN_AUTHORITY_REPLACEMENT_REQUIRED", "retirement requires a replacement Authority Ref or Claim")
    replay = next((item for item in plan["operations"] if item["operation_type"] == "retire_authority_ref"
                   and item["input"] == {"authority_ref_id": args.authority_ref_id,
                                         "replacement_authority_ref_id": replacement_ref,
                                         "replacement_claim_id": replacement_claim, "reason": reason}), None)
    if replay:
        details = next(item for item in plan.get("authority_ref_retirements", []) if item["authority_ref_id"] == args.authority_ref_id)
        return _summary(plan, "retire-authority-ref", operation_id=replay["operation_id"],
                        authority_ref_id=args.authority_ref_id, affected_claim_ids=details["affected_claim_ids"], replayed=True)
    refs_rel, data = _authority_registry_overlay(root, instance, plan)
    matches = [item for item in data["refs"] if item.get("id") == args.authority_ref_id]
    if len(matches) != 1:
        _fail("PLAN_AUTHORITY_REF_MISSING", f"Authority Ref not found or not unique: {args.authority_ref_id}", path=refs_rel)
    retired = matches[0]
    if replacement_ref:
        replacement = next((item for item in data["refs"] if item.get("id") == replacement_ref), None)
        if not replacement or replacement_ref == args.authority_ref_id:
            _fail("PLAN_AUTHORITY_REPLACEMENT_INVALID", "replacement Authority Ref must exist and differ from the retired Ref", path=refs_rel)
    if replacement_claim:
        temporary, staging = _with_overlay(root, plan)
        try:
            registry, _ = _core().load_authority(staging)
            claim_ids = {item["id"] for item in _core().parse_claims(staging, registry)[0]}
        finally:
            temporary.cleanup()
        if replacement_claim not in claim_ids:
            _fail("PLAN_AUTHORITY_REPLACEMENT_INVALID", "replacement Claim does not exist", path=replacement_claim)
    canonical_input = {"authority_ref_id": args.authority_ref_id, "replacement_authority_ref_id": replacement_ref,
                       "replacement_claim_id": replacement_claim, "reason": reason}
    operation = _operation(plan["plan_id"], "retire_authority_ref", canonical_input)
    if any(item["operation_id"] == operation["operation_id"] for item in plan["operations"]):
        return _summary(plan, "retire-authority-ref", operation_id=operation["operation_id"],
                        authority_ref_id=args.authority_ref_id, affected_claim_ids=retired.get("claim_ids", []), replayed=True)
    data["refs"].remove(retired)
    created_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    event = {**_core().event_identity(root, argparse.Namespace(actor=plan["writer"])),
             "event_id": f"evt_{operation['operation_digest'][:26].upper()}", "event_type": "authority_ref_retired",
             "authority_ref_id": args.authority_ref_id, "retired_ref": retired,
             "affected_claim_ids": retired.get("claim_ids", []), "replacement_authority_ref_id": replacement_ref,
             "replacement_claim_id": replacement_claim, "reason": reason, "created_at": created_at}
    _store_authority_registry(plan, refs_rel, data, "retire_authority_ref")
    event_path = _append_authority_event(root, plan, event, "retire_authority_ref")
    details = {"authority_ref_id": args.authority_ref_id, "affected_claim_ids": retired.get("claim_ids", []),
               "path": retired["path"], "old_hash": retired.get("approved_hash") or retired.get("fragment_hash"),
               "replacement_authority_ref_id": replacement_ref, "replacement_claim_id": replacement_claim,
               "reason": reason, "event_id": event["event_id"], "event_path": event_path}
    operation["authority_ref_id"] = args.authority_ref_id
    plan["operations"].append(operation); plan.setdefault("authority_ref_retirements", []).append(details)
    plan["delta"] = None; _counters(plan); _save(path, plan)
    return _summary(plan, "retire-authority-ref", operation_id=operation["operation_id"], authority_ref_id=args.authority_ref_id,
                    affected_claim_ids=retired.get("claim_ids", []), replayed=False)


def _evaluation_contract(root: Path, instance: Instance) -> dict[str, Any]:
    try:
        return load_evaluation_contract(root, instance, required=False)
    except EvaluationContractError as exc:
        details = {"field": exc.field, "case_id": exc.case_id, "evaluator_contract_version": 1,
                   "runtime_version": _runtime_version()}
        _fail("PLAN_EVALUATION_SCHEMA", str(exc), path=exc.path, **{key: value for key, value in details.items() if value is not None})


def _evaluation_cases(root: Path, instance: Instance) -> list[dict[str, Any]]:
    return _evaluation_contract(root, instance)["cases"]


def _affected_cases(root: Path, instance: Instance, plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    contract = _evaluation_contract(root, instance)
    touched_topics = {claim["topic_id"] for claim in plan.get("claims", {}).values()} | set(plan.get("affected_topics", []))
    touched_nodes = set(plan.get("affected_nodes", []))
    touched_claims = set(plan.get("existing_claim_changes", []))
    selected, decisions = select_delta_cases(contract, node_ids=touched_nodes, topic_ids=touched_topics, claim_ids=touched_claims)
    return contract, selected, decisions


def _run_cases(staging: Path, instance: Instance, contract: dict[str, Any], cases: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    core = _core()
    evaluation = evaluate_normalized_cases(
        contract, cases,
        lambda query, terms, permission, limit, semantic: core.knowledge_search_command(
            staging, instance, query, terms, permission, limit, semantic),
        semantic=False, phase=phase)
    return evaluation["rows"]


def _validation_records(staging: Path, instance: Instance, contract: dict[str, Any], cases: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    core = _core()
    validation = core.validate(staging)
    projection = core.rebuild(staging)
    tree = core.tree_command(staging) if validation["ok"] and projection["ok"] else {"ok": False, "errors": []}
    case_records = _run_cases(staging, instance, contract, cases, phase) if validation["ok"] and projection["ok"] else []
    refs = []
    refs_path = instance.authority.get("authority_refs")
    if refs_path and (staging / refs_path).is_file():
        from .authority import observe_authority_refs
        refs = observe_authority_refs(staging, authority_refs_from_document(json.loads((staging / refs_path).read_text(encoding="utf-8"))))
    failed = [item["case_id"] for item in case_records if not item["ok"]]
    ok = validation["ok"] and projection["ok"] and tree.get("ok", False) and not failed and all(item.get("effective_status", item.get("status")) in {"current", "fresh"} for item in refs)
    return {"ok": ok, "validation": validation, "projection": projection, "tree": tree,
            "evaluation_records": case_records, "failed_case_ids": failed, "authority_records": refs}


def check_delta(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    if args.mode != "delta":
        _fail("PLAN_CHECK_MODE_INVALID", f"unsupported knowledge-plan check mode: {args.mode}")
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, plan); _assert_budget(plan)
    temporary, staging = _with_overlay(root, plan)
    try:
        registry, _ = _core().load_authority(staging)
        claims, parse_findings = _core().parse_claims(staging, registry)
        changed_ids = set(plan["claims"]) | set(plan.get("existing_claim_changes", {}))
        planned_claims = [claim for claim in claims if claim["id"] in changed_ids]
        findings = [{"code": item.code, "path": item.path, "message": item.message} for item in parse_findings]
        refs_rel = instance.authority.get("authority_refs")
        all_refs = authority_refs_from_document(json.loads((staging / refs_rel).read_text(encoding="utf-8"))) if refs_rel else []
        findings.extend({**item, "path": refs_rel or "authority_ref", "message": "missing changed Claim Authority fact coverage"}
                        for item in validate_authority_coverage(planned_claims, all_refs))
        for claim_id, change in plan.get("existing_claim_changes", {}).items():
            if change["semantic_declaration"] in {"correct", "expand"} and not any(claim_id in ref.get("claim_ids", []) for ref in all_refs):
                findings.append({"code": "PLAN_CLAIM_AUTHORITY_INSUFFICIENT", "path": refs_rel or "authority_ref", "message": f"{claim_id} correction/expansion lacks Authority coverage"})
        for ref in plan["authority_refs"]:
            if ref["path"] in plan.get("writes", {}):
                findings.append({"code": "PLAN_AUTHORITY_STAGED_DRIFT", "path": ref["path"],
                                 "message": "Authority Reference path is also modified by the current plan; committed-baseline hashes cannot authorize staged self-reference",
                                 "authority_ref_id": ref["id"], "claim_ids": ref.get("claim_ids", []),
                                 "staged_by_current_plan": True})
                continue
            committed = _committed_bytes(root, plan["baseline_commit"], ref["path"])
            if committed is None or hashlib.sha256(committed).hexdigest() != ref["approved_hash"]:
                findings.append({"code": "PLAN_AUTHORITY_STALE", "path": ref["path"],
                                 "message": "committed Authority hash changed since plan baseline; commit the intended Authority change, then start a new plan"})
            elif not (root / ref["path"]).is_file() or (root / ref["path"]).read_bytes() != committed:
                findings.append({"code": "PLAN_AUTHORITY_WORKTREE_DIRTY", "path": ref["path"],
                                 "message": "Authority has uncommitted content; restore the committed baseline or commit it and start a new plan"})
        contract, affected, selection = _affected_cases(staging, instance, plan)
        if not findings:
            projection = _core().rebuild(staging)
            if not projection["ok"]:
                findings.extend(projection.get("errors", []))
        records = _run_cases(staging, instance, contract, affected, "delta") if not findings else []
        failed_case_ids = [item["case_id"] for item in records if not item["ok"]]
        findings.extend({"code": "PLAN_EVALUATION_FAILED", "path": "evaluation", "message": f"affected evaluation failed: {case_id}", "case_id": case_id}
                        for case_id in failed_case_ids)
        digest = _content_digest(plan)
        artifact = _artifact_rel(instance, digest, "delta")
        full = {"schema_version": 1, "evaluator_contract_version": contract["contract_version"], "mode": "delta",
                "plan_id": plan["plan_id"], "plan_digest": digest,
                "affected_case_ids": [item["id"] for item in affected],
                "deferred_case_ids": [item["case_id"] for item in selection if item["decision"] == "deferred"],
                "case_selection": selection, "records": records, "findings": findings}
        _write_artifact(root, artifact, full)
        plan["counters"]["delta_checks"] += 1
        delta = {"ok": not findings, "mode": "delta", "delta_digest": digest, "touched_operations": len(plan["operations"]),
                 "touched_files": sorted(plan["writes"]), "affected_case_ids": full["affected_case_ids"],
                 "failed_case_ids": failed_case_ids, "findings": findings, "can_finalize": not findings, "artifact_path": artifact}
        plan["delta"] = delta; _counters(plan); _save(path, plan)
        return _compact(plan, "knowledge-plan check", delta, summary={"can_finalize": not findings, "touched_operations": len(plan["operations"]), "touched_files": len(plan["writes"])})
    finally:
        temporary.cleanup()


def _action_operation(plan: dict[str, Any], rel: str) -> str:
    operations = plan.get("path_operations", {}).get(rel, [])
    if not operations:
        _fail("PLAN_PROVENANCE_MISMATCH", f"no semantic operation owns changed path: {rel}", path=rel)
    # The last operation produced the exact after-image; its provenance owns it.
    return f"semantic_overlay:{operations[-1]}"


def _assert_finalized_environment(root: Path, plan: dict[str, Any], *, allow_applied: bool = False) -> None:
    if _head(root) != plan["baseline_commit"]:
        _fail("PLAN_STALE_BASELINE", "committed baseline changed after finalize")
    checked_refs = list(plan.get("authority_refs", [])) + [
        {"path": item["path"], "approved_hash": item["new_hash"]} for item in plan.get("authority_ref_refreshes", [])
    ]
    for ref in checked_refs:
        committed = _committed_bytes(root, plan["baseline_commit"], ref["path"])
        if committed is None or hashlib.sha256(committed).hexdigest() != ref["approved_hash"]:
            _fail("PLAN_AUTHORITY_STALE", "committed Authority hash changed since plan baseline; commit the intended Authority change, then start a new plan", path=ref["path"])
        if not (root / ref["path"]).is_file() or (root / ref["path"]).read_bytes() != committed:
            _fail("PLAN_AUTHORITY_WORKTREE_DIRTY", "Authority has uncommitted content; restore the committed baseline or commit it and start a new plan", path=ref["path"])
    if not allow_applied:
        for action in (plan.get("finalized_bundle") or {}).get("actions", []):
            target = root / action["path"]
            actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if actual != action["expected_hash"]:
                _fail("PLAN_WORKTREE_DRIFT", "planned authority changed after finalize", path=action["path"])


def finalize(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id)
    if plan.get("finalized_bundle"):
        verify_finalized_bundle_provenance(root, instance, plan["finalized_bundle"])
        bundle = plan["finalized_bundle"]
        return _compact(plan, "knowledge-plan finalize", {"bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"],
                        "changed_files": bundle["expected_changed_files"], "artifact_path": plan["full_preflight_receipt"]["artifact_path"]},
                        summary={"finalized": True, "replayed": True, "approved": False, "applied": False})
    _ensure_open(root, plan)
    delta = plan.get("delta")
    content_digest = _content_digest(plan)
    if not delta or not delta.get("ok") or delta.get("delta_digest") != content_digest:
        _fail("PLAN_DELTA_REQUIRED", "successful delta check for the current plan digest is required before finalize")
    # Refuse before another candidate or full gate is produced.
    _assert_budget(plan, {"candidate_bundles": 1, "full_preflight_checks": 1})
    actions = []
    for rel, after in sorted(_decode_writes(plan).items()):
        target = root / rel
        existed = target.exists(); before = target.read_bytes() if existed else b""
        if (after is not None and before == after) or (after is None and not existed):
            plan["counters"]["noop_actions"] += 1
            _save(path, plan); _assert_budget(plan)
        new_hash = hashlib.sha256(after).hexdigest() if after is not None else None; operation_type = _action_operation(plan, rel)
        descriptor = {"plan_id": plan["plan_id"], "operation_type": operation_type, "core_version": _runtime_version(), "path": rel, "new_hash": new_hash}
        operation_digest = canonical_digest(descriptor)
        provenance = {"plan_id": plan["plan_id"], "operation_id": f"op_{operation_digest[:26]}", "operation_type": operation_type,
                      "operation_digest": operation_digest, "core_version": _runtime_version()}
        actions.append({"operation": "replace" if after is not None else "delete", "path": rel,
                        "content": after.decode("utf-8") if after is not None else None, "provenance": provenance})
    operation_types = {item["operation_type"] for item in plan["operations"]}
    if "move_topic" in operation_types and "revise_claim" in operation_types:
        bundle_type = "knowledge_refactor"
    elif "move_topic" in operation_types:
        bundle_type = "knowledge_structure_change"
    elif "revise_claim" in operation_types:
        bundle_type = "claim_revise"
    elif operation_types.intersection({"refresh_authority_ref", "retire_authority_ref"}) and not operation_types.intersection({"add_claim", "add_authority_ref"}):
        bundle_type = "authority_maintenance"
    else:
        bundle_type = "claim_create"
    manifest = {"bundle_type": bundle_type, "intent": plan["intent"],
                "semantic_diff": {"plan_digest": content_digest, "operations": len(plan["operations"]), "claims_created": sorted(plan["claims"]),
                                  "claims_revised": sorted(plan.get("existing_claim_changes", {})),
                                  "structure_changes": plan.get("structure_changes", []),
                                  "affected_topics": plan.get("affected_topics", []), "affected_nodes": plan.get("affected_nodes", []),
                                  "authority_refs_added": [item["id"] for item in plan["authority_refs"]],
                                  "authority_refs_refreshed": [{key: item[key] for key in ("authority_ref_id", "old_hash", "new_hash", "affected_claim_ids")} for item in plan.get("authority_ref_refreshes", [])],
                                  "authority_refs_retired": [{key: item.get(key) for key in ("authority_ref_id", "affected_claim_ids", "replacement_authority_ref_id", "replacement_claim_id", "reason")} for item in plan.get("authority_ref_retirements", [])]},
                "evidence_refs": [], "authority_refs": sorted(set([item["id"] for item in plan["authority_refs"]]
                    + [item["authority_ref_id"] for item in plan.get("authority_ref_refreshes", [])]
                    + [item["authority_ref_id"] for item in plan.get("authority_ref_retirements", [])])), "permission_effect": "none",
                "risk": plan["risk"], "actions": actions}
    bundle = build_bundle(root, manifest, instance.identities)
    bundle = _core().preflight_bundle(root, bundle)
    temporary, staging = _with_overlay(root, plan)
    try:
        contract = _evaluation_contract(staging, instance)
        records = _validation_records(staging, instance, contract, contract["cases"], "full_preflight")
        records["case_selection"] = [{"case_id": case["id"], "decision": "selected", "reason": "full_preflight_all_cases"}
                                     for case in contract["cases"]]
    finally:
        temporary.cleanup()
    if not records["ok"]:
        failed_artifact = _artifact_rel(instance, content_digest, "full-preflight-failed")
        _write_artifact(root, failed_artifact, {
            "schema_version": 1, "evaluator_contract_version": contract["contract_version"],
            "plan_id": plan["plan_id"], "plan_digest": content_digest, "ok": False,
            "records": records, "runtime_version": _runtime_version(), "cost_counters": _counters(plan),
        })
        findings = records["validation"].get("errors", []) + records["projection"].get("errors", [])
        findings += [{"code": "PLAN_FULL_EVALUATION_FAILED", "path": "evaluation", "message": case_id,
                      "case_id": case_id, "artifact_path": failed_artifact,
                      "evaluator_contract_version": contract["contract_version"], "runtime_version": _runtime_version()}
                     for case_id in records["failed_case_ids"]]
        changed_paths = set(plan.get("writes", {}))
        for ref in records["authority_records"]:
            status = ref.get("effective_status", ref.get("status"))
            if status in {"current", "fresh"}:
                continue
            findings.append({"code": "PLAN_AUTHORITY_STAGED_DRIFT" if ref.get("path") in changed_paths else "PLAN_FULL_AUTHORITY_NOT_CURRENT",
                             "path": ref.get("path", "authority_ref"),
                             "message": f"Authority Reference {ref.get('id', 'unknown')} is not current during full staged preflight: {status}",
                             "authority_ref_id": ref.get("id"), "claim_ids": ref.get("claim_ids", []),
                             "baseline_status": ref.get("baseline_status"), "working_tree_status": ref.get("working_tree_status"),
                             "effective_status": status, "expected_hash": ref.get("expected_hash", ref.get("approved_hash")),
                             "observed_hash": ref.get("observed_hash"), "staged_by_current_plan": ref.get("path") in changed_paths})
        if not findings:
            findings.append({"code": "PLAN_FULL_PREFLIGHT_FAILED", "path": "full_preflight",
                             "message": "full staged preflight failed without component findings"})
        raise _core().SemanticPlanError("PLAN_FULL_PREFLIGHT_FAILED", "full staged preflight failed", findings)
    plan["counters"]["full_checks"] += 1; plan["counters"]["full_preflight_checks"] += 1
    plan["counters"]["candidate_bundles"] += 1; _counters(plan); _assert_budget(plan)
    artifact = _artifact_rel(instance, content_digest, "full-preflight")
    _write_artifact(root, artifact, {"schema_version": 1, "plan_id": plan["plan_id"], "plan_digest": content_digest,
                                     "bundle": bundle, "records": records, "cost_counters": _counters(plan)})
    bundle_path, _, _ = _core().bundle_paths(root, bundle["bundle_id"])
    bundle_path.parent.mkdir(parents=True, exist_ok=True); bundle_path.write_bytes(bundle_bytes(bundle))
    plan["state"] = "finalized"; plan["finalized_bundle"] = bundle; plan["finalized_plan_digest"] = content_digest
    plan["full_preflight_receipt"] = {"ok": True, "plan_digest": content_digest, "bundle_id": bundle["bundle_id"],
                                          "content_hash": bundle["content_hash"], "artifact_path": artifact}
    _save(path, plan)
    return _compact(plan, "knowledge-plan finalize", {"bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"],
                    "changed_files": bundle["expected_changed_files"], "artifact_path": artifact},
                    summary={"finalized": True, "replayed": False, "approved": False, "applied": False})


def verify_finalized_bundle_provenance(root: Path, instance: Instance, bundle: dict[str, Any], *, allow_applied: bool = False) -> dict[str, Any]:
    actions = bundle.get("actions", [])
    provenance = [action.get("provenance") for action in actions]
    if not provenance or any(not isinstance(item, dict) for item in provenance):
        _fail("BUNDLE_PROVENANCE_REQUIRED", "production Bundle actions require semantic-plan provenance")
    plan_ids = {item.get("plan_id") for item in provenance}
    if len(plan_ids) != 1:
        _fail("BUNDLE_PROVENANCE_MISMATCH", "Bundle actions must originate from one semantic plan")
    _, plan = _load(root, instance, next(iter(plan_ids)))
    finalized = plan.get("finalized_bundle")
    if plan.get("state") != "finalized" or not finalized or finalized.get("content_hash") != bundle.get("content_hash"):
        _fail("BUNDLE_PROVENANCE_MISMATCH", "Bundle identity is not bound to the finalized semantic plan")
    if plan.get("finalized_plan_digest") != _content_digest(plan):
        _fail("PLAN_PROVENANCE_MISMATCH", "finalized plan operations or writes were modified")
    receipt = plan.get("full_preflight_receipt")
    if not receipt or receipt.get("plan_digest") != plan["finalized_plan_digest"] or not (root / receipt.get("artifact_path", "")).is_file():
        _fail("PLAN_FINALIZED_ARTIFACT_MISSING", "finalized full-preflight artifact is missing or mismatched")
    bundle_path, _, _ = _core().bundle_paths(root, bundle["bundle_id"])
    if not bundle_path.is_file() or json.loads(bundle_path.read_text(encoding="utf-8")) != bundle:
        _fail("BUNDLE_PROVENANCE_MISMATCH", "immutable Bundle artifact is missing or differs from finalized plan")
    expected = {action["path"]: action.get("provenance") for action in finalized.get("actions", [])}
    if any(expected.get(action["path"]) != action.get("provenance") for action in actions):
        _fail("BUNDLE_PROVENANCE_MISMATCH", "Bundle action provenance differs from finalized plan content")
    _assert_finalized_environment(root, plan, allow_applied=allow_applied)
    return plan


def record_post_apply_full_check(root: Path, instance: Instance, bundle: dict[str, Any]) -> dict[str, Any]:
    path, plan = _load(root, instance, bundle["actions"][0]["provenance"]["plan_id"])
    if plan.get("post_apply_receipt"):
        return plan["post_apply_receipt"]
    contract = _evaluation_contract(root, instance)
    records = _validation_records(root, instance, contract, contract["cases"], "post_apply")
    if not records["ok"]:
        _fail("PLAN_POST_APPLY_FULL_FAILED", "post-apply full validation failed")
    plan["counters"]["full_checks"] += 1; plan["counters"]["post_apply_full_checks"] += 1
    artifact = _artifact_rel(instance, plan["finalized_plan_digest"], "post-apply-full")
    receipt = {"ok": True, "plan_digest": plan["finalized_plan_digest"], "bundle_id": bundle["bundle_id"], "artifact_path": artifact}
    _write_artifact(root, artifact, {"schema_version": 1, **receipt, "records": records, "cost_counters": _counters(plan)})
    plan["post_apply_receipt"] = receipt; _save(path, plan)
    return receipt


def _affected_authority_refs(root: Path, instance: Instance, plan: dict[str, Any], required_paths: set[str] | None = None) -> list[dict[str, Any]]:
    report = []
    for ref in plan.get("authority_refs", []):
        report.append({"authority_ref_id": ref["id"], "change": "added", "path": ref["path"],
                       "old_hash": None, "new_hash": ref.get("approved_hash") or ref.get("fragment_hash"),
                       "linked_claim_ids": ref.get("claim_ids", []),
                       "human_review_reason": "A new Authority Reference requires exact-hash human review."})
    for item in plan.get("authority_ref_refreshes", []):
        report.append({"authority_ref_id": item["authority_ref_id"], "change": "refreshed", "path": item["path"],
                       "old_hash": item["old_hash"], "new_hash": item["new_hash"],
                       "linked_claim_ids": item.get("affected_claim_ids", []),
                       "human_review_reason": item.get("reason", "The committed Authority changed and requires exact-hash human review.")})
    for item in plan.get("authority_ref_retirements", []):
        report.append({"authority_ref_id": item["authority_ref_id"], "change": "retired", "path": item.get("path"),
                       "old_hash": item.get("old_hash"), "new_hash": None,
                       "linked_claim_ids": item.get("affected_claim_ids", []),
                       "human_review_reason": item["reason"]})

    refs_rel = instance.authority.get("authority_refs")
    committed = _committed_bytes(root, plan["baseline_commit"], refs_rel) if refs_rel else None
    if committed:
        try:
            existing = authority_refs_from_document(json.loads(committed.decode("utf-8")))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            existing = []
        reported = {item["authority_ref_id"] for item in report}
        writes = _decode_writes(plan)
        required_paths = required_paths or set()
        for ref in existing:
            if ref.get("id") in reported or ref.get("path") not in set(writes) | required_paths:
                continue
            after = writes.get(ref["path"])
            count_dependency = ref["path"] in required_paths and ref["path"] not in writes
            report.append({"authority_ref_id": ref["id"], "change": "memory_sync_required" if count_dependency else "source_path_staged", "path": ref["path"],
                           "old_hash": ref.get("approved_hash") or ref.get("fragment_hash"),
                           "new_hash": None if count_dependency else hashlib.sha256(after).hexdigest() if after is not None else None,
                           "linked_claim_ids": ref.get("claim_ids", []),
                           "human_review_reason": "Claim-count Memory must be synchronized and committed before this reference can be refreshed." if count_dependency else
                                                  "The staged Authority change requires a committed baseline before this reference can be refreshed or retired."})
    return sorted(report, key=lambda item: (item["path"] or "", item["authority_ref_id"]))


def _closeout_preview(root: Path, instance: Instance, plan: dict[str, Any]) -> dict[str, Any]:
    operation_types = {item["operation_type"] for item in plan.get("operations", [])}
    claim_work = bool(operation_types.intersection({"add_claim", "revise_claim", "move_topic"}))
    memory_paths = {item.get("path") for item in instance.raw.get("memory", {}).get("roles", [])}
    staged_memory_paths = memory_paths.intersection(plan.get("writes", {}))
    count_memory_paths = memory_paths.intersection(instance.raw.get("experience", {}).get("count_surfaces", [])) if claim_work else set()
    affected_memory_paths = sorted(staged_memory_paths | count_memory_paths)
    memory_work = bool(affected_memory_paths)
    affected_authority_refs = _affected_authority_refs(root, instance, plan, count_memory_paths)
    authority_work = bool(affected_authority_refs)
    delta = plan.get("delta") or {}
    phases = [
        {"id": "claim_capture", "status": "planned" if claim_work else "not_needed",
         "read_only": True, "mutation_required": claim_work,
         "reason": "Claim operations are staged in this plan" if claim_work else "No Claim operation is staged"},
        {"id": "memory_synchronization", "status": "planned" if memory_work else "not_configured",
         "read_only": True, "mutation_required": memory_work, "affected_paths": affected_memory_paths,
         "reason": "Configured Memory count surfaces require synchronization after Claim changes" if count_memory_paths else
                   "A configured Memory role is staged for update" if memory_work else "This plan has no staged Memory synchronization"},
        {"id": "git_commit", "status": "planned" if plan.get("writes") else "not_needed",
         "read_only": True, "mutation_required": bool(plan.get("writes")),
         "reason": "Staged files require an authorized Git commit" if plan.get("writes") else "No files are staged"},
        {"id": "authority_refresh", "status": "planned" if authority_work else "not_needed",
         "read_only": True, "mutation_required": authority_work,
         "reason": "Authority References are added, refreshed, or retired" if authority_work else "No Authority Reference maintenance is staged"},
        {"id": "final_validation", "status": "ready" if delta.get("ok") and delta.get("delta_digest") == _content_digest(plan) else "pending",
         "read_only": True, "mutation_required": False,
         "reason": "Current delta validation permits finalize" if delta.get("ok") and delta.get("delta_digest") == _content_digest(plan) else "A current successful delta check is required before finalize"},
    ]
    counts = {"added": 0, "refreshed": 0, "retired": 0, "affected": len(affected_authority_refs)}
    for item in affected_authority_refs:
        if item["change"] in counts:
            counts[item["change"]] += 1
    delta_ready = bool(delta.get("ok") and delta.get("delta_digest") == _content_digest(plan))
    health = "PASS_WITH_REVIEW" if delta_ready and affected_authority_refs else "PASS" if delta_ready else "FAIL"
    return {"read_only": True, "phases": phases, "affected_authority_refs": affected_authority_refs,
            "authority_ref_counts": counts, "health": health}


def inspect(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    _, plan = _load(root, instance, args.plan_id)
    bundle = plan.get("finalized_bundle")
    lifecycle = {"approval_recorded": False, "bundle_state": "not_finalized", "bundle_applied": False}
    if bundle:
        _, approval_path, receipt_path = _core().bundle_paths(root, bundle["bundle_id"])
        projected = lifecycle_projection(
            bundle,
            approved=approval_path.is_file(),
            applied=receipt_path.is_file(),
            events=_core()._lifecycle_events(root, bundle["bundle_id"]),
        )
        lifecycle = {
            "approval_recorded": approval_path.is_file(),
            "bundle_state": projected["state"],
            "bundle_applied": receipt_path.is_file(),
        }
    return _summary(plan, "inspect", delta=plan.get("delta"), closeout_preview=_closeout_preview(root, instance, plan),
                    finalized_bundle_id=(bundle or {}).get("bundle_id"),
                    full_preflight_receipt=plan.get("full_preflight_receipt"), post_apply_receipt=plan.get("post_apply_receipt"),
                    **lifecycle)


def abandon(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id)
    if plan.get("finalized_bundle"):
        _fail("PLAN_FINALIZED_IMMUTABLE", "finalized plan cannot be abandoned")
    if plan.get("state") == "abandoned":
        return _summary(plan, "abandon", replayed=True)
    plan["state"] = "abandoned"; plan["abandon_reason"] = args.reason.strip(); plan["writes"] = {}; _save(path, plan)
    return _summary(plan, "abandon", replayed=False)


def _compact(plan: dict[str, Any], command: str, values: dict[str, Any], *, summary: dict[str, Any]) -> dict[str, Any]:
    findings = values.get("findings", [])
    payload = {"ok": not findings, "command": command, "plan_id": plan["plan_id"], "plan_digest": _content_digest(plan),
               "summary": summary, "failed_case_ids": values.get("failed_case_ids", []),
               "affected_case_ids": values.get("affected_case_ids", []), "artifact_path": values.get("artifact_path"),
               "findings": [{key: item.get(key) for key in ("code", "path", "message", "case_id", "authority_ref_id", "claim_ids", "staged_by_current_plan") if item.get(key) is not None} for item in findings[:12]],
               "cost_counters": _counters(plan),
               **{key: values[key] for key in ("bundle_id", "content_hash", "changed_files", "delta_digest", "touched_operations", "touched_files", "can_finalize") if key in values},
               "errors": findings[:12]}
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > STDOUT_CHARACTER_BUDGET:
        payload["findings"] = payload["findings"][:3]; payload["errors"] = payload["errors"][:3]
    return payload


def _summary(plan: dict[str, Any], action: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "command": f"knowledge-plan {action}", "plan_id": plan["plan_id"], "plan_digest": _content_digest(plan),
            "state": plan["state"], "baseline_commit": plan["baseline_commit"], "operation_count": len(plan["operations"]),
            "claim_count": len(plan["claims"]), "authority_ref_count": len(plan["authority_refs"]),
            "touched_files": sorted(plan.get("writes", {})), "formal_authority_written": False,
            "cost_counters": _counters(plan), **extra, "errors": []}


def dispatch_plan_command(root: Path, args: argparse.Namespace, instance: Instance) -> dict[str, Any]:
    commands = {"init": init_plan, "add-claim": add_claim, "revise-claim": revise_claim, "move-topic": move_topic,
                "add-authority-ref": add_authority_ref, "refresh-authority-ref": refresh_authority_ref,
                "retire-authority-ref": retire_authority_ref, "check": check_delta, "finalize": finalize,
                "inspect": inspect, "abandon": abandon}
    return commands[args.plan_command](root, instance, args)
