#!/usr/bin/env python3
"""Portable Knowledge Core deterministic store, validator, and local projection.

Git text assets under data/knowledge and knowledge are authoritative. SQLite and
transaction state under .local are disposable local projections. This module
uses only the Python standard library and never invokes Git mutations.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

from .instance import Instance, InstanceError, load_instance, validate_project_memory
from .bundle import BundleError, apply_bundle, approval, build_bundle, bundle_paths, canonical as bundle_json, capture_bundle_draft, rollback_bundle, verify_bundle
from .authority import observe_authority_refs, validate_authority_coverage, validate_authority_ref
from .retrieval import RetrievalError, build_progressive_scope

SCHEMA_VERSION = 1
REGISTRY_REL = Path("data/knowledge/registry.json")
ACTORS_REL = Path("data/knowledge/actors.json")
STORE_REL = Path("data/knowledge")
LOCAL_REL = Path(".local/knowledge")
DB_REL = LOCAL_REL / "knowledge.sqlite"
CLAIM_START_RE = re.compile(r"<!--\s*CLAIM:START\s+(clm_[0-9A-HJKMNP-TV-Z]{26})\s*-->")
CLAIM_END_RE = re.compile(r"<!--\s*CLAIM:END\s+(clm_[0-9A-HJKMNP-TV-Z]{26})\s*-->")
ID_RE = {
    "event": re.compile(r"^evt_[0-9A-HJKMNP-TV-Z]{26}$"),
    "source": re.compile(r"^src_[0-9A-HJKMNP-TV-Z]{26}$"),
    "family": re.compile(r"^sfm_[0-9A-HJKMNP-TV-Z]{26}$"),
    "claim": re.compile(r"^clm_[0-9A-HJKMNP-TV-Z]{26}$"),
    "proposal": re.compile(r"^prp_[0-9A-HJKMNP-TV-Z]{26}$"),
}
SHARD_RE = re.compile(r"^(\d{4}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.jsonl$")
MIGRATION_STATES = {"legacy", "pilot", "managed"}
SOURCE_RESULTS = {"existing_source", "new_representation", "new_version", "new_source", "needs_review"}
SUPPORT_TYPES = {"supports", "contradicts", "qualifies"}
PERMISSIONS = {"restricted", "internal", "public_redacted", "public"}
SENSITIVITIES = {"generalized", "restricted"}
EVENT_TYPES = {
    "sources": {"source_registered", "source_corrected", "source_retracted", "processed_as_duplicate"},
    "evidence": {"evidence_added", "evidence_corrected", "evidence_retracted"},
    "proposals": {
        "proposal_created", "proposal_resolved", "claim_revised", "claim_superseded",
        "claims_merged", "claim_confirmed", "claim_permission_changed",
    },
}
LIFECYCLES = {"draft", "active", "superseded", "deprecated", "rejected"}
CONFIRMATIONS = {"unconfirmed", "confirmed", "confirmed_with_limits"}
QUERY_BUDGETS = {1: 4_000, 2: 8_000, 3: 20_000}
AUTHORIZED_REVIEW_ROLES = {"business_reviewer", "owner"}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+"),
)
SENSITIVE_PATTERNS = (
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


class KnowledgeError(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def root_default() -> Path:
    return Path.cwd()


def configure(instance: Instance) -> None:
    """Bind compatibility path constants to one explicitly configured instance."""
    global REGISTRY_REL, ACTORS_REL, STORE_REL, LOCAL_REL, DB_REL
    authority = instance.authority
    REGISTRY_REL = Path(authority["registry"])
    ACTORS_REL = Path(authority["actors"])
    STORE_REL = Path(authority["store"])
    LOCAL_REL = instance.projection_path
    DB_REL = LOCAL_REL / "knowledge.sqlite"


def relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeError(f"required file missing: {path.as_posix()}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"invalid UTF-8 JSON {path.as_posix()}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[\w\u3400-\u9fff]+", text, re.UNICODE))


def content_hash(text: str) -> str:
    return sha256_bytes(normalize_text(text).encode("utf-8"))


def text_fingerprint(text: str) -> str:
    tokens = normalize_text(text).split()
    shingles = {" ".join(tokens[i:i + 3]) for i in range(max(1, len(tokens) - 2))}
    return sha256_bytes("\n".join(sorted(shingles)).encode("utf-8"))


def ngrams(text: str, size: int = 2) -> list[str]:
    compact = re.sub(r"\s+", "", normalize_text(text))
    if not compact:
        return []
    if len(compact) <= size:
        return [compact]
    return sorted({compact[i:i + size] for i in range(len(compact) - size + 1)})


# Monotonicity inside one process plus 80 random bits gives collision-safe offline IDs.
_last_ulid_ms = -1
_last_ulid_random = 0
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(now_ms: int | None = None, random_bytes: bytes | None = None) -> str:
    global _last_ulid_ms, _last_ulid_random
    timestamp = int(time.time() * 1000) if now_ms is None else now_ms
    if not 0 <= timestamp < 2**48:
        raise KnowledgeError("ULID timestamp is outside 48-bit range")
    random_value = int.from_bytes(os.urandom(10) if random_bytes is None else random_bytes, "big")
    if timestamp == _last_ulid_ms and random_bytes is None:
        random_value = max(random_value, _last_ulid_random + 1) % (2**80)
    _last_ulid_ms, _last_ulid_random = timestamp, random_value
    value = (timestamp << 80) | random_value
    return "".join(_CROCKFORD[(value >> (5 * (25 - index))) & 31] for index in range(26))


def new_id(kind: str) -> str:
    prefixes = {"event": "evt", "source": "src", "family": "sfm", "claim": "clm", "proposal": "prp"}
    if kind not in prefixes:
        raise KnowledgeError(f"unknown ID kind: {kind}")
    return f"{prefixes[kind]}_{new_ulid()}"


def evidence_business_key(event: dict[str, Any]) -> str:
    return "\x1f".join(str(event.get(key, "")) for key in ("claim_id", "source_id", "locator", "support_type"))


def _portable_relative_path(value: str, prefix: str | None = None) -> str | None:
    if "\\" in value or re.match(r"^[A-Za-z]:", value) or value.startswith("/"):
        return "path must be project-relative and use '/'"
    pure = PurePosixPath(value)
    if ".." in pure.parts or any(char in value for char in '<>:"|?*'):
        return "path is not portable"
    if any(part.rstrip(". ").upper() in WINDOWS_RESERVED for part in pure.parts):
        return "path contains a Windows reserved name"
    if prefix and not (value == prefix or value.startswith(prefix.rstrip("/") + "/")):
        return f"path must remain under {prefix}/"
    return None


def _knowledge_rel(root: Path) -> Path:
    try:
        return Path(load_instance(root).authority["knowledge"])
    except InstanceError:
        return Path("knowledge")


def load_authority(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry, actors = read_json(root / REGISTRY_REL), read_json(root / ACTORS_REL)
    return registry, actors


def iter_jsonl(root: Path) -> Iterator[tuple[str, str, int, dict[str, Any]]]:
    for category in ("sources", "evidence", "proposals"):
        directory = root / STORE_REL / category
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            rel = relpath(root, path)
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise KnowledgeError(f"cannot read UTF-8 JSONL {rel}: {exc}") from exc
            if b"\r" in raw:
                raise KnowledgeError(f"JSONL must use LF: {rel}")
            for line_no, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise KnowledgeError(f"invalid JSONL {rel}:{line_no}: {exc}") from exc
                if not isinstance(event, dict):
                    raise KnowledgeError(f"JSONL event must be object: {rel}:{line_no}")
                yield category, rel, line_no, event


def parse_claims(root: Path, registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Finding]]:
    findings: list[Finding] = []
    topics = {topic["path"]: topic for topic in registry.get("topics", [])}
    claim_metadata = registry.get("claim_metadata", {})
    claims: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for path in sorted((root / _knowledge_rel(root)).rglob("*.md")):
        rel = relpath(root, path)
        raw = path.read_bytes()
        if b"\r" in raw:
            findings.append(Finding("TEXT_LINE_ENDING", rel, "must use LF line endings"))
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            findings.append(Finding("TEXT_ENCODING", rel, str(exc)))
            continue
        starts, ends = list(CLAIM_START_RE.finditer(text)), list(CLAIM_END_RE.finditer(text))
        markers = sorted([(m.start(), "start", m) for m in starts] + [(m.start(), "end", m) for m in ends])
        active: tuple[str, int] | None = None
        for _, marker_type, match in markers:
            claim_id = match.group(1)
            if marker_type == "start":
                if active:
                    findings.append(Finding("CLAIM_NESTED", rel, f"nested claim {claim_id}"))
                else:
                    active = (claim_id, match.end())
            elif not active:
                findings.append(Finding("CLAIM_UNPAIRED", rel, f"end without start: {claim_id}"))
            else:
                opened_id, body_start = active
                if opened_id != claim_id:
                    findings.append(Finding("CLAIM_MISMATCH", rel, f"start {opened_id}, end {claim_id}"))
                else:
                    body = text[body_start:match.start()].strip()
                    heading = next((line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("#")), claim_id)
                    topic = topics.get(rel)
                    if not topic:
                        findings.append(Finding("CLAIM_TOPIC_MISSING", rel, f"claim {claim_id} is not in a registered topic"))
                    claims.append({
                        "id": claim_id, "path": rel, "topic_id": topic["id"] if topic else None,
                        "node_id": topic["node_id"] if topic else None, "title": heading, "statement": body,
                        "lifecycle": "active", "confirmation": "unconfirmed", "conflict": "none",
                        "permission": topic.get("permission", "internal") if topic else "internal",
                        "content_hash": content_hash(body), "fingerprint": text_fingerprint(body),
                        "fact_classes": claim_metadata.get(claim_id, {}).get("fact_classes", []),
                    })
                    if claim_id in seen:
                        findings.append(Finding("CLAIM_ID_DUPLICATE", rel, f"also appears in {seen[claim_id]}"))
                    seen[claim_id] = rel
                active = None
        if active:
            findings.append(Finding("CLAIM_UNPAIRED", rel, f"start without end: {active[0]}"))
    return claims, findings


def projected_state(events: list[tuple[str, str, int, dict[str, Any]]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Fold append-only semantic and evidence events into current state."""
    states: dict[str, dict[str, Any]] = {}
    retracted_evidence: set[str] = set()
    for category, _, _, event in events:
        event_type = event.get("event_type")
        claim_id = event.get("claim_id")
        if category == "evidence" and event_type == "evidence_retracted":
            retracted_evidence.add(str(event.get("target_event_id", "")))
        elif category == "proposals" and claim_id:
            state = states.setdefault(str(claim_id), {})
            if event_type == "claim_superseded":
                state.update(lifecycle="superseded", superseded_by=event.get("replacement_claim_id"))
            elif event_type == "claims_merged":
                state.update(lifecycle="superseded", superseded_by=event.get("target_claim_id"), merged_into=event.get("target_claim_id"))
            elif event_type == "claim_confirmed":
                state["confirmation"] = event.get("confirmation")
            elif event_type == "claim_permission_changed":
                state["permission"] = event.get("permission")
    return states, retracted_evidence


