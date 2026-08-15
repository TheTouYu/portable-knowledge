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

from .authority import (FACT_CLASSES, POLICIES, ROLES, authority_refs_from_document, canonical_authority_document,
                        observe_authority_refs, validate_authority_coverage, validate_authority_ref)
from .bundle import (BundleError, build_bundle, canonical as bundle_bytes, digest as canonical_digest,
                     lifecycle_projection)
from .evaluation_contract import (EvaluationContractError, evaluate_normalized_cases,
                                  load_evaluation_contract, select_delta_cases)
from .instance import Instance

CORE_PLAN_VERSION = "semantic-plan-v2"
CHECK_MODES = ("delta",)
PERMISSION_RANK = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}
STDOUT_CHARACTER_BUDGET = 4096
DEFAULT_BUDGETS = {
    "max_candidate_bundles": 2,
    "max_full_preflight": 1,
    "max_tool_gap": 1,
    "max_noop_actions": 0,
}
CAPTURE_DRAFT_VERSION = 1
_CAPTURE_DRAFT_KEYS = {"schema_version", "intent", "risk", "claims"}
_CAPTURE_CLAIM_KEYS = {"id", "node", "node_name", "node_path", "node_boundary", "node_keywords",
                       "topic_id", "topic_path", "topic_title", "topic_summary", "topic_keywords",
                       "title", "statement", "boundary", "permission", "duplicate_resolution",
                       "fact_classes", "authority_refs"}
_CAPTURE_REF_KEYS = {"claim_id", "path", "locator", "role", "change_policy", "fact_classes", "diagnostic_hash"}
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


MAINTENANCE_UNCOMMITTED_CODE = "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED"


def _authority_registry_drift(root: Path, plan: dict[str, Any], instance: Instance) -> str | None:
    refs_rel = instance.authority.get("authority_refs")
    if not refs_rel:
        return None
    working_path = root / refs_rel
    working = working_path.read_bytes() if working_path.is_file() else None
    head_bytes = _committed_bytes(root, _head(root), refs_rel)
    if working == head_bytes:
        return None
    planned = _decode_writes(plan).get(refs_rel)
    if planned is not None and working == planned:
        return None
    committed = _committed_bytes(root, plan["baseline_commit"], refs_rel)
    if committed == working:
        return None
    try:
        before = authority_refs_from_document(json.loads((committed or b"{}").decode("utf-8")))
        after = {ref["id"]: ref for ref in authority_refs_from_document(json.loads((working or b"{}").decode("utf-8")))}
    except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    for observed in observe_authority_refs(root, before):
        if observed.get("effective_status", observed.get("status")) in {"current", "fresh"}:
            continue
        replacement = after.get(observed.get("id"))
        if replacement is None:
            return refs_rel
        refreshed = observe_authority_refs(root, [replacement])[0]
        if refreshed.get("effective_status", refreshed.get("status")) in {"current", "fresh"}:
            return refs_rel
    return None


def _maintenance_uncommitted_message(plan: dict[str, Any], refs_rel: str) -> str:
    return (
        "Authority maintenance is already reflected in the working tree but has no committed baseline yet: "
        f"HEAD and this plan snapshot still approve the old values (uncommitted path: {refs_rel}). "
        "A human must first review and commit the applied maintenance (separate Git authorization), then abandon "
        f"this plan and rebuild it on the new committed baseline: knowledge-plan abandon {plan['plan_id']} --reason ... "
        "then knowledge-plan init. Rebase cannot re-anchor to uncommitted working-tree content; uncommitted content "
        "is never accepted as the Authority baseline."
    )


def _assert_no_maintenance_drift(root: Path, plan: dict[str, Any], instance: Instance) -> None:
    refs_rel = _authority_registry_drift(root, plan, instance)
    if refs_rel is None:
        return
    _fail(MAINTENANCE_UNCOMMITTED_CODE, _maintenance_uncommitted_message(plan, refs_rel), path=refs_rel,
          plan_id=plan["plan_id"], plan_baseline_commit=plan["baseline_commit"], head_commit=_head(root),
          uncommitted_paths=[refs_rel],
          recommended_action="Review and commit the applied Authority maintenance, then abandon this plan and rebuild it on the new committed baseline.")


def _authority_registry_worktree_snapshot(root: Path, instance: Instance) -> str | None:
    """Hash of the current working-tree authority registry, or None when absent."""
    refs_rel = instance.authority.get("authority_refs")
    if not refs_rel:
        return None
    working_path = root / refs_rel
    return hashlib.sha256(working_path.read_bytes()).hexdigest() if working_path.is_file() else None


