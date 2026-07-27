"""Configured, bounded Context -> Node -> Topic retrieval for Project Adapters."""
from __future__ import annotations

import math
import re
from typing import Any


class RetrievalError(ValueError):
    def __init__(self, message: str, code: str = "RETRIEVAL_ROUTE_ERROR", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _semantic_values(config: dict[str, Any], route: dict[str, Any], field: str, group_field: str) -> set[str]:
    values = {_normalized(str(value)) for value in route.get(field, []) if str(value).strip()}
    groups = config.get("retrieval", {}).get("semantic_groups", {})
    for group_id in route.get(group_field, []):
        values.update(_normalized(str(value)) for value in groups.get(group_id, []) if str(value).strip())
    return values


def _terms(value: str) -> set[str]:
    normalized = _normalized(value)
    latin = set(re.findall(r"[a-z0-9_][a-z0-9_.-]*", normalized))
    cjk_chunks = re.findall(r"[\u3400-\u9fff]+", normalized)
    cjk: set[str] = set(cjk_chunks)
    for chunk in cjk_chunks:
        cjk.update(chunk[index:index + size] for size in (2, 3, 4) for index in range(max(0, len(chunk) - size + 1)))
    return latin | cjk


def select_intent_route(config: dict[str, Any], *, context_id: str, intent: str) -> dict[str, Any]:
    """Select one configured route without searching or expanding knowledge bodies."""
    routes = config.get("retrieval", {}).get("intent_routes", [])
    candidates = [route for route in routes if context_id in route.get("contexts", [])]
    normalized = _normalized(intent)
    exact = [route for route in candidates if _normalized(str(route.get("id", ""))) == normalized]
    if len(exact) == 1:
        return exact[0]

    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for route in candidates:
        blocked = _semantic_values(config, route, "blocked_by", "blocked_by_groups")
        if any(value in normalized for value in blocked):
            continue
        keywords = {_normalized(str(value)) for value in route.get("keywords", []) if str(value).strip()}
        matches = []
        for keyword in keywords:
            if len(keyword) <= 2 and keyword.isascii():
                matched = re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", normalized) is not None
            else:
                matched = keyword in normalized
            if matched:
                matches.append(keyword)
        if matches:
            scored.append((len(matches), int(route.get("priority", 0)), str(route.get("id", "")), route))
    if not scored:
        raise RetrievalError(f"no configured intent route for context {context_id}: {intent}", "RETRIEVAL_ROUTE_UNKNOWN")
    matched_routes = sorted({item[2] for item in scored})
    if len(matched_routes) > 1:
        raise RetrievalError("intent route is ambiguous: " + ", ".join(matched_routes), "RETRIEVAL_ROUTE_AMBIGUOUS",
                             details={"failure_type": "ambiguous", "clarification_options": matched_routes})
    return scored[0][3]


def _metadata(topic: dict[str, Any], node: dict[str, Any], registry_claims: list[dict[str, Any]]) -> str:
    claims = [claim for claim in registry_claims if claim.get("topic_id") == topic.get("id") and claim.get("lifecycle", "active") == "active"]
    compact_claims = " ".join(str(claim.get(key, "")) for claim in claims for key in ("title", "summary", "statement"))
    return " ".join(str(value) for value in (
        node.get("id", ""), node.get("name", ""), node.get("boundary", ""), " ".join(node.get("keywords", [])),
        topic.get("id", ""), topic.get("title", ""), topic.get("summary", ""), " ".join(topic.get("aliases", [])),
        " ".join(topic.get("keywords", [])), compact_claims,
    ))


def _candidate_scores(registry: dict[str, Any], intent: str) -> list[dict[str, Any]]:
    query_terms = _terms(intent)
    if not query_terms:
        return []
    nodes = {node.get("id"): node for node in registry.get("nodes", [])}
    documents = [(topic, _terms(_metadata(topic, nodes.get(topic.get("node_id"), {}), registry.get("claims", [])))) for topic in registry.get("topics", [])]
    document_frequency = {term: sum(term in terms for _, terms in documents) for term in query_terms}
    count = max(1, len(documents))
    results = []
    for topic, terms in documents:
        overlap = query_terms.intersection(terms)
        if not overlap:
            continue
        raw = sum(math.log1p((count + 1) / (document_frequency[term] + 0.5)) for term in overlap)
        confidence = min(1.0, len(overlap) / max(1, min(len(query_terms), 4)))
        results.append({"id": topic["id"], "node_id": topic.get("node_id"), "score": round(raw, 6), "confidence": round(confidence, 6), "matched_terms": sorted(overlap)[:8]})
    return sorted(results, key=lambda item: (-item["score"], item["id"]))


def _dynamic_route(config: dict[str, Any], registry: dict[str, Any], *, context_id: str, intent: str,
                   linked_nodes: set[str], effective_limit: int) -> tuple[dict[str, Any], list[dict[str, Any]], float, float]:
    settings = config.get("retrieval", {}).get("dynamic", {})
    candidate_limit = min(20, max(1, int(settings.get("candidate_limit", 8))))
    confidence_threshold = min(1.0, max(0.0, float(settings.get("confidence_threshold", 0.25))))
    margin_threshold = min(1.0, max(0.0, float(settings.get("margin_threshold", 0.08))))
    all_candidates = _candidate_scores(registry, intent)
    normalized = _normalized(intent)
    blocked_topics = {
        topic_id
        for route in config.get("retrieval", {}).get("intent_routes", [])
        if context_id in route.get("contexts", [])
        and any(term in normalized for term in _semantic_values(config, route, "blocked_by", "blocked_by_groups"))
        for topic_id in route.get("topic_ids", [])
    }
    candidates = [item for item in all_candidates if item["node_id"] in linked_nodes and item["id"] not in blocked_topics][:candidate_limit]
    outside = [item for item in all_candidates if item["node_id"] not in linked_nodes]
    if not candidates:
        failure = "out_of_context" if outside and outside[0]["confidence"] >= confidence_threshold else "coverage_gap"
        raise RetrievalError(f"dynamic retrieval {failure}: {intent}", "RETRIEVAL_CANDIDATE_UNKNOWN",
                             details={"failure_type": failure, "candidate_topics": outside[:3] if failure == "out_of_context" else []})
    confidence = float(candidates[0]["confidence"])
    margin = confidence - float(candidates[1]["confidence"]) if len(candidates) > 1 else confidence
    if confidence < confidence_threshold:
        raise RetrievalError(f"dynamic retrieval coverage gap: {intent}", "RETRIEVAL_CANDIDATE_UNKNOWN",
                             details={"failure_type": "coverage_gap", "candidate_topics": candidates[:3], "confidence": confidence, "margin": margin})
    if len(candidates) > 1 and margin < margin_threshold:
        raise RetrievalError("dynamic retrieval candidates are ambiguous", "RETRIEVAL_CANDIDATE_AMBIGUOUS",
                             details={"failure_type": "ambiguous", "candidate_topics": candidates[:3],
                                      "clarification_options": [item["id"] for item in candidates[:3]], "confidence": confidence, "margin": margin})
    selected = [item for item in candidates if item["confidence"] >= confidence_threshold][:effective_limit]
    route = {"id": None, "topic_ids": [item["id"] for item in selected], "escalate_to_l3": False, "verification_roles": []}
    return route, candidates, confidence, margin


def build_progressive_scope(config: dict[str, Any], registry: dict[str, Any], *, context_id: str,
                            intent: str, limit: int) -> dict[str, Any]:
    """Resolve explicit routes first, then bounded metadata candidates inside one Context."""
    contexts = {item.get("id"): item for item in config.get("memory", {}).get("contexts", [])}
    context = contexts.get(context_id)
    if not context:
        raise RetrievalError(f"context not found: {context_id}", "RETRIEVAL_CONTEXT_UNKNOWN",
                             details={"failure_type": "out_of_context"})
    if context.get("lifecycle") not in {"active", "paused"}:
        raise RetrievalError(f"context is not queryable by default: {context_id}", "RETRIEVAL_CONTEXT_UNAVAILABLE",
                             details={"failure_type": "out_of_context"})

    settings = config.get("retrieval", {})
    hard_limit = min(3, max(1, int(settings.get("max_topics", 3))))
    effective_limit = min(max(1, limit), hard_limit)
    topic_by_id = {item["id"]: item for item in registry.get("topics", [])}
    node_by_id = {item["id"]: item for item in registry.get("nodes", [])}
    linked_nodes = {item.get("node_id") for item in config.get("relations", {}).get("context_nodes", []) if item.get("context_id") == context_id}
    if not linked_nodes:
        raise RetrievalError(f"context has no linked knowledge nodes: {context_id}", "RETRIEVAL_CANDIDATE_UNKNOWN",
                             details={"failure_type": "coverage_gap"})

    strategy, candidate_topics, confidence, margin = "explicit_route", [], 1.0, 1.0
    try:
        route = select_intent_route(config, context_id=context_id, intent=intent)
    except RetrievalError as exc:
        if exc.code != "RETRIEVAL_ROUTE_UNKNOWN":
            raise
        route, candidate_topics, confidence, margin = _dynamic_route(
            config, registry, context_id=context_id, intent=intent, linked_nodes=linked_nodes, effective_limit=effective_limit)
        strategy = "dynamic_metadata"

    topics: list[dict[str, Any]] = []
    for topic_id in route.get("topic_ids", []):
        topic = topic_by_id.get(topic_id)
        if not topic:
            raise RetrievalError(f"configured topic not found: {topic_id}")
        if topic.get("node_id") not in linked_nodes:
            raise RetrievalError(f"topic {topic_id} is outside context {context_id}", "RETRIEVAL_CONTEXT_SCOPE_VIOLATION",
                                 details={"failure_type": "out_of_context"})
        topics.append(topic)
    topics = topics[:effective_limit]
    nodes = []
    for node_id in dict.fromkeys(topic["node_id"] for topic in topics):
        node = node_by_id.get(node_id)
        if not node:
            raise RetrievalError(f"configured node not found: {node_id}")
        nodes.append(node)

    return {"context": context, "route": route, "nodes": nodes, "topics": topics, "limit": effective_limit,
            "truncated": len(route.get("topic_ids", [])) > len(topics), "retrieval_strategy": strategy,
            "candidate_topics": candidate_topics, "confidence": confidence, "margin": margin}