def apply_projected_state(claims: list[dict[str, Any]], events: list[tuple[str, str, int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], set[str]]:
    states, retracted = projected_state(events)
    for claim in claims:
        claim.update(states.get(claim["id"], {}))
    return claims, retracted


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    findings: list[Finding] = []
    for authority_rel in (REGISTRY_REL, ACTORS_REL):
        authority_path = root / authority_rel
        if authority_path.is_file():
            raw = authority_path.read_bytes()
            if b"\r" in raw:
                findings.append(Finding("TEXT_LINE_ENDING", authority_rel.as_posix(), "must use LF line endings"))
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                findings.append(Finding("TEXT_ENCODING", authority_rel.as_posix(), str(exc)))
    try:
        registry, actors_doc = load_authority(root)
    except KnowledgeError as exc:
        return report("validate", [Finding("AUTHORITY_INVALID", ".", str(exc))])
    if registry.get("schema_version") != SCHEMA_VERSION:
        findings.append(Finding("REGISTRY_SCHEMA", REGISTRY_REL.as_posix(), "unsupported schema_version"))
    if actors_doc.get("schema_version") != SCHEMA_VERSION:
        findings.append(Finding("ACTORS_SCHEMA", ACTORS_REL.as_posix(), "unsupported schema_version"))
    actors = actors_doc.get("actors", [])
    actor_ids = [actor.get("id") for actor in actors if isinstance(actor, dict)]
    try:
        instance = load_instance(root)
        actor_map = instance.raw.get("compatibility", {}).get("v1_actor_map", {})
        configured_principal = instance.identities["principal"]["id"]
        configured_writer = instance.identities["writer"]["id"]
    except (InstanceError, KeyError):
        actor_map, configured_principal, configured_writer = {}, None, None
    if len(actor_ids) != len(set(actor_ids)) or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(x)) for x in actor_ids):
        findings.append(Finding("ACTOR_ID", ACTORS_REL.as_posix(), "actor IDs must be unique portable slugs"))
    knowledge_prefix = _knowledge_rel(root).as_posix()
    nodes = registry.get("nodes", [])
    node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(set(node_ids)):
        findings.append(Finding("NODE_ID_DUPLICATE", REGISTRY_REL.as_posix(), "node IDs must be unique"))
    for node in nodes:
        path, state = node.get("path", ""), node.get("migration_status")
        error = _portable_relative_path(path, knowledge_prefix)
        if error:
            findings.append(Finding("NODE_PATH", REGISTRY_REL.as_posix(), f"{node.get('id')}: {error}"))
        elif not (root / path).exists():
            findings.append(Finding("NODE_PATH_MISSING", path, f"node {node.get('id')} path does not exist"))
        if state not in MIGRATION_STATES:
            findings.append(Finding("MIGRATION_STATUS", REGISTRY_REL.as_posix(), f"{node.get('id')}: {state}"))
    topics = registry.get("topics", [])
    topic_ids, topic_paths = [x.get("id") for x in topics], [x.get("path") for x in topics]
    if len(topic_ids) != len(set(topic_ids)) or len(topic_paths) != len(set(topic_paths)):
        findings.append(Finding("TOPIC_DUPLICATE", REGISTRY_REL.as_posix(), "topic IDs and paths must be unique"))
    duplicate_suffix = re.compile(r"(?:^|[-_ ])(?:copy|duplicate|副本|重复|\d+)$", re.IGNORECASE)
    normalized_topic_keys: dict[str, str] = {}
    for topic in topics:
        stem = PurePosixPath(str(topic.get("path", ""))).stem
        key = duplicate_suffix.sub("", normalize_text(stem)).strip()
        if key and key in normalized_topic_keys:
            findings.append(Finding("TOPIC_SILENT_DUPLICATE", str(topic.get("path", "")), f"looks like a suffixed duplicate of {normalized_topic_keys[key]}"))
        elif key:
            normalized_topic_keys[key] = str(topic.get("path", ""))
    for topic in topics:
        if topic.get("node_id") not in node_ids:
            findings.append(Finding("TOPIC_NODE_MISSING", REGISTRY_REL.as_posix(), f"{topic.get('id')}: {topic.get('node_id')}"))
        error = _portable_relative_path(topic.get("path", ""), knowledge_prefix)
        if error or not (root / topic.get("path", "")).is_file():
            findings.append(Finding("TOPIC_PATH", topic.get("path", ""), error or "topic file missing"))
    claims, claim_findings = parse_claims(root, registry)
    findings.extend(claim_findings)
    claim_ids = {claim["id"] for claim in claims}
    try:
        instance_for_refs = load_instance(root)
        refs_value = instance_for_refs.authority.get("authority_refs")
        refs = read_json(root / refs_value).get("refs", []) if refs_value else []
        for ref in refs:
            for error in validate_authority_ref(ref)["errors"]:
                findings.append(Finding(error["code"], refs_value or "authority_ref", error["message"]))
        for coverage in validate_authority_coverage(claims, refs):
            findings.append(Finding(coverage["code"], str(refs_value or REGISTRY_REL), f"{coverage['claim_id']}: missing {', '.join(coverage['missing_fact_classes'])}"))
    except (InstanceError, OSError, json.JSONDecodeError):
        pass
    event_ids: dict[str, str] = {}
    source_ids: dict[str, str] = {}
    family_hashes: dict[tuple[str, str], str] = {}
    evidence_keys: dict[str, tuple[str, str]] = {}
    evidence_event_ids: set[str] = set()
    content_hashes: dict[str, str] = {}
    proposal_ids: dict[str, str] = {}
    try:
        events = list(iter_jsonl(root))
    except KnowledgeError as exc:
        findings.append(Finding("JSONL_INVALID", STORE_REL.as_posix(), str(exc)))
        events = []
    for category, rel, line_no, event in events:
        location = f"{rel}:{line_no}"
        match = SHARD_RE.match(Path(rel).name)
        event_schema = event.get("schema_version")
        actor = event.get("actor") if event_schema == 1 else event.get("writer")
        principal = event.get("principal") if event_schema == 2 else actor_map.get(actor)
        if not match or match.group(2) != actor or actor not in actor_ids:
            findings.append(Finding("ACTOR_SHARD_MISMATCH", location, f"writer {actor!r} does not own shard"))
        if event_schema == 2 and (principal != configured_principal or actor != configured_writer or not event.get("executor") or not event.get("workspace")):
            findings.append(Finding("EVENT_IDENTITY", location, "new event identity must match configured principal/writer and include executor/workspace"))
        created_at = event.get("created_at", "")
        if match and (not isinstance(created_at, str) or created_at[:7] != match.group(1)):
            findings.append(Finding("EVENT_SHARD_MONTH", location, "created_at month does not match shard"))
        if event_schema not in {1, 2} or event.get("event_type") not in EVENT_TYPES[category]:
            findings.append(Finding("EVENT_SCHEMA", location, "unsupported schema or event_type"))
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not ID_RE["event"].fullmatch(event_id):
            findings.append(Finding("EVENT_ID", location, f"invalid event_id: {event_id}"))
        elif event_id in event_ids:
            findings.append(Finding("EVENT_ID_DUPLICATE", location, f"also in {event_ids[event_id]}"))
        else:
            event_ids[event_id] = location
        try:
            dt.datetime.fromisoformat(event.get("created_at", ""))
            if dt.datetime.fromisoformat(event["created_at"]).tzinfo is None:
                raise ValueError
        except (TypeError, ValueError):
            findings.append(Finding("EVENT_TIME", location, "created_at must be timezone-aware ISO 8601"))
        serialized = canonical_json(event)
        if any(pattern.search(serialized) for pattern in SECRET_PATTERNS):
            findings.append(Finding("SECRET_DETECTED", location, "event contains credential-like content"))
        if category == "sources" and event.get("event_type") == "source_registered":
            source_id, family_id = event.get("source_id"), event.get("source_family_id")
            if not isinstance(source_id, str) or not ID_RE["source"].fullmatch(source_id):
                findings.append(Finding("SOURCE_ID", location, f"invalid source_id: {source_id}"))
            elif source_id in source_ids:
                findings.append(Finding("SOURCE_ID_DUPLICATE", location, f"also in {source_ids[source_id]}"))
            else:
                source_ids[source_id] = location
            if not isinstance(family_id, str) or not ID_RE["family"].fullmatch(family_id):
                findings.append(Finding("SOURCE_FAMILY_ID", location, f"invalid source_family_id: {family_id}"))
            if event.get("registration_result") not in SOURCE_RESULTS:
                findings.append(Finding("SOURCE_RESULT", location, "invalid registration_result"))
            source_path = event.get("source_path")
            if source_path is not None:
                path_error = _portable_relative_path(str(source_path))
                if path_error:
                    findings.append(Finding("SOURCE_PATH", location, path_error))
            digest = event.get("content_hash")
            if digest:
                if digest in content_hashes and event.get("registration_result") == "new_source":
                    findings.append(Finding("SOURCE_CONTENT_DUPLICATE", location, f"same content as {content_hashes[digest]}"))
                content_hashes[digest] = source_id
                key = (family_id, str(event.get("representation", "")))
                if key in family_hashes and family_hashes[key] != digest:
                    findings.append(Finding("SOURCE_REPRESENTATION_CONFLICT", location, "same family representation has conflicting content"))
                family_hashes[key] = digest
        if category == "proposals":
            event_type = event.get("event_type")
            proposal_id = event.get("proposal_id")
            if event_type == "proposal_created":
                if not isinstance(proposal_id, str) or not ID_RE["proposal"].fullmatch(proposal_id):
                    findings.append(Finding("PROPOSAL_ID", location, f"invalid proposal_id: {proposal_id}"))
                else:
                    proposal_ids[proposal_id] = location
            elif event_type == "proposal_resolved" and proposal_id not in proposal_ids:
                findings.append(Finding("PROPOSAL_MISSING", location, str(proposal_id)))
            if event_type in {"claim_revised", "claim_superseded", "claims_merged", "claim_confirmed", "claim_permission_changed"}:
                if event.get("claim_id") not in claim_ids:
                    findings.append(Finding("LIFECYCLE_CLAIM_MISSING", location, str(event.get("claim_id"))))
                if event_type == "claim_superseded" and event.get("replacement_claim_id") not in claim_ids:
                    findings.append(Finding("SUPERSEDE_TARGET_MISSING", location, str(event.get("replacement_claim_id"))))
                if event_type == "claims_merged" and event.get("target_claim_id") not in claim_ids:
                    findings.append(Finding("MERGE_TARGET_MISSING", location, str(event.get("target_claim_id"))))
                if event_type == "claim_confirmed" and event.get("confirmation") not in CONFIRMATIONS:
                    findings.append(Finding("CONFIRMATION_INVALID", location, str(event.get("confirmation"))))
                if event_type == "claim_permission_changed" and event.get("permission") not in PERMISSIONS:
                    findings.append(Finding("PERMISSION_INVALID", location, str(event.get("permission"))))
        if category == "evidence" and event.get("event_type") == "evidence_added":
            evidence_event_ids.add(str(event.get("event_id")))
            if event.get("claim_id") not in claim_ids:
                findings.append(Finding("EVIDENCE_CLAIM_MISSING", location, str(event.get("claim_id"))))
            if event.get("source_id") not in source_ids:
                findings.append(Finding("EVIDENCE_SOURCE_MISSING", location, str(event.get("source_id"))))
            if event.get("support_type") not in SUPPORT_TYPES:
                findings.append(Finding("EVIDENCE_SUPPORT_TYPE", location, str(event.get("support_type"))))
            if event.get("permission") not in PERMISSIONS or event.get("sensitivity") not in SENSITIVITIES:
                findings.append(Finding("EVIDENCE_CLASSIFICATION", location, "invalid permission or sensitivity"))
            summary = event.get("summary")
            if summary is not None and len(summary) > 240:
                findings.append(Finding("EVIDENCE_SUMMARY_LENGTH", location, "summary exceeds 240 characters"))
            if summary and any(pattern.search(summary) for pattern in SENSITIVE_PATTERNS):
                findings.append(Finding("SENSITIVE_SUMMARY", location, "summary contains direct identifier"))
            if event.get("sensitivity") == "restricted" and summary is not None:
                findings.append(Finding("RESTRICTED_SUMMARY", location, "restricted evidence summary must be null"))
            key = evidence_business_key(event)
            digest = content_hash(canonical_json({k: v for k, v in event.items() if k not in {"event_id", "created_at"}}))
            if key in evidence_keys:
                old_digest, old_location = evidence_keys[key]
                code = "EVIDENCE_KEY_DUPLICATE" if old_digest == digest else "EVIDENCE_KEY_CONFLICT"
                findings.append(Finding(code, location, f"same business key as {old_location}"))
            evidence_keys[key] = (digest, location)
        if category == "evidence" and event.get("event_type") == "evidence_retracted":
            if event.get("target_event_id") not in evidence_event_ids:
                findings.append(Finding("EVIDENCE_RETRACTION_TARGET", location, str(event.get("target_event_id"))))
    states, _ = projected_state(events)
    for claim_id, state in states.items():
        if state.get("lifecycle") == "superseded" and not state.get("superseded_by"):
            findings.append(Finding("SUPERSEDED_WITHOUT_TARGET", "data/knowledge/proposals", claim_id))
    return report("validate", findings, counts={"nodes": len(nodes), "topics": len(topics), "claims": len(claims), "events": len(events), "sources": len(source_ids)})