def _assert_worktree_snapshot_stable(root: Path, plan: dict[str, Any], instance: Instance) -> None:
    """worktree-baseline plans pin their authority snapshot at init; refuse if the working tree drifted since."""
    refs_rel = instance.authority.get("authority_refs")
    if not refs_rel:
        return
    pinned = plan.get("worktree_authority_hash")
    current = _authority_registry_worktree_snapshot(root, instance)
    if pinned is not None and current is not None and pinned != current:
        _fail("PLAN_WORKTREE_SNAPSHOT_DRIFT",
              f"working-tree authority registry changed since this worktree-baseline plan was initialized ({refs_rel}); "
              "abandon this plan and re-init on the current working tree: "
              f"knowledge-plan abandon {plan['plan_id']} --reason ... then knowledge-plan init --baseline worktree",
              path=refs_rel, plan_id=plan["plan_id"], plan_baseline_commit=plan["baseline_commit"], head_commit=_head(root),
              uncommitted_paths=[refs_rel] if current != pinned else [],
              recommended_action="Abandon this plan and re-initialize with --baseline worktree on the current working tree.")


def _ensure_open(root: Path, instance: Instance, plan: dict[str, Any]) -> None:
    if plan.get("state") != "open":
        _fail("PLAN_NOT_OPEN", f"plan is {plan.get('state')}")
    baseline_mode = plan.get("baseline_mode", "committed")
    if baseline_mode == "worktree":
        # Operator explicitly accepted the working-tree authority as baseline (applied-but-uncommitted maintenance).
        # Skip the committed-baseline drift guards; still refuse if the working tree moved after init.
        _assert_worktree_snapshot_stable(root, plan, instance)
        return
    _assert_no_maintenance_drift(root, plan, instance)
    if _head(root) != plan["baseline_commit"]:
        _fail("PLAN_STALE_BASELINE",
              "committed baseline changed since plan init; recover with knowledge-plan rebase <plan_id> --reason ... (keeps operations) or abandon and re-init (replays them)")


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
    baseline_mode = getattr(args, "baseline", "committed")
    if baseline_mode not in {"committed", "worktree"}:
        _fail("PLAN_INPUT_INVALID", "baseline must be committed or worktree")
    baseline = _head(root)
    identity = {"instance_id": instance.identity["id"], "baseline_commit": baseline, "baseline_mode": baseline_mode,
                "principal": instance.identities["principal"]["id"],
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
        if existing.get("state") == "abandoned":
            _fail("PLAN_ABANDONED", f"plan {plan_id} was previously abandoned; use a different intent to start a new plan")
        return _summary(existing, "init", artifact_path=_local_base(instance).joinpath(path.name).as_posix())
    plan = {"schema_version": 2, "plan_id": plan_id, "plan_digest": plan_digest, **identity, "state": "open",
            "operations": [], "writes": {}, "claims": {}, "existing_claim_changes": {}, "structure_changes": [],
            "authority_refs": [], "authority_ref_refreshes": [], "authority_ref_retirements": [],
            "affected_topics": [], "affected_nodes": [], "path_operations": {}, "delta": None,
            "finalized_bundle": None, "full_preflight_receipt": None, "post_apply_receipt": None,
            "budgets": dict(DEFAULT_BUDGETS), "counters": {key: 0 for key in COUNTER_KEYS}}
    if baseline_mode == "worktree":
        plan["worktree_authority_hash"] = _authority_registry_worktree_snapshot(root, instance)
    _save(path, plan)
    return _summary(plan, "init", artifact_path=_local_base(instance).joinpath(path.name).as_posix(),
                    baseline_mode=plan.get("baseline_mode", "committed"),
                    worktree_authority_hash=plan.get("worktree_authority_hash"))


def add_claim(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
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
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
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
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
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
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
    claim = plan["claims"].get(args.claim_id)
    if not claim:
        plan_path = _local_base(instance) / f"{plan['plan_id']}.json"
        if args.claim_id in plan.get("existing_claim_changes", {}):
            _fail("PLAN_CLAIM_REVISED_NEEDS_REFRESH",
                  f"claim {args.claim_id} was revised, not added in this plan; refresh its existing Authority Ref instead: "
                  f"knowledge-plan refresh-authority-ref <plan_id> --authority-ref-id <ref_id> --reason ...; plan JSON: {plan_path.as_posix()}")
        _fail("PLAN_CLAIM_MISSING", f"planned claim not found: {args.claim_id}; inspect {plan_path.as_posix()} (planned claim ids are listed under 'claims')")
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
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
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
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan)
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
    if args.mode not in CHECK_MODES:
        _fail("PLAN_CHECK_MODE_INVALID", f"unsupported knowledge-plan check mode: {args.mode}")
    path, plan = _load(root, instance, args.plan_id); _ensure_open(root, instance, plan); _assert_budget(plan)
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


def _assert_finalized_environment(root: Path, plan: dict[str, Any], instance: Instance, *, allow_applied: bool = False) -> None:
    if not allow_applied:
        _assert_no_maintenance_drift(root, plan, instance)
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
        warnings = (plan.get("full_preflight_receipt") or {}).get("authority_warnings", [])
        return _compact(plan, "knowledge-plan finalize", {"bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"],
                        "changed_files": bundle["expected_changed_files"], "artifact_path": plan["full_preflight_receipt"]["artifact_path"],
                        "warnings": warnings, "authority_maintenance": _authority_maintenance_summary(warnings)},
                        summary={"finalized": True, "replayed": True, "approved": False, "applied": False})
    _ensure_open(root, instance, plan)
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
        blocking_authority, historical_warnings = _classify_authority_records(plan, records["authority_records"])
        component_ok = (records["validation"].get("ok") and records["projection"].get("ok")
                        and records["tree"].get("ok", False) and not records["failed_case_ids"])
        if not component_ok or blocking_authority:
            failed_artifact = _artifact_rel(instance, content_digest, "full-preflight-failed")
            _write_artifact(root, failed_artifact, {
                "schema_version": 1, "evaluator_contract_version": contract["contract_version"],
                "plan_id": plan["plan_id"], "plan_digest": content_digest, "ok": False,
                "records": records, "authority_warnings": historical_warnings,
                "runtime_version": _runtime_version(), "cost_counters": _counters(plan),
            })
            findings = records["validation"].get("errors", []) + records["projection"].get("errors", []) + records["tree"].get("errors", [])
            findings += [{"code": "PLAN_FULL_EVALUATION_FAILED", "path": "evaluation", "message": case_id,
                          "case_id": case_id, "artifact_path": failed_artifact,
                          "evaluator_contract_version": contract["contract_version"], "runtime_version": _runtime_version()}
                         for case_id in records["failed_case_ids"]]
            findings += blocking_authority + historical_warnings
            if not findings:
                findings.append({"code": "PLAN_FULL_PREFLIGHT_FAILED", "path": "full_preflight",
                                 "message": "full staged preflight failed without component findings"})
            raise _core().SemanticPlanError("PLAN_FULL_PREFLIGHT_FAILED", "full staged preflight failed", findings)
    else:
        historical_warnings = []
    plan["counters"]["full_checks"] += 1; plan["counters"]["full_preflight_checks"] += 1
    plan["counters"]["candidate_bundles"] += 1; _counters(plan); _assert_budget(plan)
    artifact = _artifact_rel(instance, content_digest, "full-preflight")
    _write_artifact(root, artifact, {"schema_version": 1, "plan_id": plan["plan_id"], "plan_digest": content_digest,
                                     "ok": True, "bundle": bundle, "records": records,
                                     "authority_warnings": historical_warnings, "cost_counters": _counters(plan)})
    bundle_path, _, _ = _core().bundle_paths(root, bundle["bundle_id"])
    bundle_path.parent.mkdir(parents=True, exist_ok=True); bundle_path.write_bytes(bundle_bytes(bundle))
    plan["state"] = "finalized"; plan["finalized_bundle"] = bundle; plan["finalized_plan_digest"] = content_digest
    plan["full_preflight_receipt"] = {"ok": True, "plan_digest": content_digest, "bundle_id": bundle["bundle_id"],
                                          "content_hash": bundle["content_hash"], "artifact_path": artifact,
                                          "authority_warnings": historical_warnings}
    _save(path, plan)
    return _compact(plan, "knowledge-plan finalize", {"bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"],
                    "changed_files": bundle["expected_changed_files"], "artifact_path": artifact,
                    "warnings": historical_warnings, "authority_maintenance": _authority_maintenance_summary(historical_warnings)},
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
    _assert_finalized_environment(root, plan, instance, allow_applied=allow_applied)
    return plan


