"""Deterministic task-start routing and task-end value gate for Project Adapters.

This module decides *whether* an Adapter should invoke the existing Memory and
Knowledge interfaces. It deliberately does not query, deduplicate, authorize,
or mutate Domain Knowledge itself.
"""
from __future__ import annotations

from typing import Any, Iterable

HIGH_RISK_SIGNALS = {
    "complex_diagnosis",
    "architecture_or_domain_change",
    "historical_constraint",
    "cross_file_judgment",
    "real_environment_evidence",
    "permission_or_sensitive_data",
}
VALUE_SIGNALS = {
    "stable_method",
    "real_evidence",
    "user_rule_correction",
    "architecture_decision",
    "knowledge_invalidated",
}


def route_task_start(*, signals: Iterable[str] = (), mechanical: bool = False) -> dict[str, Any]:
    """Return a bounded execution plan; no project files are read here."""
    normalized = sorted(set(signals))
    matched = sorted(HIGH_RISK_SIGNALS.intersection(normalized))
    if mechanical and not matched:
        return {
            "route": "no_query",
            "memory": False,
            "knowledge_levels": [],
            "reason": "ordinary_mechanical_change",
            "matched_signals": [],
        }
    if matched:
        return {
            "route": "memory_then_knowledge",
            "memory": True,
            "knowledge_levels": [1, 2],
            "reason": "bounded_high_risk_route",
            "matched_signals": matched,
        }
    return {
        "route": "no_query",
        "memory": False,
        "knowledge_levels": [],
        "reason": "no_query_trigger",
        "matched_signals": [],
    }


def task_end_value_gate(candidates: Iterable[dict[str, Any]], *, max_bundles: int = 3) -> dict[str, Any]:
    """Select only proposal-worthy candidates; never approves or applies them."""
    if max_bundles < 1 or max_bundles > 3:
        raise ValueError("max_bundles must be between 1 and 3")
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in candidates:
        signals = sorted(set(candidate.get("value_signals", [])))
        matched = sorted(VALUE_SIGNALS.intersection(signals))
        item = {**candidate, "matched_value_signals": matched}
        if matched and len(selected) < max_bundles:
            selected.append(item)
        else:
            reason = "bundle_limit" if matched else "no_durable_value_signal"
            excluded.append({**item, "exclusion_reason": reason})
    return {
        "show_proposals": bool(selected),
        "default_write": False,
        "bundle_limit": max_bundles,
        "proposals": selected,
        "excluded": excluded,
    }