def report(command: str, findings: Iterable[Finding], **extra: Any) -> dict[str, Any]:
    errors = sorted(set(findings), key=lambda x: (x.path, x.code, x.message))
    return {"ok": not errors, "command": command, **extra, "errors": [asdict(x) for x in errors]}


def clean_projection(root: Path) -> Path:
    db = root / DB_REL
    db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        with contextlib.suppress(FileNotFoundError):
            Path(str(db) + suffix).unlink()
    return db


def rebuild(root: Path) -> dict[str, Any]:
    validation = validate(root)
    if not validation["ok"]:
        return {"ok": False, "command": "rebuild", "projection_valid": False, "errors": validation["errors"]}
    registry, _ = load_authority(root)
    claims, _ = parse_claims(root, registry)
    events = list(iter_jsonl(root))
    claims, retracted_evidence = apply_projected_state(claims, events)
    db = clean_projection(root)
    try:
        connection = sqlite3.connect(db)
        connection.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE nodes(id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, boundary TEXT NOT NULL, keywords TEXT NOT NULL, migration_status TEXT NOT NULL);
            CREATE TABLE topics(id TEXT PRIMARY KEY, node_id TEXT NOT NULL, title TEXT NOT NULL, path TEXT NOT NULL, summary TEXT NOT NULL, keywords TEXT NOT NULL, permission TEXT NOT NULL);
            CREATE TABLE claims(id TEXT PRIMARY KEY, node_id TEXT, topic_id TEXT, path TEXT NOT NULL, title TEXT NOT NULL, statement TEXT NOT NULL, lifecycle TEXT NOT NULL, confirmation TEXT NOT NULL, conflict TEXT NOT NULL, permission TEXT NOT NULL, content_hash TEXT NOT NULL, fingerprint TEXT NOT NULL);
            CREATE TABLE sources(id TEXT PRIMARY KEY, family_id TEXT NOT NULL, title TEXT NOT NULL, permission TEXT NOT NULL, content_hash TEXT);
            CREATE TABLE evidence(event_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, source_id TEXT NOT NULL, source_family_id TEXT NOT NULL, locator TEXT NOT NULL, support_type TEXT NOT NULL, evidence_kind TEXT NOT NULL, summary TEXT, permission TEXT NOT NULL, sensitivity TEXT NOT NULL, created_at TEXT NOT NULL, business_key TEXT NOT NULL UNIQUE);
            CREATE TABLE search_ngrams(kind TEXT NOT NULL, object_id TEXT NOT NULL, gram TEXT NOT NULL, PRIMARY KEY(kind, object_id, gram));
            CREATE VIRTUAL TABLE search USING fts5(kind UNINDEXED, object_id UNINDEXED, title, body, keywords, tokenize='unicode61');
        """)
        connection.execute("INSERT INTO metadata VALUES (?, ?)", ("schema_version", str(SCHEMA_VERSION)))
        for node in registry["nodes"]:
            keywords = " ".join(node.get("keywords", []))
            connection.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?)", (node["id"], node["name"], node["path"], node["boundary"], keywords, node["migration_status"]))
            add_search(connection, "node", node["id"], node["name"], node["boundary"], keywords)
        for topic in registry.get("topics", []):
            keywords = " ".join(topic.get("keywords", []))
            connection.execute("INSERT INTO topics VALUES (?,?,?,?,?,?,?)", (topic["id"], topic["node_id"], topic["title"], topic["path"], topic.get("summary", ""), keywords, topic.get("permission", "internal")))
            add_search(connection, "topic", topic["id"], topic["title"], topic.get("summary", ""), keywords)
        for claim in claims:
            connection.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tuple(claim[key] for key in ("id", "node_id", "topic_id", "path", "title", "statement", "lifecycle", "confirmation", "conflict", "permission", "content_hash", "fingerprint")))
            add_search(connection, "claim", claim["id"], claim["title"], claim["statement"], "")
        for category, _, _, event in events:
            if category == "sources" and event["event_type"] == "source_registered":
                connection.execute("INSERT INTO sources VALUES (?,?,?,?,?)", (event["source_id"], event["source_family_id"], event.get("title", ""), event.get("permission", "internal"), event.get("content_hash")))
            elif category == "evidence" and event["event_type"] == "evidence_added" and event["event_id"] not in retracted_evidence:
                family = connection.execute("SELECT family_id FROM sources WHERE id=?", (event["source_id"],)).fetchone()[0]
                connection.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (event["event_id"], event["claim_id"], event["source_id"], family, event.get("locator", ""), event["support_type"], event.get("evidence_kind", "practice_statement"), event.get("summary"), event["permission"], event["sensitivity"], event["created_at"], evidence_business_key(event)))
        connection.commit()
        fts5 = connection.execute("SELECT count(*) FROM search").fetchone()[0]
        connection.close()
    except Exception as exc:
        with contextlib.suppress(Exception):
            connection.close()
        for suffix in ("", "-wal", "-shm"):
            with contextlib.suppress(FileNotFoundError):
                Path(str(db) + suffix).unlink()
        marker = db.parent / "projection_failed.json"
        atomic_write(marker, (canonical_json({"schema_version": 1, "error": str(exc)}) + "\n").encode(), expected_hash=file_hash(marker))
        return {"ok": False, "command": "rebuild", "projection_valid": False, "errors": [{"code": "PROJECTION_FAILED", "path": DB_REL.as_posix(), "message": str(exc)}]}
    with contextlib.suppress(FileNotFoundError):
        (db.parent / "projection_failed.json").unlink()
    return {"ok": True, "command": "rebuild", "database": DB_REL.as_posix(), "projection_valid": True, "counts": {**validation["counts"], "search_rows": fts5}, "errors": []}


def add_search(connection: sqlite3.Connection, kind: str, object_id: str, title: str, body: str, keywords: str) -> None:
    connection.execute("INSERT INTO search VALUES (?,?,?,?,?)", (kind, object_id, title, body, keywords))
    for gram in ngrams(" ".join((title, body, keywords))):
        connection.execute("INSERT OR IGNORE INTO search_ngrams VALUES (?,?,?)", (kind, object_id, gram))


def ensure_projection(root: Path) -> sqlite3.Connection:
    db = root / DB_REL
    if not db.is_file() or (db.parent / "projection_failed.json").exists():
        raise KnowledgeError("local projection is missing or invalid; run rebuild")
    return sqlite3.connect(db)


def tree_command(root: Path) -> dict[str, Any]:
    registry, _ = load_authority(root)
    claims, _ = parse_claims(root, registry)
    nodes = []
    for node in registry["nodes"]:
        item = {key: node[key] for key in ("id", "name", "path", "boundary", "keywords", "migration_status")}
        item["topics"] = [
            {**{key: topic.get(key) for key in ("id", "title", "path", "summary")},
             "claim_count": sum(claim.get("topic_id") == topic.get("id") for claim in claims)}
            for topic in registry.get("topics", []) if topic.get("node_id") == node.get("id")
        ]
        nodes.append(item)
    return {"ok": True, "command": "tree", "count": len(nodes), "nodes": nodes, "truncated": False, "next_cursor": None, "errors": []}


def _json_characters(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _apply_budget(results: list[dict[str, Any]], budget: int) -> tuple[list[dict[str, Any]], int, bool]:
    kept: list[dict[str, Any]] = []
    used = 0
    for item in results:
        size = _json_characters(item)
        if kept and used + size > budget:
            return kept, used, True
        if size > budget:
            compact = dict(item)
            compact["summary"] = str(compact.get("summary", ""))[:max(0, budget // 2)]
            size = _json_characters(compact)
            item = compact
        kept.append(item)
        used += size
    return kept, used, False


def query_command(root: Path, query: str, level: int, limit: int, cursor: int, permission: str,
                  node: str | None = None, topic: str | None = None) -> dict[str, Any]:
    maximum = {1: 5, 2: 12, 3: 3}[level]
    limit = min(max(1, limit), maximum)
    connection = ensure_projection(root)
    normalized = normalize_text(query)
    if not normalized:
        raise KnowledgeError("query must not be empty")
    tokens = normalized.split()
    fts_query = " AND ".join(f'"{token.replace(chr(34), chr(34)*2)}"' for token in tokens)
    kinds = {1: ("node", "topic"), 2: ("claim",), 3: ("claim",)}[level]
    placeholders = ",".join("?" for _ in kinds)
    fetch_limit = max(limit + 1, 100)
    rows = connection.execute(f"SELECT kind, object_id, title, snippet(search, 3, '', '', '…', 24), bm25(search) FROM search WHERE search MATCH ? AND kind IN ({placeholders}) ORDER BY bm25(search), kind, object_id LIMIT ?", (fts_query, *kinds, fetch_limit)).fetchall()
    used_ngram_fallback = False
    if not rows:
        used_ngram_fallback = True
        grams = ngrams(query)
        if grams:
            rows = connection.execute(f"SELECT s.kind,s.object_id,s.title,substr(s.body,1,500),-count(*) FROM search_ngrams n JOIN search s ON s.kind=n.kind AND s.object_id=n.object_id WHERE n.gram IN ({','.join('?' for _ in grams)}) AND s.kind IN ({placeholders}) GROUP BY s.kind,s.object_id ORDER BY count(*) DESC,s.kind,s.object_id LIMIT ?", (*grams, *kinds, fetch_limit)).fetchall()
    allowed = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}
    results = []
    for kind, object_id, title, snippet, score in rows:
        if used_ngram_fallback and -float(score) < 2:
            continue
        object_permission = "internal"
        if kind == "topic":
            object_permission = connection.execute("SELECT permission FROM topics WHERE id=?", (object_id,)).fetchone()[0]
        elif kind == "claim":
            object_permission = connection.execute("SELECT permission FROM claims WHERE id=?", (object_id,)).fetchone()[0]
        if allowed[object_permission] < allowed[permission]:
            continue
        if kind == "claim":
            claim_meta = connection.execute("SELECT node_id,topic_id,lifecycle,confirmation,conflict FROM claims WHERE id=?", (object_id,)).fetchone()
            if claim_meta[2] != "active" or (node and claim_meta[0] != node) or (topic and claim_meta[1] != topic):
                continue
            item = {"kind": kind, "id": object_id, "node_id": claim_meta[0], "topic_id": claim_meta[1], "title": title,
                    "summary": snippet[:500], "lifecycle": claim_meta[2], "confirmation": claim_meta[3],
                    "conflict": claim_meta[4], "score": score, "permission": object_permission}
        else:
            if node and object_id != node:
                if kind != "topic" or connection.execute("SELECT node_id FROM topics WHERE id=?", (object_id,)).fetchone()[0] != node:
                    continue
            if topic and object_id != topic:
                continue
            item = {"kind": kind, "id": object_id, "title": title, "summary": snippet[:500], "score": score, "permission": object_permission}
            if kind == "topic":
                item["node_id"] = connection.execute("SELECT node_id FROM topics WHERE id=?", (object_id,)).fetchone()[0]
        results.append(item)
    visible = results[cursor:cursor + limit + 1]
    count_truncated = len(visible) > limit
    visible = visible[:limit]
    visible, used, budget_truncated = _apply_budget(visible, QUERY_BUDGETS[level])
    connection.close()
    truncated = count_truncated or budget_truncated or cursor + len(visible) < len(results)
    return {"ok": True, "command": "query", "query": query, "level": level, "count": len(visible), "results": visible,
            "used_characters": used, "budget": QUERY_BUDGETS[level], "truncated": truncated,
            "next_cursor": cursor + len(visible) if truncated and visible else None,
            "scope_note": "Local deterministic projection only; permission and lifecycle filters were applied before pagination. A limited result is not proof of repository-wide absence.", "errors": []}


def _claim_summary(statement: str, limit: int = 500) -> dict[str, Any]:
    boundary_marker = "#### 适用边界"
    assertion, _, boundary = statement.partition(boundary_marker)
    assertion = assertion.strip()
    boundary = boundary.strip()
    full = assertion + (("\n\n" + boundary_marker + "\n\n" + boundary) if boundary else "")
    if len(full) <= limit:
        return {"summary": full, "assertion": assertion, "safety_boundary": boundary or None,
                "summary_truncated": False, "truncated_sections": [], "full_claim_requires_l3": False}
    # Safety boundaries are mandatory. Trim the assertion first and report every local truncation.
    boundary_budget = min(len(boundary), max(120, limit // 2)) if boundary else 0
    assertion_budget = max(80, limit - boundary_budget - (len(boundary_marker) + 4 if boundary else 0))
    compact_assertion = assertion[:assertion_budget].rstrip()
    compact_boundary = boundary[:boundary_budget].rstrip()
    sections = []
    if len(compact_assertion) < len(assertion): sections.append("assertion")
    if len(compact_boundary) < len(boundary): sections.append("safety_boundary")
    summary = compact_assertion + (("\n\n" + boundary_marker + "\n\n" + compact_boundary) if boundary else "")
    return {"summary": summary, "assertion": compact_assertion, "safety_boundary": compact_boundary or None,
            "summary_truncated": True, "truncated_sections": sections, "full_claim_requires_l3": True}


def progressive_query_command(root: Path, instance: Instance, context_id: str, intent: str, max_level: int,
                              limit: int, permission: str, check_authority: bool, cursor: int = 0) -> dict[str, Any]:
    registry, _ = load_authority(root)
    scope = build_progressive_scope(instance.raw, registry, context_id=context_id, intent=intent, limit=limit)
    settings = instance.raw.get("retrieval", {})
    character_limit = min(12_000, max(500, int(settings.get("max_characters", 6_000))))
    topic_items = [{key: topic.get(key) for key in ("id", "node_id", "title", "summary", "path", "permission")}
                   for topic in scope["topics"]]
    node_items = [{key: node.get(key) for key in ("id", "name", "boundary")}
                  for node in scope["nodes"]]
    claim_items: list[dict[str, Any]] = []
    claims_truncated = False
    next_cursor: int | None = None
    if max_level >= 2:
        connection = ensure_projection(root)
        rank = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}
        all_claims: list[dict[str, Any]] = []
        for topic in scope["topics"]:
            rows = connection.execute("SELECT id,node_id,topic_id,title,statement,lifecycle,confirmation,conflict,permission FROM claims WHERE topic_id=? AND lifecycle='active' ORDER BY id", (topic["id"],)).fetchall()
            for row in rows:
                if rank[row[8]] < rank[permission]:
                    continue
                all_claims.append({"kind": "claim", "id": row[0], "node_id": row[1], "topic_id": row[2], "title": row[3],
                                   **_claim_summary(row[4]), "lifecycle": row[5], "governance_confirmation": row[6],
                                   "confirmation": row[6], "conflict": row[7], "permission": row[8]})
        evidence_rows = connection.execute("SELECT claim_id,support_type,evidence_kind FROM evidence").fetchall()
        evidence_by_claim: dict[str, list[tuple[str, str]]] = {}
        for claim_id_value, support_type, evidence_kind in evidence_rows:
            evidence_by_claim.setdefault(claim_id_value, []).append((support_type, evidence_kind))
        for claim in all_claims:
            evidence = evidence_by_claim.get(claim["id"], [])
            kinds = sorted({kind for support, kind in evidence if support == "supports"})
            claim["evidence_strength"] = {"status": "supported" if kinds else "not_registered", "supporting_kinds": kinds,
                                          "qualifier_count": sum(support == "qualifies" for support, _ in evidence),
                                          "contradiction_count": sum(support == "contradicts" for support, _ in evidence)}
        connection.close()
        claim_limit = min(12, max(1, int(settings.get("max_claims", 6))))
        claim_items = all_claims[cursor:cursor + claim_limit]
        claims_truncated = cursor + len(claim_items) < len(all_claims)
        next_cursor = cursor + len(claim_items) if claims_truncated else None
    claim_ids = {claim["id"] for claim in claim_items}
    ref_items: list[dict[str, Any]] = []
    refs_path_value = instance.authority.get("authority_refs")
    if refs_path_value and claim_ids:
        refs_doc = read_json(root / refs_path_value)
        matching = [ref for ref in refs_doc.get("refs", []) if claim_ids.intersection(ref.get("claim_ids", []))]
        requested_roles = set(scope["route"].get("verification_roles", [])) if max_level >= 3 else set()
        if requested_roles:
            matching = [ref for ref in matching if ref.get("role") in requested_roles]
        observations = observe_authority_refs(root, matching) if check_authority else matching
        blocked_ids = set().union(*(set(ref.get("claim_ids", [])) for ref in observations if ref.get("status") in {"invalidated", "missing", "invalid_ref", "working_observation"}), set())
        if blocked_ids:
            claim_items = [claim for claim in claim_items if claim["id"] not in blocked_ids]
            claim_ids = {claim["id"] for claim in claim_items}
            observations = [ref for ref in observations if claim_ids.intersection(ref.get("claim_ids", []))]
        ref_items = [{key: ref.get(key) for key in ("id", "path", "locator", "role", "baseline_state", "change_policy", "status", "baseline_status", "working_tree_status", "effective_status", "supports_fact_classes", "claim_ids") if key in ref}
                     for ref in observations]
    minimum_files = list(dict.fromkeys(
        [topic["path"] for topic in topic_items]
        + ([ref["path"] for ref in ref_items if ref.get("effective_status", ref.get("status", "current")) in {"current", "pending_review"}] if max_level >= 3 else [])
    ))
    payload = {
        "ok": True, "command": "progressive-query", "context": {key: scope["context"].get(key) for key in ("id", "lifecycle", "goal", "current_recovery")},
        "intent": scope["route"].get("id"), "query": intent, "max_level": max_level,
        "retrieval_strategy": scope["retrieval_strategy"], "candidate_topics": scope["candidate_topics"],
        "confidence": scope["confidence"], "margin": scope["margin"], "failure_type": None,
        "nodes": node_items, "topics": topic_items, "claims": claim_items,
        "escalate_to_l3": bool(scope["route"].get("escalate_to_l3", False)),
        "authority_refs": ref_items, "minimum_files": minimum_files,
        "capabilities": scope["route"].get("capabilities", {"read_knowledge": True, "write": False}),
        "read_only": True, "operation_authorized": False,
        "truncated": scope["truncated"] or claims_truncated, "next_cursor": next_cursor, "errors": [],
        "summary_truncated": any(claim.get("summary_truncated", False) for claim in claim_items),
        "truncated_claims": [{"id": claim["id"], "sections": claim.get("truncated_sections", [])} for claim in claim_items if claim.get("summary_truncated")],
        "warnings": [f"authority pending review: {ref.get('path')}" for ref in ref_items if ref.get("effective_status") == "pending_review"],
        "budget": character_limit,
        "scope_note": "Context-scoped explicit route or bounded metadata retrieval only; no full knowledge document or unregistered authority file was read. This is a read-only retrieval result, not operation authorization.",
    }
    if scope["route"].get("result_profile") == "production_progress":
        payload["durable_baseline"] = {"claims": [{"id": claim["id"], "title": claim["title"]} for claim in claim_items], "status": "historically_verified"}
        payload["current_recovery"] = {"path": payload["context"].get("current_recovery"), "status": "requires_memory_read"}
        payload["working_observations"] = []
        payload["staleness"] = {"target_rechecked": False, "still_current": "unknown", "recheck_required": True}
    if _json_characters(payload) > character_limit:
        payload["claims"] = [{key: claim.get(key) for key in ("id", "node_id", "topic_id", "title", "confirmation", "conflict")} for claim in claim_items]
        payload["context"].pop("goal", None)
        payload["nodes"] = [{key: node.get(key) for key in ("id", "name")} for node in node_items]
        payload["topics"] = [{key: topic.get(key) for key in ("id", "node_id", "title", "path")} for topic in topic_items]
        payload["authority_refs"] = [{key: ref.get(key) for key in ("id", "path", "role", "status")} for ref in ref_items]
        payload["truncated"] = True
    while payload["candidate_topics"] and _json_characters(payload) + 32 > character_limit:
        payload["candidate_topics"].pop()
        payload["truncated"] = True
    while payload["claims"] and _json_characters(payload) + 32 > character_limit:
        payload["claims"].pop()
        payload["truncated"] = True
        payload["next_cursor"] = cursor + len(payload["claims"])
    while payload["authority_refs"] and _json_characters(payload) + 32 > character_limit:
        payload["authority_refs"].pop()
        payload["truncated"] = True
    if _json_characters(payload) + 32 > character_limit:
        payload["scope_note"] = "Bounded read-only route; no operation authorization."
        payload["query"] = str(payload["query"])[:120]
        payload["truncated"] = True
    payload["used_characters"] = 0
    for _ in range(4):
        payload["used_characters"] = _json_characters(payload)
    if payload["used_characters"] > character_limit:
        raise RetrievalError(f"response budget too small for mandatory progressive-query metadata: {character_limit}")
    return payload


def show_claim(root: Path, claim_id: str, evidence_limit: int, cursor: int, permission: str) -> dict[str, Any]:
    if not ID_RE["claim"].fullmatch(claim_id):
        raise KnowledgeError("invalid claim ID")
    connection = ensure_projection(root)
    connection.row_factory = sqlite3.Row
    claim = connection.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not claim:
        connection.close()
        raise KnowledgeError(f"claim not found: {claim_id}")
    rank = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}
    if rank[claim["permission"]] < rank[permission]:
        connection.close()
        raise KnowledgeError("claim is not available at requested permission")
    if claim["lifecycle"] != "active":
        connection.close()
        raise KnowledgeError("claim is not active; explicit audit access is not available through default show-claim")
    rows_all = connection.execute("SELECT event_id,source_id,source_family_id,locator,support_type,evidence_kind,summary,permission,sensitivity,created_at FROM evidence WHERE claim_id=? ORDER BY CASE support_type WHEN 'contradicts' THEN 0 WHEN 'qualifies' THEN 1 ELSE 2 END, CASE WHEN evidence_kind LIKE '%outcome%' THEN 0 WHEN evidence_kind LIKE '%practice%' THEN 1 ELSE 2 END, created_at DESC,event_id", (claim_id,)).fetchall()
    visible_rows = [row for row in rows_all if rank[row["permission"]] >= rank[permission]]
    total = len(visible_rows)
    rows = visible_rows[cursor:cursor + min(evidence_limit, 10) + 1]
    evidence = []
    for row in rows:
        if rank[row["permission"]] < rank[permission]:
            continue
        item = dict(row)
        if item["sensitivity"] == "restricted":
            item["summary"] = None
            item["existence_only"] = True
        evidence.append(item)
    family_count = len({row["source_family_id"] for row in visible_rows})
    source_count = len({row["source_id"] for row in visible_rows})
    support_counts = {kind: sum(1 for row in visible_rows if row["support_type"] == kind) for kind in sorted(SUPPORT_TYPES)}
    evidence_status = evidence_status_for(visible_rows)
    connection.close()
    limit = min(evidence_limit, 10)
    truncated = len(evidence) > limit
    page = evidence[:limit]
    used = _json_characters(page)
    return {"ok": True, "command": "show-claim", "claim": dict(claim), "evidence_total": total,
            "evidence_visibility": "visible_count_only", "source_count": source_count, "source_family_count": family_count,
            "support_type_counts": support_counts, "evidence_status": evidence_status, "evidence": page,
            "used_characters": used, "budget": 20_000, "truncated": truncated,
            "next_cursor": cursor + limit if truncated else None, "errors": []}


def ingestion_amplification(inputs: int, new_sources: int, new_evidence: int, new_claims: int, markdown_characters: int) -> dict[str, Any]:
    denominator = max(1, inputs)
    return {"input_count": inputs, "new_source_count": new_sources, "new_evidence_count": new_evidence,
            "new_claim_count": new_claims, "knowledge_markdown_character_change": markdown_characters,
            "source_amplification": new_sources / denominator, "evidence_amplification": new_evidence / denominator,
            "claim_amplification": new_claims / denominator, "markdown_amplification": markdown_characters / denominator}


def evidence_status_for(rows: Iterable[Any]) -> str:
    items = list(rows)
    if not items:
        return "none"
    supports = [row for row in items if row["support_type"] == "supports"]
    contradicts = [row for row in items if row["support_type"] == "contradicts"]
    if contradicts:
        return "mixed"
    families = {row["source_family_id"] for row in supports}
    kinds = {row["evidence_kind"] for row in supports}
    if any("outcome" in kind for kind in kinds):
        return "outcome_supported"
    if any("practice" in kind for kind in kinds):
        return "practice_supported"
    if len(families) > 1:
        return "multi_source"
    if len(supports) > 1:
        return "repeated_same_context"
    return "single_source"


def atomic_write(target: Path, data: bytes, expected_hash: str | None) -> None:
    if file_hash(target) != expected_hash:
        raise KnowledgeError(f"target hash changed: {target.as_posix()}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if file_hash(target) != expected_hash:
            raise KnowledgeError(f"target hash changed before replace: {target.as_posix()}")
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(temporary).unlink()


class WriteLock:
    def __init__(self, root: Path, operation_id: str):
        self.path = root / LOCAL_REL / "write.lock"
        self.operation_id = operation_id

    def __enter__(self) -> "WriteLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_json({"pid": os.getpid(), "operation_id": self.operation_id, "started_at": dt.datetime.now().astimezone().isoformat()}) + "\n"
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            try:
                existing = read_json(self.path)
                pid = int(existing.get("pid", -1))
                os.kill(pid, 0)
            except (KnowledgeError, ValueError, TypeError, ProcessLookupError, PermissionError, OSError):
                raise KnowledgeError(f"stale write lock requires explicit removal after inspection: {self.path.as_posix()}") from exc
            raise KnowledgeError(f"knowledge write lock held by PID {pid}") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return self

    def __exit__(self, *args: Any) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def transaction_dirs(root: Path) -> list[Path]:
    directory = root / LOCAL_REL / "transactions"
    return sorted(path for path in directory.glob("*") if path.is_dir()) if directory.exists() else []


def transactional_replace(root: Path, command: str, writes: dict[str, bytes], validate_staged: Any | None = None) -> list[str]:
    """Replace one or more authority files with rollback on any local failure.

    Staged files and backups stay in the local transaction directory. Existing
    unfinished transactions block the operation. This helper intentionally does
    not rebuild: callers validate authority, then call rebuild and mark any
    projection failure without reverting validated authority.
    """
    unfinished = transaction_dirs(root)
    if unfinished:
        raise KnowledgeError(f"unfinished transaction blocks write: {unfinished[0].name}")
    operation_id = f"op_{new_ulid()}"
    directory = root / LOCAL_REL / "transactions" / operation_id
    backup_dir = directory / "backup"
    backup_dir.mkdir(parents=True)
    normalized: list[tuple[str, Path, Path, bytes, str | None]] = []
    for rel, data in sorted(writes.items()):
        error = _portable_relative_path(rel)
        if error or rel.startswith(".local/"):
            raise KnowledgeError(f"invalid authority target {rel}: {error or 'local projection is not authority'}")
        target = (root / Path(*PurePosixPath(rel).parts)).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as exc:
            raise KnowledgeError(f"target escapes project: {rel}") from exc
        staged = target.with_name(f".{target.name}.{operation_id}.tmp")
        normalized.append((rel, target, staged, data, file_hash(target)))
    plan_path = directory / "plan.json"
    plan: dict[str, Any] = {"schema_version": 1, "operation_id": operation_id, "command": command, "stage": "planned", "writes": [{"path": rel, "staged_path": relpath(root, staged), "expected_hash": digest, "new_hash": sha256_bytes(data)} for rel, _, staged, data, digest in normalized], "failure": None}
    atomic_write(plan_path, (canonical_json(plan) + "\n").encode(), None)
    try:
        for index, (rel, target, staged, data, digest) in enumerate(normalized):
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(staged, data, None)
            if file_hash(staged) != sha256_bytes(data):
                raise KnowledgeError(f"staged hash mismatch: {rel}")
            if target.exists():
                atomic_write(backup_dir / str(index), target.read_bytes(), None)
        plan["stage"] = "staged"
        atomic_write(plan_path, (canonical_json(plan) + "\n").encode(), file_hash(plan_path))
        if validate_staged:
            validate_staged({rel: staged for rel, _, staged, _, _ in normalized})
        with WriteLock(root, operation_id):
            for _, target, _, _, digest in normalized:
                if file_hash(target) != digest:
                    raise KnowledgeError(f"target hash changed before transaction: {target.as_posix()}")
            replaced: list[int] = []
            try:
                for index, (_, target, staged, _, _) in enumerate(normalized):
                    os.replace(staged, target)
                    replaced.append(index)
            except Exception:
                for index in reversed(replaced):
                    _, target, _, _, old_digest = normalized[index]
                    backup = backup_dir / str(index)
                    if old_digest is None:
                        with contextlib.suppress(FileNotFoundError):
                            target.unlink()
                    elif backup.exists():
                        os.replace(backup, target)
                raise
        plan["stage"] = "authority_replaced"
        atomic_write(plan_path, (canonical_json(plan) + "\n").encode(), file_hash(plan_path))
        # Completed local transaction state is disposable; only failures remain.
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()
        directory.rmdir()
        return [rel for rel, _, _, _, _ in normalized]
    except Exception as exc:
        for _, _, staged, _, _ in normalized:
            with contextlib.suppress(FileNotFoundError):
                staged.unlink()
        plan["stage"] = "failed"
        plan["failure"] = str(exc)
        atomic_write(plan_path, (canonical_json(plan) + "\n").encode(), file_hash(plan_path))
        raise


def inspect_transactions(root: Path) -> dict[str, Any]:
    transactions = []
    for directory in transaction_dirs(root):
        plan = read_json(directory / "plan.json")
        transactions.append({"operation_id": directory.name, "stage": plan.get("stage"), "command": plan.get("command"), "failure": plan.get("failure")})
    return {"ok": True, "command": "inspect-transaction", "count": len(transactions), "transactions": transactions, "errors": []}


def recover_transaction(root: Path, operation_id: str) -> dict[str, Any]:
    directory = root / LOCAL_REL / "transactions" / operation_id
    plan = read_json(directory / "plan.json")
    # Recovery is deliberately conservative: authority replacement is never guessed.
    if plan.get("stage") == "authority_replaced":
        result = rebuild(root)
        if result["ok"]:
            plan["stage"] = "complete"
            atomic_write(directory / "plan.json", (canonical_json(plan) + "\n").encode(), file_hash(directory / "plan.json"))
        return {**result, "command": "recover", "operation_id": operation_id}
    raise KnowledgeError("transaction cannot be automatically recovered; use rollback after inspection")


def rollback_transaction(root: Path, operation_id: str) -> dict[str, Any]:
    directory = root / LOCAL_REL / "transactions" / operation_id
    plan = read_json(directory / "plan.json")
    if plan.get("stage") not in {"planned", "staged", "failed"}:
        raise KnowledgeError("authority may have been replaced; rollback is unsafe")
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    directory.rmdir()
    return {"ok": True, "command": "rollback", "operation_id": operation_id, "changed_files": [], "errors": []}


def abandon_transaction(root: Path, operation_id: str) -> dict[str, Any]:
    directory = root / LOCAL_REL / "transactions" / operation_id
    plan = read_json(directory / "plan.json")
    if plan.get("stage") == "authority_replaced":
        raise KnowledgeError("authority was replaced; recover projection instead of abandoning")
    for staged in plan.get("writes", []):
        staged_path = staged.get("staged_path")
        if staged_path:
            with contextlib.suppress(FileNotFoundError):
                (root / staged_path).unlink()
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_file(): path.unlink()
        elif path.is_dir(): path.rmdir()
    directory.rmdir()
    return {"ok": True, "command": "abandon", "operation_id": operation_id, "changed_files": [], "errors": []}


def now_iso(value: str | None = None) -> str:
    if value:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise KnowledgeError("created-at must include a timezone")
        return parsed.isoformat()
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def shard_rel(category: str, actor: str, created_at: str) -> str:
    month = created_at[:7]
    return f"{STORE_REL.as_posix()}/{category}/{month}-{actor}.jsonl"


def event_identity(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Emit v2 identity for configured instances; retain v1 only for unconfigured test/legacy roots."""
    try:
        identities = load_instance(root).identities
    except (InstanceError, KeyError):
        return {"schema_version": 1, "actor": args.actor, "performed_by": args.performed_by}
    writer = identities["writer"]["id"]
    if getattr(args, "actor", writer) != writer:
        raise KnowledgeError(f"mutation writer must be configured writer: {writer}")
    return {"schema_version": 2, "principal": identities["principal"]["id"],
            "executor": identities["executor"]["id"], "workspace": identities["workspace"]["id"],
            "writer": writer}