def record_post_apply_full_check(root: Path, instance: Instance, bundle: dict[str, Any]) -> dict[str, Any]:
    path, plan = _load(root, instance, bundle["actions"][0]["provenance"]["plan_id"])
    if plan.get("post_apply_receipt"):
        return plan["post_apply_receipt"]
    contract = _evaluation_contract(root, instance)
    records = _validation_records(root, instance, contract, contract["cases"], "post_apply")
    blocking_authority, historical_warnings = _classify_authority_records(plan, records["authority_records"], phase="post-apply full validation")
    component_ok = (records["validation"].get("ok") and records["projection"].get("ok")
                    and records["tree"].get("ok", False) and not records["failed_case_ids"])
    if not component_ok or blocking_authority:
        findings = records["validation"].get("errors", []) + records["projection"].get("errors", []) + records["tree"].get("errors", [])
        findings += [{"code": "PLAN_POST_APPLY_EVALUATION_FAILED", "path": "evaluation", "message": case_id, "case_id": case_id}
                     for case_id in records["failed_case_ids"]]
        findings += blocking_authority
        raise _core().SemanticPlanError("PLAN_POST_APPLY_FULL_FAILED", "post-apply full validation failed", findings)
    plan["counters"]["full_checks"] += 1; plan["counters"]["post_apply_full_checks"] += 1
    artifact = _artifact_rel(instance, plan["finalized_plan_digest"], "post-apply-full")
    receipt = {"ok": True, "plan_digest": plan["finalized_plan_digest"], "bundle_id": bundle["bundle_id"],
               "artifact_path": artifact, "authority_warnings": historical_warnings}
    _write_artifact(root, artifact, {"schema_version": 1, **receipt, "records": records, "cost_counters": _counters(plan)})
    plan["post_apply_receipt"] = receipt; _save(path, plan)
    return receipt


