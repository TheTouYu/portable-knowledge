"""Canonical deterministic retrieval-evaluation contract shared by all gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

EVALUATOR_CONTRACT_VERSION = 1


class EvaluationContractError(ValueError):
    def __init__(self, message: str, *, path: str, field: str | None = None, case_id: str | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.field = field
        self.case_id = case_id


def _alias(value: dict[str, Any], snake: str, camel: str, *, path: str, case_id: str | None = None,
           default: Any = None) -> Any:
    if snake in value and camel in value and value[snake] != value[camel]:
        raise EvaluationContractError(
            f"conflicting evaluation aliases {snake} and {camel}", path=path, field=snake, case_id=case_id)
    if snake in value:
        return value[snake]
    if camel in value:
        return value[camel]
    return default


def _string_list(value: Any, *, path: str, field: str, case_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise EvaluationContractError(f"{field} must be a list of non-empty strings", path=path, field=field, case_id=case_id)
    return list(value)


def load_evaluation_contract(root: Path, instance: Any, *, required: bool = True) -> dict[str, Any]:
    rel = instance.raw.get("evaluation", {}).get("cases_path")
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        if not required and not rel:
            return {"contract_version": EVALUATOR_CONTRACT_VERSION, "path": None,
                    "defaults": {"topic_top_n": 3, "claim_top_n": 5, "permission": "internal"}, "cases": []}
        raise EvaluationContractError("evaluation.cases_path must be a configured project-relative path", path="project-intelligence.json")
    path = root / rel
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationContractError(f"evaluation fixture is unavailable or invalid JSON: {exc}", path=rel) from exc
    if not isinstance(fixture, dict):
        raise EvaluationContractError("evaluation fixture must be an object", path=rel)
    schema = _alias(fixture, "schema_version", "schemaVersion", path=rel)
    if schema != 1:
        raise EvaluationContractError("evaluation cases must use schema version 1", path=rel, field="schema_version")
    raw_cases = fixture.get("cases")
    if not isinstance(raw_cases, list):
        raise EvaluationContractError("evaluation cases must be a list", path=rel, field="cases")
    raw_defaults = fixture.get("defaults", {})
    if not isinstance(raw_defaults, dict):
        raise EvaluationContractError("evaluation defaults must be an object", path=rel, field="defaults")
    topic_top_n = _alias(raw_defaults, "topic_top_n", "topicTopN", path=rel, default=3)
    claim_top_n = _alias(raw_defaults, "claim_top_n", "claimTopN", path=rel, default=5)
    permission = raw_defaults.get("permission", "internal")
    if not isinstance(topic_top_n, int) or not 1 <= topic_top_n <= 20:
        raise EvaluationContractError("topic_top_n must be an integer from 1 to 20", path=rel, field="topic_top_n")
    if not isinstance(claim_top_n, int) or not 1 <= claim_top_n <= 20:
        raise EvaluationContractError("claim_top_n must be an integer from 1 to 20", path=rel, field="claim_top_n")
    if not isinstance(permission, str) or not permission:
        raise EvaluationContractError("permission must be a non-empty string", path=rel, field="permission")

    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        case_path = f"{rel}#cases[{index}]"
        if not isinstance(raw, dict):
            raise EvaluationContractError("evaluation case must be an object", path=case_path)
        case_id = raw.get("id")
        query = raw.get("query")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise EvaluationContractError("evaluation case id must be unique and non-empty", path=case_path, field="id")
        if not isinstance(query, str) or not query.strip():
            raise EvaluationContractError("evaluation case query must be non-empty", path=case_path, field="query", case_id=case_id)
        seen.add(case_id)
        expected_topics = _string_list(_alias(raw, "expected_topic_ids", "expectedTopicIds", path=case_path, case_id=case_id, default=[]),
                                       path=case_path, field="expected_topic_ids", case_id=case_id)
        expected_claims = _string_list(_alias(raw, "expected_claim_ids", "expectedClaimIds", path=case_path, case_id=case_id, default=[]),
                                       path=case_path, field="expected_claim_ids", case_id=case_id)
        forbidden = _string_list(_alias(raw, "must_not_claim_ids", "mustNotClaimIds", path=case_path, case_id=case_id, default=[]),
                                 path=case_path, field="must_not_claim_ids", case_id=case_id)
        terms = _string_list(_alias(raw, "search_terms", "searchTerms", path=case_path, case_id=case_id, default=[]),
                             path=case_path, field="search_terms", case_id=case_id)
        affected = raw.get("affected_by")
        if affected is not None and not isinstance(affected, dict):
            raise EvaluationContractError("affected_by must be an object", path=case_path, field="affected_by", case_id=case_id)
        blocking = raw.get("blocking", True)
        if not isinstance(blocking, bool):
            raise EvaluationContractError("evaluation case blocking must be a boolean", path=case_path, field="blocking", case_id=case_id)
        scope_source = affected if affected is not None else raw
        legacy_scope = affected is None and any(key in raw for key in ("node_ids", "topic_ids", "claim_ids"))
        scope = {
            "node_ids": _string_list(scope_source.get("node_ids", []), path=case_path, field="affected_by.node_ids", case_id=case_id),
            "topic_ids": _string_list(scope_source.get("topic_ids", []), path=case_path, field="affected_by.topic_ids", case_id=case_id),
            "claim_ids": _string_list(scope_source.get("claim_ids", []), path=case_path, field="affected_by.claim_ids", case_id=case_id),
        } if affected is not None or legacy_scope else None
        cases.append({"id": case_id, "query": query.strip(), "search_terms": terms,
                      "expected_topic_ids": expected_topics, "expected_claim_ids": expected_claims,
                      "must_not_claim_ids": forbidden, "affected_by": scope, "blocking": blocking})
    return {"contract_version": EVALUATOR_CONTRACT_VERSION, "path": rel,
            "defaults": {"topic_top_n": topic_top_n, "claim_top_n": claim_top_n, "permission": permission}, "cases": cases}


def select_delta_cases(contract: dict[str, Any], *, node_ids: set[str], topic_ids: set[str], claim_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, str]] = []
    for case in contract["cases"]:
        scope = case["affected_by"]
        if scope is None:
            selected.append(case); decisions.append({"case_id": case["id"], "decision": "selected", "reason": "unscoped_conservative"})
            continue
        intersects = bool(node_ids.intersection(scope["node_ids"]) or topic_ids.intersection(scope["topic_ids"])
                          or claim_ids.intersection(scope["claim_ids"]))
        decision = "selected" if intersects else "deferred"
        decisions.append({"case_id": case["id"], "decision": decision, "reason": "scope_intersection" if intersects else "explicit_scope_unaffected"})
        if intersects:
            selected.append(case)
    return selected, decisions


def evaluate_normalized_cases(contract: dict[str, Any], cases: list[dict[str, Any]],
                              search: Callable[[str, list[str], str, int, bool], dict[str, Any]], *,
                              semantic: bool = False, phase: str = "project") -> dict[str, Any]:
    defaults = contract["defaults"]
    limit = max(defaults["topic_top_n"], defaults["claim_top_n"], 8)
    rows = []
    for case in cases:
        try:
            result = search(case["query"], case["search_terms"], defaults["permission"], limit, semantic)
            results = result.get("results", [])
            topic_rows = [{"rank": item.get("rank", index), "id": item.get("topic_id", item.get("id"))}
                          for index, item in enumerate(results[:defaults["topic_top_n"]], 1)]
            claim_rows = [{"rank": item.get("rank", index), "id": item.get("id")}
                          for index, item in enumerate(results[:defaults["claim_top_n"]], 1)]
            returned_topics = [item["id"] for item in topic_rows]
            returned_claims = [item["id"] for item in claim_rows]
            topic_ok = not case["expected_topic_ids"] or bool(set(case["expected_topic_ids"]) & set(returned_topics))
            claim_ok = not case["expected_claim_ids"] or bool(set(case["expected_claim_ids"]) & set(returned_claims))
            forbidden_hits = sorted(set(case["must_not_claim_ids"]) & set(returned_claims))
            filters_ok = all(item.get("permission") == defaults["permission"] and item.get("lifecycle") == "active"
                             and item.get("conflict") == "none" for item in results)
            assertions = []
            if not topic_ok: assertions.append("expected_topic_missing")
            if not claim_ok: assertions.append("expected_claim_missing")
            if forbidden_hits: assertions.append("forbidden_claim_returned")
            if not filters_ok: assertions.append("visibility_filter_failed")
            ranks = [item["rank"] for item in claim_rows if item["id"] in case["expected_claim_ids"]]
            topic_ranks = [item["rank"] for item in topic_rows if item["id"] in case["expected_topic_ids"]]
            rows.append({"id": case["id"], "case_id": case["id"], "ok": not assertions, "pass": not assertions,
                         "phase": phase, "query": case["query"], "terms": case["search_terms"],
                         "alternate_terms_used": bool(case["search_terms"]), "mode": result.get("mode", "lexical"),
                         "permission": defaults["permission"], "topic_top_n": defaults["topic_top_n"],
                         "claim_top_n": defaults["claim_top_n"], "expected_topic_ids": case["expected_topic_ids"],
                         "returned_topic_ids": returned_topics, "returned_topics": topic_rows,
                         "expected_claim_ids": case["expected_claim_ids"], "returned_claim_ids": returned_claims,
                         "returned_claims": claim_rows, "forbidden_claim_ids": case["must_not_claim_ids"],
                         "forbidden_claim_ids_encountered": forbidden_hits, "failed_assertions": assertions,
                         "topic_pass": topic_ok, "claim_pass": claim_ok, "forbidden_pass": not forbidden_hits,
                         "filter_pass": filters_ok, "best_expected_claim_rank": min(ranks) if ranks else None,
                         "best_expected_topic_rank": min(topic_ranks) if topic_ranks else None,
                         "warnings": result.get("warnings", [])})
        except Exception as exc:
            rows.append({"id": case["id"], "case_id": case["id"], "ok": False, "pass": False, "phase": phase,
                         "query": case["query"], "terms": case["search_terms"], "permission": defaults["permission"],
                         "topic_top_n": defaults["topic_top_n"], "claim_top_n": defaults["claim_top_n"],
                         "failed_assertions": ["evaluation_error"], "error": str(exc), "warnings": []})
    return {"contract_version": contract["contract_version"], "passed": sum(row["pass"] for row in rows),
            "total": len(rows), "topic_top_n": defaults["topic_top_n"], "claim_top_n": defaults["claim_top_n"], "rows": rows}