def append_jsonl_bytes(path: Path, event: dict[str, Any]) -> bytes:
    old = path.read_bytes() if path.exists() else b""
    if old and not old.endswith(b"\n"):
        raise KnowledgeError(f"JSONL does not end with LF: {path.as_posix()}")
    return old + (canonical_json(event) + "\n").encode("utf-8")


def validate_planned_writes(root: Path, writes: dict[str, bytes]) -> None:
    """Validate a complete authority overlay before transactional replacement."""
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
        knowledge_rel = _knowledge_rel(root)
        shutil.copytree(root / knowledge_rel, staging / knowledge_rel)
        shutil.copytree(root / STORE_REL, staging / STORE_REL)
        instance_config = root / "project-intelligence.json"
        if instance_config.is_file():
            shutil.copy2(instance_config, staging / instance_config.name)
        for rel, data in writes.items():
            target = staging / Path(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        result = validate(staging)
        if not result["ok"]:
            first = result["errors"][0]
            raise KnowledgeError(f"staged authority invalid [{first['code']}] {first['path']}: {first['message']}")


def mutation_result(root: Path, command: str, writes: dict[str, bytes], apply: bool, details: dict[str, Any]) -> dict[str, Any]:
    validate_planned_writes(root, writes)
    changed = sorted(writes)
    if not apply:
        return {"ok": True, "command": command, "applied": False, "dry_run": True, "changed_files": changed, **details, "errors": []}
    replaced = transactional_replace(root, command, writes, lambda _: validate_planned_writes(root, writes))
    projection = rebuild(root)
    return {"ok": projection["ok"], "command": command, "applied": True, "dry_run": False,
            "changed_files": replaced, **details, "validation": validate(root), "projection": projection,
            "git_status": git_status(root), "errors": projection.get("errors", [])}


def ensure_actor(root: Path, actor: str, review_required: bool = False) -> None:
    _, actors = load_authority(root)
    record = next((item for item in actors.get("actors", []) if item.get("id") == actor), None)
    if not record:
        raise KnowledgeError(f"unknown actor: {actor}")
    if review_required and not (set(record.get("roles", [])) & AUTHORIZED_REVIEW_ROLES):
        raise KnowledgeError(f"actor is not authorized for semantic review: {actor}")


def append_semantic_event(root: Path, args: argparse.Namespace, command: str, event_type: str,
                          fields: dict[str, Any], review_required: bool = True) -> dict[str, Any]:
    ensure_actor(root, args.actor, review_required=review_required)
    created_at = now_iso(args.created_at)
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": event_type,
             "created_at": created_at, **fields}
    rel = shard_rel("proposals", args.actor, created_at)
    writes = {rel: append_jsonl_bytes(root / rel, event)}
    return mutation_result(root, command, writes, args.apply, {"event_id": event["event_id"], **fields})