def _plan_affected_claim_ids(plan: dict[str, Any]) -> set[str]:
    return (set(plan.get("claims", {})) | set(plan.get("existing_claim_changes", {})) |
            {claim_id for operation in plan.get("operations", []) if operation.get("operation_type") == "move_topic"
             for claim_id in operation.get("claim_ids", [])})


def _classify_authority_records(plan: dict[str, Any], authority_records: list[dict[str, Any]], *, phase: str = "full staged preflight") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split non-current full-preflight Authority observations into blocking plan_affected findings and non-blocking historical warnings.

    A Ref is ``plan_affected`` when its path is staged by this plan (staged drift) or when a Claim
    touched by this plan is linked to it; those stay fail-closed. Unrelated historical non-current
    Refs are pre-existing maintenance debt and are reported as non-blocking warnings so the plan
    can still finalize while clearly listing what must be maintained separately.
    """
    changed_paths = set(plan.get("writes", {}))
    changed_claim_ids = _plan_affected_claim_ids(plan)
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for ref in authority_records:
        status = ref.get("effective_status", ref.get("status"))
        if status in {"current", "fresh"}:
            continue
        staged_drift = ref.get("path") in changed_paths
        plan_affected = staged_drift or bool(changed_claim_ids.intersection(ref.get("claim_ids", [])))
        scope = "plan_affected" if plan_affected else "historical"
        finding = {
            "code": "PLAN_AUTHORITY_STAGED_DRIFT" if staged_drift else "PLAN_FULL_AUTHORITY_NOT_CURRENT",
            "path": ref.get("path", "authority_ref"),
            "message": f"Authority Reference {ref.get('id', 'unknown')} is not current during {phase}: {status} ({scope})",
            "authority_ref_id": ref.get("id"), "claim_ids": ref.get("claim_ids", []),
            "authority_scope": scope, "blocking": plan_affected,
            "recommended_action": "Review and refresh or retire this Ref; historical refs may use a separate authority-maintenance plan. After applying maintenance, commit it with human authorization, then abandon and rebuild dependent plans.",
            "baseline_status": ref.get("baseline_status"), "working_tree_status": ref.get("working_tree_status"),
            "effective_status": status, "expected_hash": ref.get("expected_hash", ref.get("approved_hash")),
            "observed_hash": ref.get("observed_hash"), "staged_by_current_plan": staged_drift,
        }
        (blocking if plan_affected else warnings).append(finding)
    return blocking, warnings


def _authority_maintenance_summary(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    historical_ref_ids = [item.get("authority_ref_id") for item in warnings
                          if item.get("authority_scope") == "historical" and item.get("authority_ref_id")]
    return {"historical_count": len(historical_ref_ids), "historical_ref_ids": historical_ref_ids, "blocking": False,
            "recommended_action": "Review historical refs in a separate authority-maintenance plan. After exact-hash apply, commit the maintenance with human authorization, then abandon and rebuild dependent plans."}


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
        changed_claim_ids = _plan_affected_claim_ids(plan)
        drift_path = _authority_registry_drift(root, plan, instance)
        worktree_refs = {}
        if drift_path and (root / drift_path).is_file():
            try:
                worktree_refs = {item["id"]: item for item in authority_refs_from_document(json.loads((root / drift_path).read_text(encoding="utf-8")))}
            except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                worktree_refs = {}
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
        for ref in observe_authority_refs(root, existing):
            status = ref.get("effective_status")
            if status in {"current", "fresh"} or ref.get("id") in reported:
                continue
            plan_affected = ref.get("path") in set(writes) | required_paths or bool(changed_claim_ids.intersection(ref.get("claim_ids", [])))
            if drift_path:
                replacement = worktree_refs.get(ref["id"])
                if replacement is None or observe_authority_refs(root, [replacement])[0].get("effective_status") in {"current", "fresh"}:
                    report.append({"authority_ref_id": ref["id"], "change": "worktree_refreshed_uncommitted",
                                   "scope": "plan_affected" if plan_affected else "historical", "blocking": True,
                                   "path": ref["path"], "old_hash": ref.get("expected_hash"),
                                   "new_hash": ref.get("observed_hash"), "linked_claim_ids": ref.get("claim_ids", []),
                                   "recommended_action": "Review and commit the applied Authority maintenance, then abandon and rebuild this plan.",
                                   "human_review_reason": "The Authority Ref is already refreshed in the working tree but is not committed; HEAD and this plan snapshot still approve the old value."})
                    continue
            report.append({"authority_ref_id": ref["id"], "change": "external_invalidated",
                           "scope": "plan_affected" if plan_affected else "historical",
                           "blocking": plan_affected, "path": ref["path"],
                           "old_hash": ref.get("expected_hash"), "new_hash": ref.get("observed_hash"),
                           "linked_claim_ids": ref.get("claim_ids", []),
                           "recommended_action": "Review and add refresh-authority-ref or retire-authority-ref; use a separate authority-maintenance plan when unrelated to this change.",
                           "human_review_reason": f"Committed Authority changed outside this plan ({status}); refresh the reference before finalize."})
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
    counts = {"added": 0, "refreshed": 0, "retired": 0, "affected": len(affected_authority_refs),
              "plan_affected": sum(item.get("scope", "plan_affected") == "plan_affected" for item in affected_authority_refs),
              "historical": sum(item.get("scope") == "historical" for item in affected_authority_refs)}
    for item in affected_authority_refs:
        if item["change"] in counts:
            counts[item["change"]] += 1
    delta_ready = bool(delta.get("ok") and delta.get("delta_digest") == _content_digest(plan))
    health = "PASS_WITH_REVIEW" if delta_ready and affected_authority_refs else "PASS" if delta_ready else "FAIL"
    historical_ref_ids = [item["authority_ref_id"] for item in affected_authority_refs if item.get("scope") == "historical"]
    drift_path = _authority_registry_drift(root, plan, instance)
    return {"read_only": True, "phases": phases, "affected_authority_refs": affected_authority_refs,
            "authority_ref_counts": counts,
            "authority_maintenance": {"historical_count": len(historical_ref_ids), "historical_ref_ids": historical_ref_ids,
                                      "blocking": bool(drift_path),
                                      "uncommitted_paths": [drift_path] if drift_path else [],
                                      "snapshot_state": "maintenance_uncommitted" if drift_path else "committed",
                                      "recommended_action": (
                                          "The applied Authority maintenance is not committed yet: review and commit it with separate Git authorization, then abandon this plan and rebuild it on the new committed baseline."
                                          if drift_path else
                                          "Review historical refs in a separate authority-maintenance plan. After exact-hash apply, commit the maintenance with human authorization, then abandon and rebuild dependent plans.")},
            "health": health}


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
                    intent=plan["intent"], finalized_bundle_id=(bundle or {}).get("bundle_id"),
                    full_preflight_receipt=plan.get("full_preflight_receipt"), post_apply_receipt=plan.get("post_apply_receipt"),
                    claims=[{"claim_id": claim_id, "title": value.get("title", ""),
                             "fact_classes": value.get("fact_classes", [])}
                            for claim_id, value in sorted(plan["claims"].items())],
                    revised_claims=[{"claim_id": claim_id, "semantic_declaration": value.get("semantic_declaration")}
                                    for claim_id, value in sorted(plan.get("existing_claim_changes", {}).items())],
                    operations=[{"operation_id": operation["operation_id"], "operation_type": operation["operation_type"]}
                                for operation in plan.get("operations", [])],
                    authority_refs=[{"authority_ref_id": ref["id"], "path": ref["path"], "role": ref["role"],
                                     "claim_ids": ref.get("claim_ids", []),
                                     "approved_hash": (ref.get("approved_hash") or ref.get("fragment_hash") or "")[:12]}
                                    for ref in plan.get("authority_refs", [])],
                    **lifecycle)


def rebase_plan(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    path, plan = _load(root, instance, args.plan_id)
    if plan.get("finalized_bundle"):
        _fail("PLAN_FINALIZED_IMMUTABLE", "finalized plan cannot be rebased")
    if plan.get("state") != "open":
        _fail("PLAN_NOT_OPEN", f"plan is {plan.get('state')}")
    reason = args.reason.strip()
    if not reason:
        _fail("PLAN_INPUT_INVALID", "rebase reason required")
    old_baseline = plan["baseline_commit"]
    head = _head(root)
    if plan.get("baseline_mode") == "worktree":
        _assert_worktree_snapshot_stable(root, plan, instance)
    else:
        _assert_no_maintenance_drift(root, plan, instance)
    if head == old_baseline:
        _fail("PLAN_REBASE_NOOP", f"plan baseline {head} is already current")
    refs_rel = instance.authority.get("authority_refs")
    referenced = {item["path"] for item in plan.get("authority_refs", [])}
    referenced |= {item.get("path") for item in plan.get("authority_ref_refreshes", []) if item.get("path")}
    referenced |= {item.get("path") for item in plan.get("authority_ref_retirements", []) if item.get("path")}
    if refs_rel:
        referenced.add(refs_rel)
    conflicts = []
    for rel in sorted(referenced):
        result = _git(root, "diff", "--quiet", old_baseline, head, "--", rel)
        if result.returncode not in {0, 1}:
            _fail("PLAN_REBASE_GIT_ERROR", f"git diff failed for {rel}: {result.stderr.strip()}")
        if result.returncode == 1:
            conflicts.append(rel)
    if conflicts:
        _fail("PLAN_REBASE_CONFLICT",
              "Authority paths changed between plan baseline and HEAD; rebase would re-anchor them under new content: "
              + ", ".join(conflicts)
              + ". Refresh or retire the affected refs in the plan, or abandon and re-init.", path=refs_rel or ".")
    plan["baseline_commit"] = head
    if plan.get("baseline_mode") == "worktree":
        plan["worktree_authority_hash"] = _authority_registry_worktree_snapshot(root, instance)
    plan.setdefault("rebase_history", []).append({"from": old_baseline, "to": head, "reason": reason,
                                                  "at": dt.datetime.now().astimezone().isoformat(timespec="seconds")})
    plan["delta"] = None
    _save(path, plan)
    return _summary(plan, "rebase", old_baseline_commit=old_baseline, rebase_count=len(plan["rebase_history"]))


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
    if values.get("warnings"):
        payload["warnings"] = values["warnings"]
    if values.get("authority_maintenance"):
        payload["authority_maintenance"] = values["authority_maintenance"]
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > STDOUT_CHARACTER_BUDGET:
        payload["findings"] = payload["findings"][:3]; payload["errors"] = payload["errors"][:3]
        if "warnings" in payload:
            payload["warnings"] = payload["warnings"][:2]
    return payload


def _summary(plan: dict[str, Any], action: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "command": f"knowledge-plan {action}", "plan_id": plan["plan_id"], "plan_digest": _content_digest(plan),
            "state": plan["state"], "baseline_commit": plan["baseline_commit"], "operation_count": len(plan["operations"]),
            "claim_count": len(plan["claims"]), "authority_ref_count": len(plan["authority_refs"]),
            "touched_files": sorted(plan.get("writes", {})), "formal_authority_written": False,
            "cost_counters": _counters(plan), **extra, "errors": []}


def _capture_field(claim_index: int, ref_index: int | None = None, field: str | None = None) -> str:
    base = f"claims[{claim_index}]"
    if ref_index is not None:
        base += f".authority_refs[{ref_index}]"
    return f"{base}.{field}" if field else base


def _draft_finding(path: Path, field: str, message: str) -> dict[str, Any]:
    return {"code": "PLAN_DRAFT_INVALID", "path": str(path), "draft_field": field, "message": message}


def load_capture_draft(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        draft = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [{"code": "PLAN_DRAFT_MISSING", "path": str(path), "message": "capture draft file not found"}]
    except ValueError as exc:
        return None, [{"code": "PLAN_DRAFT_INVALID", "path": str(path), "message": f"capture draft is not valid JSON: {exc}"}]
    if not isinstance(draft, dict):
        return None, [_draft_finding(path, "$", "draft must be a JSON object")]
    findings: list[dict[str, Any]] = []
    unknown = sorted(set(draft) - _CAPTURE_DRAFT_KEYS)
    if unknown:
        findings.append(_draft_finding(path, unknown[0], f"unknown draft field: {unknown[0]}"))
    if draft.get("schema_version") != CAPTURE_DRAFT_VERSION:
        findings.append(_draft_finding(path, "schema_version", f"unsupported schema_version: {draft.get('schema_version')!r} (expected {CAPTURE_DRAFT_VERSION})"))
    if not isinstance(draft.get("intent"), str) or not draft["intent"].strip():
        findings.append(_draft_finding(path, "intent", "intent is required"))
    if draft.get("risk") not in {"low", "medium", "high"}:
        findings.append(_draft_finding(path, "risk", "risk must be low, medium, or high"))
    claims = draft.get("claims")
    if not isinstance(claims, list) or not claims:
        findings.append(_draft_finding(path, "claims", "claims must be a non-empty list"))
        return draft, findings
    seen_ids: dict[str, int] = {}
    claim_facts: dict[str, set[str]] = {}
    for index, claim in enumerate(claims):
        prefix = _capture_field(index)
        if not isinstance(claim, dict):
            findings.append(_draft_finding(path, prefix, "claim must be an object")); continue
        unknown = sorted(set(claim) - _CAPTURE_CLAIM_KEYS)
        if unknown:
            findings.append(_draft_finding(path, f"{prefix}.{unknown[0]}", f"unknown claim field: {unknown[0]}"))
        for field in ("node", "topic_id", "title", "statement", "boundary"):
            if not isinstance(claim.get(field), str) or not claim[field].strip():
                findings.append(_draft_finding(path, f"{prefix}.{field}", f"{field} is required"))
        facts = claim.get("fact_classes")
        if not isinstance(facts, list) or not facts or any(value not in FACT_CLASSES for value in facts):
            findings.append(_draft_finding(path, f"{prefix}.fact_classes", "fact_classes must be a non-empty list of valid fact classes"))
        if "permission" in claim and claim["permission"] not in PERMISSION_RANK:
            findings.append(_draft_finding(path, f"{prefix}.permission", f"invalid permission: {claim['permission']!r}"))
        if "duplicate_resolution" in claim and claim["duplicate_resolution"] not in {"cancel", "create_distinct_with_boundary"}:
            findings.append(_draft_finding(path, f"{prefix}.duplicate_resolution", "duplicate_resolution must be cancel or create_distinct_with_boundary"))
        for field in ("node_keywords", "topic_keywords"):
            values = claim.get(field)
            if values is not None and (not isinstance(values, list) or any(not isinstance(value, str) for value in values)):
                findings.append(_draft_finding(path, f"{prefix}.{field}", f"{field} must be a list of strings"))
        if "id" in claim and (not isinstance(claim["id"], str) or not claim["id"].strip()):
            findings.append(_draft_finding(path, f"{prefix}.id", "id must be a non-empty string"))
        elif "id" in claim:
            if claim["id"] in seen_ids:
                findings.append(_draft_finding(path, f"{prefix}.id", f"duplicate claim id: {claim['id']} (also claims[{seen_ids[claim['id']]}])"))
            seen_ids[claim["id"]] = index
            claim_facts[claim["id"]] = set(facts) if isinstance(facts, list) else set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict): continue
        prefix = _capture_field(index); facts = claim.get("fact_classes"); refs = claim.get("authority_refs", [])
        if refs is not None and not isinstance(refs, list):
            findings.append(_draft_finding(path, f"{prefix}.authority_refs", "authority_refs must be a list")); continue
        for ref_index, ref in enumerate(refs or []):
            ref_prefix = _capture_field(index, ref_index)
            if not isinstance(ref, dict):
                findings.append(_draft_finding(path, ref_prefix, "authority ref must be an object")); continue
            unknown = sorted(set(ref) - _CAPTURE_REF_KEYS)
            if unknown:
                findings.append(_draft_finding(path, f"{ref_prefix}.{unknown[0]}", f"unknown authority ref field: {unknown[0]}"))
            for field in ("path", "locator"):
                if not isinstance(ref.get(field), str) or not ref[field].strip():
                    findings.append(_draft_finding(path, f"{ref_prefix}.{field}", f"{field} is required"))
            if ref.get("role") not in ROLES:
                findings.append(_draft_finding(path, f"{ref_prefix}.role", f"invalid role: {ref.get('role')!r}"))
            if ref.get("change_policy") not in POLICIES:
                findings.append(_draft_finding(path, f"{ref_prefix}.change_policy", f"invalid change_policy: {ref.get('change_policy')!r}"))
            ref_facts = ref.get("fact_classes")
            if not isinstance(ref_facts, list) or not ref_facts or any(value not in FACT_CLASSES for value in ref_facts):
                findings.append(_draft_finding(path, f"{ref_prefix}.fact_classes", "fact_classes must be a non-empty list of valid fact classes"))
            elif isinstance(facts, list):
                target_facts = claim_facts.get(ref.get("claim_id"), set(facts))
                if not set(ref_facts).issubset(target_facts):
                    findings.append(_draft_finding(path, f"{ref_prefix}.fact_classes", "authority ref fact classes must be declared by the target claim"))
            target = ref.get("claim_id")
            if target is not None and (not isinstance(target, str) or target not in seen_ids):
                findings.append(_draft_finding(path, f"{ref_prefix}.claim_id", f"claim_id references unknown draft claim: {target!r}"))
    return draft, findings


def _annotate_capture_error(exc: Exception, field: str) -> Exception:
    findings = getattr(exc, "findings", None)
    if not findings: return exc
    return _core().SemanticPlanError(getattr(exc, "code", "PLAN_CAPTURE_FAILED"), str(exc),
                                     [{**item, "draft_field": field} for item in findings])


def _capture_report(plan: dict[str, Any], draft_path: str) -> dict[str, Any]:
    bundle = plan["finalized_bundle"]
    return {"ok": True, "command": "knowledge-plan capture", "draft_path": draft_path,
            "plan_id": plan["plan_id"], "plan_state": "finalized", "bundle_id": bundle["bundle_id"],
            "content_hash": bundle["content_hash"], "semantic_diff": bundle["semantic_diff"],
            "expected_changed_files": bundle["expected_changed_files"], "risk": bundle["risk"],
            "permission_effect": bundle["permission_effect"], "operation_count": len(plan.get("operations", [])),
            "approved": False, "applied": False, "errors": []}


def capture(root: Path, instance: Instance, args: argparse.Namespace) -> dict[str, Any]:
    file_path = Path(args.file) if Path(args.file).is_absolute() else root / args.file
    draft, findings = load_capture_draft(file_path)
    if findings:
        return {"ok": False, "command": "knowledge-plan capture", "draft_path": str(file_path), "plan_id": None,
                "retained_plan": None, "errors": findings, "exit_code": 1}
    plan_id = None; claim_to_field: dict[str, str] = {}
    try:
        created = init_plan(root, instance, argparse.Namespace(intent=draft["intent"], risk=draft["risk"]))
        plan_id = created["plan_id"]
        _, plan = _load(root, instance, plan_id)
        if plan.get("state") == "finalized":
            verify_finalized_bundle_provenance(root, instance, plan["finalized_bundle"])
            return _capture_report(plan, str(file_path))
        claim_ids: dict[str, str] = {}; claim_by_index: dict[int, str] = {}
        for index, claim in enumerate(draft["claims"]):
            ns = argparse.Namespace(plan_id=plan_id, node=claim["node"], node_name=claim.get("node_name"),
                node_path=claim.get("node_path"), node_boundary=claim.get("node_boundary"),
                node_keywords=claim.get("node_keywords", []), topic_id=claim["topic_id"],
                topic_path=claim.get("topic_path"), topic_title=claim.get("topic_title"),
                topic_summary=claim.get("topic_summary", ""), topic_keywords=claim.get("topic_keywords", []),
                title=claim["title"], statement=claim["statement"], boundary=claim["boundary"],
                permission=claim.get("permission", "internal"), duplicate_resolution=claim.get("duplicate_resolution", "cancel"),
                fact_class=claim["fact_classes"])
            try: result = add_claim(root, instance, ns)
            except _core().SemanticPlanError as exc: raise _annotate_capture_error(exc, _capture_field(index)) from exc
            claim_ids[claim.get("id") or result["claim_id"]] = result["claim_id"]
            claim_by_index[index] = result["claim_id"]
            claim_to_field[result["claim_id"]] = _capture_field(index) + (f".{claim['id']}" if claim.get("id") else "")
        for index, claim in enumerate(draft["claims"]):
            for ref_index, ref in enumerate(claim.get("authority_refs", [])):
                target = ref.get("claim_id") or claim.get("id") or claim_by_index[index]
                ns = argparse.Namespace(plan_id=plan_id, claim_id=claim_ids[target], path=ref["path"], locator=ref["locator"],
                    role=ref["role"], change_policy=ref["change_policy"], fact_class=ref["fact_classes"],
                    diagnostic_hash=ref.get("diagnostic_hash"))
                try: add_authority_ref(root, instance, ns)
                except _core().SemanticPlanError as exc: raise _annotate_capture_error(exc, _capture_field(index, ref_index)) from exc
        checked = check_delta(root, instance, argparse.Namespace(plan_id=plan_id, mode="delta"))
        if not checked.get("can_finalize"):
            _, plan = _load(root, instance, plan_id); delta = plan.get("delta") or {}
            failures = [{**item, "draft_field": claim_to_field[item["claim_id"]]} if item.get("claim_id") in claim_to_field else item
                        for item in (delta.get("findings") or checked.get("findings") or [])]
            raise _core().SemanticPlanError("PLAN_DELTA_FAILED", "delta validation failed; fix the draft and re-run with a new intent", failures)
        finalize(root, instance, argparse.Namespace(plan_id=plan_id))
    except (BundleError, _core().SemanticPlanError) as exc:
        code = getattr(exc, "code", "PLAN_CAPTURE_FAILED"); message = str(exc); retained = None
        if plan_id is not None:
            _, plan = _load(root, instance, plan_id)
            if plan.get("state") == "open":
                reason = f"knowledge-plan capture failed ({code}): {message}"
                abandon(root, instance, argparse.Namespace(plan_id=plan_id, reason=reason[:200]))
                retained = {"plan_id": plan_id, "state": "abandoned", "reason": reason}
        errors = getattr(exc, "findings", None) or [{"code": code, "path": ".", "message": message}]
        errors = [{**item, "draft_field": claim_to_field[item["claim_id"]]} if item.get("claim_id") in claim_to_field and "draft_field" not in item else item for item in errors]
        return {"ok": False, "command": "knowledge-plan capture", "draft_path": str(file_path), "plan_id": plan_id,
                "retained_plan": retained, "errors": errors, "exit_code": 1}
    _, plan = _load(root, instance, plan_id)
    return _capture_report(plan, str(file_path))


def dispatch_plan_command(root: Path, args: argparse.Namespace, instance: Instance) -> dict[str, Any]:
    commands = {"init": init_plan, "rebase": rebase_plan, "add-claim": add_claim, "revise-claim": revise_claim, "move-topic": move_topic,
                "add-authority-ref": add_authority_ref, "refresh-authority-ref": refresh_authority_ref,
                "retire-authority-ref": retire_authority_ref, "check": check_delta, "finalize": finalize,
                "inspect": inspect, "abandon": abandon, "capture": capture}
    return commands[args.plan_command](root, instance, args)