def resolve_proposal_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor, review_required=True)
    created = [event for category, _, _, event in iter_jsonl(root) if category == "proposals" and event.get("event_type") == "proposal_created" and event.get("proposal_id") == args.proposal_id]
    resolved = [event for category, _, _, event in iter_jsonl(root) if category == "proposals" and event.get("event_type") == "proposal_resolved" and event.get("proposal_id") == args.proposal_id]
    if not created or resolved:
        raise KnowledgeError("proposal is missing or already resolved")
    return append_semantic_event(root, args, "resolve-proposal", "proposal_resolved",
                                 {"proposal_id": args.proposal_id, "resolution": args.resolution,
                                  "resolution_summary": args.reason})


def retract_evidence_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor)
    target = next((event for category, _, _, event in iter_jsonl(root) if category == "evidence" and event.get("event_type") == "evidence_added" and event.get("event_id") == args.event_id), None)
    if not target:
        raise KnowledgeError("evidence event not found")
    created_at = now_iso(args.created_at)
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": "evidence_retracted",
             "target_event_id": args.event_id,
             "claim_id": target["claim_id"], "reason": args.reason, "created_at": created_at}
    rel = shard_rel("evidence", args.actor, created_at)
    return mutation_result(root, "retract-evidence", {rel: append_jsonl_bytes(root / rel, event)}, args.apply,
                           {"event_id": event["event_id"], "target_event_id": args.event_id, "claim_id": target["claim_id"]})


def revise_claim_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor, review_required=True)
    registry, _ = load_authority(root)
    claim = next((item for item in parse_claims(root, registry)[0] if item["id"] == args.claim_id), None)
    if not claim:
        raise KnowledgeError("claim not found")
    old = (root / claim["path"]).read_text(encoding="utf-8")
    pattern = re.compile(rf"<!--\s*CLAIM:START\s+{re.escape(args.claim_id)}\s*-->.*?<!--\s*CLAIM:END\s+{re.escape(args.claim_id)}\s*-->", re.S)
    replacement = claim_markdown(args.title or claim["title"], args.claim_id, args.statement, args.boundary).strip()
    new = pattern.sub(replacement, old, count=1)
    created_at = now_iso(args.created_at)
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": "claim_revised",
             "claim_id": args.claim_id, "before_hash": claim["content_hash"],
             "after_hash": content_hash(replacement), "semantic_declaration": args.semantic_declaration,
             "reason": args.reason, "created_at": created_at}
    rel = shard_rel("proposals", args.actor, created_at)
    writes = {claim["path"]: new.encode("utf-8"), rel: append_jsonl_bytes(root / rel, event)}
    return mutation_result(root, "revise-claim", writes, args.apply, {"claim_id": args.claim_id, "event_id": event["event_id"]})


def register_source_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor)
    source_path = args.source_path
    error = _portable_relative_path(source_path)
    path = root / Path(*PurePosixPath(source_path).parts)
    if error or not path.is_file():
        raise KnowledgeError(f"invalid source path: {error or 'file missing'}")
    digest = sha256_bytes(path.read_bytes())
    existing: list[dict[str, Any]] = []
    for category, _, _, event in iter_jsonl(root):
        if category == "sources" and event.get("event_type") == "source_registered":
            existing.append(event)
    identical = next((event for event in existing if event.get("content_hash") == digest), None)
    if identical:
        return {"ok": True, "command": "register-source", "applied": False, "registration_result": "existing_source",
                "source_id": identical["source_id"], "source_family_id": identical["source_family_id"],
                "amplification": ingestion_amplification(1, 0, 0, 0, 0), "changed_files": [], "errors": []}
    family_id = args.family_id or new_id("family")
    if not ID_RE["family"].fullmatch(family_id):
        raise KnowledgeError("invalid source family ID")
    same_representation = next((event for event in existing if event.get("source_family_id") == family_id and event.get("representation") == args.representation), None)
    result = args.registration_result
    if same_representation and result not in {"new_version", "needs_review"}:
        raise KnowledgeError("family representation already exists; choose new_version or needs_review")
    source_id, created_at = new_id("source"), now_iso(args.created_at)
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": "source_registered",
             "source_id": source_id,
             "source_family_id": family_id, "title": args.title, "representation": args.representation,
             "source_path": source_path, "content_hash": digest, "registration_result": result,
             "permission": args.permission, "created_at": created_at}
    if args.external_alias:
        event["external_alias"] = args.external_alias
    rel = shard_rel("sources", args.actor, created_at)
    writes = {rel: append_jsonl_bytes(root / rel, event)}
    return mutation_result(root, "register-source", writes, args.apply,
                           {"registration_result": result, "source_id": source_id, "source_family_id": family_id, "event_id": event["event_id"],
                            "amplification": ingestion_amplification(1, 1, 0, 0, 0)})


def claim_markdown(title: str, claim_id: str, statement: str, boundary: str) -> str:
    return (f"<!-- CLAIM:START {claim_id} -->\n\n### {title}\n\n{statement.strip()}\n\n"
            f"#### 适用边界\n\n{boundary.strip()}\n\n<!-- CLAIM:END {claim_id} -->\n")


def new_claim_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor)
    registry, _ = load_authority(root)
    node = next((item for item in registry["nodes"] if item["id"] == args.node), None)
    if not node:
        raise KnowledgeError(f"node not found: {args.node}")
    topic = next((item for item in registry.get("topics", []) if item["id"] == args.topic_id), None)
    topic_path = args.topic_path or (topic and topic["path"])
    if not topic_path:
        raise KnowledgeError("topic-path is required for a new topic")
    error = _portable_relative_path(topic_path, _knowledge_rel(root).as_posix())
    if error or not topic_path.endswith(".md"):
        raise KnowledgeError(f"invalid topic path: {error or 'must be Markdown'}")
    if topic and (topic["node_id"] != args.node or topic["path"] != topic_path):
        raise KnowledgeError("topic identity conflicts with registry")
    claims, findings = parse_claims(root, registry)
    if findings:
        raise KnowledgeError("existing claim authority is invalid")
    candidate = f"{args.title}\n{args.statement}\n{args.boundary}"
    normalized = normalize_text(candidate)
    for claim in claims:
        ratio = difflib.SequenceMatcher(None, normalized, normalize_text(claim["statement"])).ratio()
        if content_hash(candidate) == claim["content_hash"] or ratio >= 0.88:
            raise KnowledgeError(f"claim is duplicate or highly similar to {claim['id']}; use add-evidence or revise workflow")
    if not topic and args.duplicate_resolution != "create_distinct_with_boundary":
        raise KnowledgeError("new topic/claim requires --duplicate-resolution create_distinct_with_boundary")
    claim_id = new_id("claim")
    block = claim_markdown(args.title, claim_id, args.statement, args.boundary)
    target = root / topic_path
    if topic:
        text = target.read_text(encoding="utf-8")
        new_text = text.rstrip() + "\n\n" + block
    else:
        topic = {"id": args.topic_id, "node_id": args.node, "title": args.topic_title or args.title,
                 "path": topic_path, "summary": args.topic_summary, "keywords": args.keywords,
                 "permission": args.permission}
        registry["topics"].append(topic)
        new_text = f"# {topic['title']}\n\n{topic['summary']}\n\n{block}"
    node["migration_status"] = "pilot"
    writes = {REGISTRY_REL.as_posix(): (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
              topic_path: new_text.encode("utf-8")}
    return mutation_result(root, "new-claim", writes, args.apply,
                           {"claim_id": claim_id, "node_id": args.node, "topic_id": args.topic_id,
                            "amplification": ingestion_amplification(1, 0, 0, 1, len(block))})


def add_evidence_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor)
    registry, _ = load_authority(root)
    claims, findings = parse_claims(root, registry)
    if findings or args.claim_id not in {claim["id"] for claim in claims}:
        raise KnowledgeError(f"claim not found or authority invalid: {args.claim_id}")
    sources = {event.get("source_id") for category, _, _, event in iter_jsonl(root)
               if category == "sources" and event.get("event_type") == "source_registered"}
    if args.source_id not in sources:
        raise KnowledgeError(f"source not found: {args.source_id}")
    if args.sensitivity == "restricted" and args.summary is not None:
        raise KnowledgeError("restricted evidence must omit summary")
    created_at = now_iso(args.created_at)
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": "evidence_added",
             "claim_id": args.claim_id,
             "source_id": args.source_id, "locator": args.locator, "support_type": args.support_type,
             "speaker_role": args.speaker_role, "evidence_kind": args.evidence_kind,
             "summary": args.summary, "permission": args.permission, "sensitivity": args.sensitivity,
             "created_at": created_at}
    rel = shard_rel("evidence", args.actor, created_at)
    writes = {rel: append_jsonl_bytes(root / rel, event)}
    return mutation_result(root, "add-evidence", writes, args.apply,
                           {"event_id": event["event_id"], "claim_id": args.claim_id, "source_id": args.source_id,
                            "amplification": ingestion_amplification(1, 0, 1, 0, 0)})


def propose_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    ensure_actor(root, args.actor)
    created_at, proposal_id = now_iso(args.created_at), new_id("proposal")
    event = {**event_identity(root, args), "event_id": new_id("event"), "event_type": "proposal_created",
             "proposal_id": proposal_id,
             "proposal_type": args.proposal_type, "target_id": args.target_id, "summary": args.summary,
             "rationale": args.rationale, "status": "open", "created_at": created_at}
    rel = shard_rel("proposals", args.actor, created_at)
    writes = {rel: append_jsonl_bytes(root / rel, event)}
    return mutation_result(root, "propose", writes, args.apply, {"proposal_id": proposal_id, "event_id": event["event_id"]})


def _load_bundle(root: Path, bundle_id: str) -> dict[str, Any]:
    path, _, _ = bundle_paths(root, bundle_id)
    value = read_json(path)
    verify_bundle(value)
    return value


def capture_command(root: Path, args: argparse.Namespace, instance: Instance) -> dict[str, Any]:
    request = read_json(Path(args.manifest))
    return capture_bundle_draft(root, request, instance.identities)


def bundle_create_command(root: Path, args: argparse.Namespace, instance: Instance) -> dict[str, Any]:
    manifest = read_json(root / args.manifest)
    bundle = build_bundle(root, manifest, instance.identities)
    path, _, _ = bundle_paths(root, bundle["bundle_id"])
    writes = {relpath(root, path): bundle_json(bundle)}
    if not args.apply:
        return {"ok": True, "command": "bundle-create", "bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"], "applied": False, "dry_run": True, "changed_files": sorted(writes), "bundle": bundle, "next_step": f"Re-run bundle-create --manifest {args.manifest} --apply. This creates the immutable Bundle file only; it does not apply knowledge changes.", "errors": []}
    changed = transactional_replace(root, "bundle-create", writes)
    return {"ok": True, "command": "bundle-create", "bundle_id": bundle["bundle_id"], "content_hash": bundle["content_hash"], "applied": True, "dry_run": False, "changed_files": changed, "next_step": f"Inspect {bundle['bundle_id']}, then obtain exact-hash approval before bundle-approve. Knowledge changes are not yet applied.", "errors": []}


def bundle_approve_command(root: Path, args: argparse.Namespace, instance: Instance) -> dict[str, Any]:
    bundle = _load_bundle(root, args.bundle_id)
    value = approval(bundle, instance.identities["principal"]["id"])
    _, path, _ = bundle_paths(root, args.bundle_id)
    writes = {relpath(root, path): bundle_json(value)}
    if not args.apply:
        return {"ok": True, "command": "bundle-approve", "bundle_id": args.bundle_id, "content_hash": bundle["content_hash"], "applied": False, "dry_run": True, "changed_files": sorted(writes), "approval": value, "errors": []}
    changed = transactional_replace(root, "bundle-approve", writes)
    return {"ok": True, "command": "bundle-approve", "bundle_id": args.bundle_id, "applied": True, "dry_run": False, "changed_files": changed, "errors": []}


def bundle_apply_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    bundle = _load_bundle(root, args.bundle_id)
    _, approval_path, receipt_path = bundle_paths(root, args.bundle_id)
    approved = read_json(approval_path)
    if not args.apply:
        return {"ok": True, "command": "bundle-apply", "bundle_id": args.bundle_id, "content_hash": bundle["content_hash"], "applied": False, "dry_run": True, "changed_files": bundle["expected_changed_files"], "errors": []}
    receipt_rel = relpath(root, receipt_path)
    receipt = {"schema_version": 1, "bundle_id": args.bundle_id, "content_hash": bundle["content_hash"], "changed_files": bundle["expected_changed_files"]}
    def replace_with_receipt(target_root: Path, command: str, writes: dict[str, bytes]) -> list[str]:
        complete = {**writes, receipt_rel: bundle_json(receipt)}
        return transactional_replace(target_root, command, complete, lambda _: validate_planned_writes(target_root, writes))
    changed = apply_bundle(root, bundle, approved, replace_with_receipt)
    validation, projection = validate(root), rebuild(root)
    return {"ok": validation["ok"] and projection["ok"], "command": "bundle-apply", "bundle_id": args.bundle_id, "applied": True, "dry_run": False, "changed_files": changed, "validation": validation, "projection": projection, "git_status": git_status(root), "errors": validation["errors"] + projection.get("errors", [])}


def bundle_inspect_command(root: Path, bundle_id: str | None) -> dict[str, Any]:
    directory = root / "data/knowledge/bundles"
    ids = [bundle_id] if bundle_id else sorted(path.stem for path in directory.glob("bnd_*.json") if ".approval" not in path.name and ".applied" not in path.name)
    items = []
    for value in ids:
        bundle_path, approval_path, receipt_path = bundle_paths(root, value)
        bundle = read_json(bundle_path); verify_bundle(bundle)
        items.append({"bundle_id": value, "content_hash": bundle["content_hash"], "approved": approval_path.is_file(), "applied": receipt_path.is_file(), "expected_changed_files": bundle["expected_changed_files"]})
    return {"ok": True, "command": "bundle-inspect", "count": len(items), "bundles": items, "errors": []}


def bundle_recover_command(root: Path, bundle_id: str) -> dict[str, Any]:
    bundle = _load_bundle(root, bundle_id)
    _, _, receipt = bundle_paths(root, bundle_id)
    if not all((root / a["path"]).is_file() and file_hash(root / a["path"]) == a["new_hash"] for a in bundle["actions"]):
        raise BundleError("authority does not match applied bundle")
    projection = rebuild(root)
    return {**projection, "command": "bundle-recover", "bundle_id": bundle_id, "receipt": receipt.is_file(), "git_status": git_status(root)}


def bundle_rollback_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    bundle = _load_bundle(root, args.bundle_id)
    if not args.apply:
        return {"ok": True, "command": "bundle-rollback", "bundle_id": args.bundle_id, "applied": False, "dry_run": True, "changed_files": bundle["expected_changed_files"], "errors": []}
    changed = rollback_bundle(root, bundle, transactional_replace)
    projection = rebuild(root)
    return {"ok": projection["ok"], "command": "bundle-rollback", "bundle_id": args.bundle_id, "applied": True, "dry_run": False, "changed_files": changed, "projection": projection, "git_status": git_status(root), "errors": projection.get("errors", [])}


def claims_from_git_ref(root: Path, ref: str) -> dict[str, str]:
    check = subprocess.run(["git", "rev-parse", "--verify", ref], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check.returncode:
        raise KnowledgeError(f"base ref not found: {ref}")
    knowledge_rel = _knowledge_rel(root).as_posix()
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, knowledge_rel], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    found: dict[str, str] = {}
    for rel in listing.stdout.splitlines():
        if not rel.endswith(".md"):
            continue
        shown = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if shown.returncode:
            continue
        text, active = shown.stdout, None
        markers = sorted([(m.start(), "start", m) for m in CLAIM_START_RE.finditer(text)] + [(m.start(), "end", m) for m in CLAIM_END_RE.finditer(text)])
        for _, kind, match in markers:
            if kind == "start":
                active = (match.group(1), match.end())
            elif active and active[0] == match.group(1):
                found[active[0]] = normalize_text(text[active[1]:match.start()])
                active = None
    return found


def git_file_bytes(root: Path, ref: str, rel: str) -> bytes | None:
    shown = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return shown.stdout if shown.returncode == 0 else None


def validate_merge_command(root: Path, base: str) -> dict[str, Any]:
    authority = validate(root)
    findings = [Finding(item["code"], item["path"], item["message"]) for item in authority["errors"]]
    registry, _ = load_authority(root)
    current_claims, _ = parse_claims(root, registry)
    baseline = claims_from_git_ref(root, base)
    current_by_id = {claim["id"]: claim for claim in current_claims}
    for claim_id, base_statement in baseline.items():
        claim = current_by_id.get(claim_id)
        if claim is None:
            findings.append(Finding("MERGE_EXISTING_CLAIM_REMOVED", _knowledge_rel(root).as_posix(), f"existing claim removed since {base}: {claim_id}"))
        elif normalize_text(claim["statement"]) != base_statement:
            findings.append(Finding("MERGE_EXISTING_CLAIM_MODIFIED", claim["path"], f"existing claim changed since {base}: {claim_id}"))

    new_claims = [claim for claim in current_claims if claim["id"] not in baseline]
    for index, claim in enumerate(new_claims):
        for other in new_claims[index + 1:]:
            ratio = difflib.SequenceMatcher(None, normalize_text(claim["statement"]), normalize_text(other["statement"])).ratio()
            if ratio >= 0.88:
                findings.append(Finding("MERGE_NEW_CLAIM_SIMILAR", claim["path"], f"new claim {claim['id']} is highly similar to {other['id']}"))

    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, STORE_REL.as_posix()], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    for rel in listing.stdout.splitlines():
        if not rel.endswith(".jsonl"):
            continue
        base_bytes = git_file_bytes(root, base, rel)
        current_path = root / rel
        current_bytes = current_path.read_bytes() if current_path.is_file() else None
        if base_bytes is not None and (current_bytes is None or not current_bytes.startswith(base_bytes)):
            findings.append(Finding("MERGE_HISTORY_REWRITTEN", rel, f"historical JSONL from {base} must remain an exact prefix"))
    return report("validate-merge", findings, base=base, counts={"base_claims": len(baseline), "current_claims": len(current_claims)})


def git_status(root: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=root, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result.stdout.splitlines() if result.returncode == 0 else []


def output(payload: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif not payload.get("ok"):
        for error in payload.get("errors", []):
            print(f"ERROR [{error.get('code', 'ERROR')}] {error.get('path', '.')}: {error.get('message', '')}")
    elif payload.get("command") == "tree":
        print("OK: tree")
        print("Knowledge tree")
        for node in payload.get("nodes", []):
            print(f"{node.get('id')} — {node.get('name')}")
            for topic in node.get("topics", []):
                print(f"  └─ {topic.get('id')} — {topic.get('title')} ({topic.get('claim_count', 0)} claims)")
    elif payload.get("command") == "progressive-query":
        print(f"Context: {payload.get('context', {}).get('id')}")
        print(f"Intent: {payload.get('intent') or '(dynamic)'}")
        print(f"Strategy: {payload.get('retrieval_strategy')}")
        print("Topics: " + ", ".join(item.get("id", "") for item in payload.get("topics", [])))
        print("Claims:")
        for claim in payload.get("claims", []): print(f"  - {claim.get('id')}: {claim.get('title')}")
        print("Authority: " + (", ".join(f"{ref.get('id', ref.get('path'))}={ref.get('effective_status', ref.get('status', 'unchecked'))}" for ref in payload.get("authority_refs", [])) or "none"))
        print("Minimum files: " + (", ".join(payload.get("minimum_files", [])) or "none"))
        print(f"Escalate to L3: {str(bool(payload.get('escalate_to_l3'))).lower()}")
        print(f"Operation authorized: {str(bool(payload.get('operation_authorized'))).lower()}")
        print(f"Budget: {payload.get('used_characters', 0)}/{payload.get('budget', 0)}")
        print("Warnings: " + (", ".join(payload.get("warnings", [])) or "none"))
    elif payload.get("command") == "show-claim":
        claim = payload.get("claim", {})
        print(f"Claim: {claim.get('id')} — {claim.get('title')}")
        print(claim.get("statement", ""))
        print(f"Governance confirmation: {claim.get('confirmation')}")
        print(f"Conflict: {claim.get('conflict')}")
        print(f"Evidence strength: {payload.get('evidence_status')}")
        print(f"Evidence: {len(payload.get('evidence', []))}/{payload.get('evidence_total', 0)}")
    else:
        print(f"OK: {payload.get('command')}")
        if "count" in payload: print(f"count: {payload['count']}")
        if payload.get("next_step"): print(f"Next step: {payload['next_step']}")


def parser_build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root_default())
    parser.add_argument("--config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        child = sub.add_parser(name, **kwargs)
        child.add_argument("--format", choices=("json", "text"), default="json")
        return child

    command("validate")
    merge = command("validate-merge")
    merge.add_argument("--base", required=True)
    command("rebuild")
    command("tree")
    query = command("query")
    query.add_argument("query")
    query.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
    query.add_argument("--limit", type=int, default=5)
    query.add_argument("--cursor", type=int, default=0)
    query.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    query.add_argument("--node")
    query.add_argument("--topic")
    progressive = command("progressive-query", aliases=["query-context"])
    progressive.add_argument("--context", required=True)
    progressive.add_argument("--intent", required=True)
    progressive.add_argument("--max-level", type=int, choices=(1, 2, 3), default=2)
    progressive.add_argument("--limit", type=int, default=3)
    progressive.add_argument("--cursor", type=int, default=0)
    progressive.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    progressive.add_argument("--check-authority", action="store_true")
    show = command("show-claim")
    show.add_argument("claim_id")
    show.add_argument("--evidence-limit", type=int, default=10)
    show.add_argument("--cursor", type=int, default=0)
    show.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    def mutation(name: str) -> argparse.ArgumentParser:
        child = command(name)
        child.add_argument("--actor")
        child.add_argument("--performed-by")
        child.add_argument("--created-at")
        mode = child.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")
        return child

    source = mutation("register-source")
    source.add_argument("--source-path", required=True)
    source.add_argument("--title", required=True)
    source.add_argument("--representation", default="sanitized_markdown")
    source.add_argument("--family-id")
    source.add_argument("--external-alias")
    source.add_argument("--registration-result", choices=tuple(SOURCE_RESULTS), default="new_source")
    source.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    claim = mutation("new-claim")
    claim.add_argument("--node", required=True)
    claim.add_argument("--topic-id", required=True)
    claim.add_argument("--topic-path")
    claim.add_argument("--topic-title")
    claim.add_argument("--topic-summary", default="")
    claim.add_argument("--keywords", nargs="*", default=[])
    claim.add_argument("--title", required=True)
    claim.add_argument("--statement", required=True)
    claim.add_argument("--boundary", required=True)
    claim.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    claim.add_argument("--duplicate-resolution", choices=("add_evidence", "revise_existing", "create_distinct_with_boundary", "cancel"), default="cancel")
    evidence = mutation("add-evidence")
    evidence.add_argument("--claim-id", required=True)
    evidence.add_argument("--source-id", required=True)
    evidence.add_argument("--locator", required=True)
    evidence.add_argument("--support-type", choices=tuple(SUPPORT_TYPES), default="supports")
    evidence.add_argument("--speaker-role", default="知识主体")
    evidence.add_argument("--evidence-kind", default="practice_statement")
    evidence.add_argument("--summary")
    evidence.add_argument("--permission", choices=tuple(PERMISSIONS), default="internal")
    evidence.add_argument("--sensitivity", choices=tuple(SENSITIVITIES), default="generalized")
    proposal = mutation("propose")
    proposal.add_argument("--proposal-type", required=True)
    proposal.add_argument("--target-id", required=True)
    proposal.add_argument("--summary", required=True)
    proposal.add_argument("--rationale", required=True)
    resolve = mutation("resolve-proposal")
    resolve.add_argument("proposal_id")
    resolve.add_argument("--resolution", choices=("accepted", "rejected"), required=True)
    resolve.add_argument("--reason", required=True)
    revise = mutation("revise-claim")
    revise.add_argument("claim_id")
    revise.add_argument("--title")
    revise.add_argument("--statement", required=True)
    revise.add_argument("--boundary", required=True)
    revise.add_argument("--semantic-declaration", choices=("clarify", "correct", "narrow", "expand"), required=True)
    revise.add_argument("--reason", required=True)
    supersede = mutation("supersede-claim")
    supersede.add_argument("claim_id")
    supersede.add_argument("--replacement-claim-id", required=True)
    supersede.add_argument("--reason", required=True)
    merge_claims = mutation("merge-claims")
    merge_claims.add_argument("claim_id")
    merge_claims.add_argument("--target-claim-id", required=True)
    merge_claims.add_argument("--reason", required=True)
    retract = mutation("retract-evidence")
    retract.add_argument("event_id")
    retract.add_argument("--reason", required=True)
    confirm = mutation("confirm-claim")
    confirm.add_argument("claim_id")
    confirm.add_argument("--confirmation", choices=tuple(CONFIRMATIONS), required=True)
    confirm.add_argument("--reason", required=True)
    permission_change = mutation("change-permission")
    permission_change.add_argument("claim_id")
    permission_change.add_argument("--permission", choices=tuple(PERMISSIONS), required=True)
    permission_change.add_argument("--reason", required=True)
    capture = command("capture")
    capture.add_argument("--manifest", required=True)
    bundle_create = mutation("bundle-create")
    bundle_create.add_argument("--manifest", required=True)
    bundle_approve = mutation("bundle-approve")
    bundle_approve.add_argument("bundle_id")
    bundle_apply = mutation("bundle-apply")
    bundle_apply.add_argument("bundle_id")
    bundle_inspect = command("bundle-inspect")
    bundle_inspect.add_argument("bundle_id", nargs="?")
    bundle_recover = command("bundle-recover")
    bundle_recover.add_argument("bundle_id")
    bundle_rollback = mutation("bundle-rollback")
    bundle_rollback.add_argument("bundle_id")
    command("inspect-transaction")
    recover = command("recover")
    recover.add_argument("operation_id")
    rollback = command("rollback")
    rollback.add_argument("operation_id")
    abandon = command("abandon")
    abandon.add_argument("operation_id")
    identity = command("new-id")
    identity.add_argument("kind", choices=tuple(ID_RE))
    return parser


def _normalize_global_options(argv: list[str]) -> list[str]:
    """Allow the global --root option before or after the subcommand."""
    leading: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in {"--root", "--config"}:
            if index + 1 >= len(argv):
                raise KnowledgeError("--root requires a value")
            leading.extend((item, argv[index + 1]))
            index += 2
        elif item.startswith(("--root=", "--config=")):
            leading.append(item)
            index += 1
        else:
            remaining.append(item)
            index += 1
    return leading + remaining


def main(argv: list[str] | None = None) -> int:
    parser = parser_build()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(_normalize_global_options(raw_argv))
    except KnowledgeError as exc:
        parser.error(str(exc))
    root = args.root.resolve()
    try:
        instance = load_instance(root, args.config)
        configure(instance)
        if hasattr(args, "actor"):
            args.actor = args.actor or instance.identities["writer"]["id"]
            args.performed_by = args.performed_by or instance.identities["executor"]["id"]
        memory = validate_project_memory(instance)
        if not memory["ok"] and args.command in {"validate", "rebuild"}:
            payload = {"ok": False, "command": args.command, "errors": memory["errors"]}
            output(payload, args.format)
            return 1
        if args.command == "validate": payload = validate(root)
        elif args.command == "validate-merge": payload = validate_merge_command(root, args.base)
        elif args.command == "rebuild": payload = rebuild(root)
        elif args.command == "tree": payload = tree_command(root)
        elif args.command == "query": payload = query_command(root, args.query, args.level, args.limit, args.cursor, args.permission, args.node, args.topic)
        elif args.command in {"progressive-query", "query-context"}: payload = progressive_query_command(root, instance, args.context, args.intent, args.max_level, args.limit, args.permission, args.check_authority, args.cursor)
        elif args.command == "show-claim": payload = show_claim(root, args.claim_id, args.evidence_limit, args.cursor, args.permission)
        elif args.command == "register-source": payload = register_source_command(root, args)
        elif args.command == "new-claim": payload = new_claim_command(root, args)
        elif args.command == "add-evidence": payload = add_evidence_command(root, args)
        elif args.command == "propose": payload = propose_command(root, args)
        elif args.command == "resolve-proposal": payload = resolve_proposal_command(root, args)
        elif args.command == "revise-claim": payload = revise_claim_command(root, args)
        elif args.command == "supersede-claim": payload = append_semantic_event(root, args, "supersede-claim", "claim_superseded", {"claim_id": args.claim_id, "replacement_claim_id": args.replacement_claim_id, "reason": args.reason})
        elif args.command == "merge-claims": payload = append_semantic_event(root, args, "merge-claims", "claims_merged", {"claim_id": args.claim_id, "target_claim_id": args.target_claim_id, "reason": args.reason})
        elif args.command == "retract-evidence": payload = retract_evidence_command(root, args)
        elif args.command == "confirm-claim": payload = append_semantic_event(root, args, "confirm-claim", "claim_confirmed", {"claim_id": args.claim_id, "confirmation": args.confirmation, "reason": args.reason})
        elif args.command == "change-permission": payload = append_semantic_event(root, args, "change-permission", "claim_permission_changed", {"claim_id": args.claim_id, "permission": args.permission, "reason": args.reason})
        elif args.command == "capture": payload = capture_command(root, args, instance)
        elif args.command == "bundle-create": payload = bundle_create_command(root, args, instance)
        elif args.command == "bundle-approve": payload = bundle_approve_command(root, args, instance)
        elif args.command == "bundle-apply": payload = bundle_apply_command(root, args)
        elif args.command == "bundle-inspect": payload = bundle_inspect_command(root, args.bundle_id)
        elif args.command == "bundle-recover": payload = bundle_recover_command(root, args.bundle_id)
        elif args.command == "bundle-rollback": payload = bundle_rollback_command(root, args)
        elif args.command == "inspect-transaction": payload = inspect_transactions(root)
        elif args.command == "recover": payload = recover_transaction(root, args.operation_id)
        elif args.command == "rollback": payload = rollback_transaction(root, args.operation_id)
        elif args.command == "abandon": payload = abandon_transaction(root, args.operation_id)
        elif args.command == "new-id": payload = {"ok": True, "command": "new-id", "kind": args.kind, "id": new_id(args.kind), "errors": []}
        else: raise KnowledgeError(f"unknown command: {args.command}")
    except (KnowledgeError, RetrievalError, BundleError, OSError, sqlite3.Error) as exc:
        error = {"code": getattr(exc, "code", "KNOWLEDGE_ERROR"), "path": ".", "message": str(exc)}
        if isinstance(exc, RetrievalError):
            error.update(exc.details)
        payload = {"ok": False, "command": args.command, "read_only": args.command in {"progressive-query", "query-context", "capture"},
                   "operation_authorized": False, "errors": [error]}
    if args.command in {"recover", "rollback", "abandon"}:
        payload["git_status"] = git_status(root)
    output(payload, args.format)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
