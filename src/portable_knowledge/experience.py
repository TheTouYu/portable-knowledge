"""Project knowledge health, evaluation, and optional hybrid retrieval.

Git text remains authority. Vector indexes and embedding caches are disposable
projections below the configured PKC projection path. This module never changes
project authority, rebuilds SQLite, or interprets vector similarity as evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib import error, request

from .authority import (authority_refs_from_document, claim_authority_statuses,
                         observe_authority_refs)
from .evaluation_contract import (EvaluationContractError, evaluate_normalized_cases,
                                  load_evaluation_contract)

DEFAULT_BASE_URL = "https://api.vectorengine.ai/v1"
DEFAULT_MODEL = "text-embedding-3-small"
VECTOR_ONLY_RELATIVE_THRESHOLD = 0.70
ENV_NAMES = ("VECTORENGINE_API_KEY", "VECTORENGINE_BASE_URL", "VECTORENGINE_EMBEDDING_MODEL")
PERMISSION_RANK = {"restricted": 0, "internal": 1, "public_redacted": 2, "public": 3}


class ExperienceError(Exception):
    def __init__(self, message: str, *, environment: bool = False) -> None:
        self.environment = environment
        super().__init__(message)


def _relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperienceError(f"invalid JSON {path}: {exc}", environment=True) from exc
    if not isinstance(value, dict):
        raise ExperienceError(f"JSON document must be an object: {path}", environment=True)
    return value


def _paths(root: Path, projection: Path) -> tuple[Path, Path, Path]:
    directory = root / projection / "vector"
    return directory, directory / "index.json", directory / "embedding-cache.json"


def _load_env(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    local = root / ".env"
    if local.is_file():
        for raw in local.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in ENV_NAMES:
                values[key] = value.strip().strip("\"'")
    for key in ENV_NAMES:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def _cache_key(model: str, text: str) -> str:
    return f"{model}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _read_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "entries": {}}
    value = _read_json(path)
    if value.get("schema_version") != 1 or not isinstance(value.get("entries"), dict):
        raise ExperienceError("vector cache schema is invalid; remove the disposable cache and rebuild")
    return value


def embed_texts(root: Path, projection: Path, inputs: list[str], *, sleep: Callable[[float], None] = time.sleep,
                opener: Callable[..., Any] = request.urlopen) -> tuple[list[list[float]], int, str]:
    config = _load_env(root)
    api_key = config.get("VECTORENGINE_API_KEY")
    if not api_key:
        raise ExperienceError("VECTORENGINE_API_KEY is unavailable", environment=True)
    model = config.get("VECTORENGINE_EMBEDDING_MODEL", DEFAULT_MODEL)
    base_url = config.get("VECTORENGINE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    directory, _, cache_path = _paths(root, projection)
    cache = _read_cache(cache_path)
    output: list[list[float] | None] = [None] * len(inputs)
    missing: list[tuple[int, str, str]] = []
    for index, text in enumerate(inputs):
        key = _cache_key(model, text)
        entry = cache["entries"].get(key)
        vector = entry.get("embedding") if isinstance(entry, dict) and entry.get("model") == model else None
        if isinstance(vector, list) and vector:
            output[index] = vector
        else:
            missing.append((index, text, key))
    remote_requests = 0
    for start in range(0, len(missing), 16):
        batch = missing[start:start + 16]
        body = json.dumps({"model": model, "input": [item[1] for item in batch], "encoding_format": "float"}).encode()
        response_body: bytes | None = None
        last_status: int | str = "unknown"
        for attempt in range(4):
            req = request.Request(f"{base_url}/embeddings", data=body,
                                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
            try:
                remote_requests += 1
                with opener(req, timeout=15) as response:
                    last_status = response.status
                    response_body = response.read()
                break
            except error.HTTPError as exc:
                last_status = exc.code
                if exc.code != 429 and exc.code < 500:
                    raise ExperienceError(f"embedding provider failed: HTTP {exc.code}", environment=True) from None
            except (error.URLError, TimeoutError):
                last_status = "timeout_or_network"
            if attempt < 3:
                sleep(min(2 ** attempt, 8))
        if response_body is None:
            raise ExperienceError(f"embedding provider unavailable ({last_status})", environment=True)
        try:
            data = sorted(json.loads(response_body)["data"], key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in data]
            valid = len(vectors) == len(batch) and all(
                isinstance(vector, list) and vector and all(isinstance(value, (int, float)) for value in vector)
                for vector in vectors
            ) and len({len(vector) for vector in vectors}) == 1
            if not valid:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ExperienceError("embedding provider returned an invalid response", environment=True) from None
        for (index, _text, key), vector in zip(batch, vectors):
            output[index] = vector
            cache["entries"][key] = {"model": model, "embedding": vector}
        directory.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    return [vector for vector in output if vector is not None], remote_requests, model


def _claim_text(claim: dict[str, Any], authority_status: str) -> str:
    return "\n".join((claim["node_id"], claim["topic_id"], claim["title"], claim["statement"], authority_status))


def _visible_claim(claim: dict[str, Any], permission: str) -> bool:
    return (claim.get("lifecycle") == "active" and claim.get("conflict") == "none"
            and PERMISSION_RANK.get(claim.get("permission"), -1) >= PERMISSION_RANK[permission])


def authorized_claims(root: Path, instance: Any, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs_path = instance.authority.get("authority_refs")
    refs = authority_refs_from_document(_read_json(root / refs_path)) if refs_path else []
    observations = observe_authority_refs(root, refs)
    statuses = claim_authority_statuses(observations, (claim["id"] for claim in claims))
    return [{**claim, "authority_status": statuses.get(claim["id"], "not_registered")} for claim in claims]


def build_vector_index(root: Path, instance: Any, claims: list[dict[str, Any]], permission: str) -> dict[str, Any]:
    visible = sorted((claim for claim in authorized_claims(root, instance, claims) if _visible_claim(claim, permission)), key=lambda item: item["id"])
    if not visible:
        raise ExperienceError("no authorized active Claims are available for indexing")
    inputs = [_claim_text(claim, claim["authority_status"]) for claim in visible]
    vectors, requests_made, model = embed_texts(root, instance.projection_path, inputs)
    directory, index_path, _ = _paths(root, instance.projection_path)
    payload = {"schema_version": 1, "model": model, "dimensions": len(vectors[0]), "permission": permission,
               "objects": [{"claim": {key: claim[key] for key in ("id", "node_id", "topic_id", "title", "permission", "lifecycle", "conflict", "authority_status")},
                            "input_hash": hashlib.sha256(text.encode()).hexdigest(), "embedding": vector}
                           for claim, text, vector in zip(visible, inputs, vectors)]}
    directory.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return {"ok": True, "command": "knowledge-index", "objects": len(visible), "model": model,
            "dimensions": payload["dimensions"], "remote_requests": requests_made,
            "projection": index_path.relative_to(root).as_posix(),
            "scope_note": "Disposable vector projection only; similarity is not evidence and no authority was changed.", "errors": []}


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    aa = sum(value * value for value in left); bb = sum(value * value for value in right)
    return dot / math.sqrt(aa * bb) if aa and bb else 0.0


def search_knowledge(root: Path, instance: Any, query: str, terms: list[str], permission: str, limit: int,
                     semantic: bool, lexical_query: Callable[[str], dict[str, Any]],
                     claim_detail: Callable[[str], dict[str, Any]], status: str = "any") -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    query_terms = list(dict.fromkeys([query, *terms]))
    for term_index, term in enumerate(query_terms):
        for rank, item in enumerate(lexical_query(term).get("results", []), 1):
            if item.get("conflict") != "none" or item.get("lifecycle") != "active":
                continue
            score = 1.0 / (rank + term_index + 1)
            if item["id"] not in merged:
                detail = claim_detail(item["id"])
                claim = detail["claim"]
                authority = detail.get("authority_support", {}).get("status", "not_registered")
                if not _visible_claim(claim, permission):
                    continue
                merged[item["id"]] = {"id": claim["id"], "node_id": claim["node_id"], "topic_id": claim["topic_id"],
                                      "title": claim["title"], "permission": claim["permission"], "lifecycle": claim["lifecycle"],
                                      "conflict": claim["conflict"], "authority_status": authority, "rank_score": score}
            else:
                merged[item["id"]]["rank_score"] = max(merged[item["id"]]["rank_score"], score)
    # Authority status filtering runs before sorting and the final limit slice, so a
    # narrow status filter can never drop a qualifying Claim because truncation ran first.
    if status != "any":
        merged = {claim_id: item for claim_id, item in merged.items() if item["authority_status"] == status}
    candidates = list(merged.values())
    warnings: list[str] = []
    mode = "lexical"
    if semantic:
        try:
            _, index_path, _ = _paths(root, instance.projection_path)
            index = _read_json(index_path)
            configured_model = _load_env(root).get("VECTORENGINE_EMBEDDING_MODEL", DEFAULT_MODEL)
            if index.get("schema_version") != 1 or index.get("model") != configured_model or index.get("permission") != permission:
                raise ExperienceError("vector index schema, model, or permission changed; rebuild it")
            query_vectors, _, _ = embed_texts(root, instance.projection_path, [query])
            indexed = {item["claim"]["id"]: item for item in index.get("objects", [])
                       if isinstance(item, dict) and isinstance(item.get("claim"), dict)}
            semantic_scores = {claim_id: _cosine(query_vectors[0], item.get("embedding", []))
                               for claim_id, item in indexed.items()}
            best_semantic_score = max(semantic_scores.values(), default=0.0)
            vector_only_floor = max(0.0, best_semantic_score) * VECTOR_ONLY_RELATIVE_THRESHOLD
            for claim_id, indexed_item in indexed.items():
                if claim_id not in merged and semantic_scores[claim_id] >= vector_only_floor:
                    detail = claim_detail(claim_id)
                    claim = detail["claim"]
                    if not _visible_claim(claim, permission):
                        continue
                    authority = detail.get("authority_support", {}).get("status", "not_registered")
                    if status != "any" and authority != status:
                        continue
                    candidates.append({"id": claim["id"], "node_id": claim["node_id"], "topic_id": claim["topic_id"],
                                       "title": claim["title"], "permission": claim["permission"], "lifecycle": claim["lifecycle"],
                                       "conflict": claim["conflict"], "authority_status": authority,
                                       "rank_score": 0.0})
            for item in candidates:
                semantic_score = semantic_scores.get(item["id"], 0.0)
                authority_score = 1.0 if item["authority_status"] == "current" else 0.0
                item["semantic_score"] = semantic_score
                item["score"] = item["rank_score"] * .40 + semantic_score * .45 + authority_score * .15
            mode = "hybrid"
        except (ExperienceError, OSError, json.JSONDecodeError) as exc:
            warnings.append(f"semantic fallback: {exc}")
    if mode == "lexical":
        for item in candidates:
            item["score"] = item["rank_score"]
    candidates.sort(key=lambda item: (-item["score"], item["id"]))
    results = [{"rank": rank, "claim_id": item["id"],
                **{key: item[key] for key in ("id", "node_id", "topic_id", "title", "permission", "lifecycle", "conflict", "authority_status")},
                "score": round(item["score"], 6), **({"semantic_score": round(item["semantic_score"], 6)} if mode == "hybrid" else {})}
               for rank, item in enumerate(candidates[:max(1, min(limit, 20))], 1)]
    return {"ok": True, "command": "knowledge-search", "query": query, "mode": mode, "warnings": warnings,
            "results": results, "scope_note": "Permission, active lifecycle, conflict, and Authority status were checked before output; similarity is not evidence.", "errors": []}


def _evaluation_error(exc: EvaluationContractError) -> ExperienceError:
    error = ExperienceError(str(exc), environment=True)
    error.code = "EVALUATION_SCHEMA"
    error.path = exc.path
    error.field = exc.field
    error.case_id = exc.case_id
    return error


def load_evaluation_cases(root: Path, instance: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compatibility facade returning the canonical normalized contract."""
    try:
        contract = load_evaluation_contract(root, instance)
    except EvaluationContractError as exc:
        raise _evaluation_error(exc) from exc
    return contract["defaults"], contract["cases"]


def evaluate_cases(root: Path, instance: Any, semantic: bool,
                   search: Callable[[str, list[str], str, int, bool], dict[str, Any]]) -> dict[str, Any]:
    try:
        contract = load_evaluation_contract(root, instance)
    except EvaluationContractError as exc:
        raise _evaluation_error(exc) from exc
    return evaluate_normalized_cases(contract, contract["cases"], search, semantic=semantic, phase="project")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, encoding="utf-8", capture_output=True, timeout=20, check=False)
    if result.returncode:
        raise ExperienceError("Git repository or command is unavailable", environment=True)
    return result.stdout.strip()


def upstream_freshness(root: Path, configured: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []; failures: list[str] = []
    for rel in configured:
        if not _relative(rel):
            failures.append(f"invalid upstream lock path: {rel}"); continue
        try:
            lock = _read_json(root / rel)
            for dependency in lock.get("dependencies", []):
                checkout = dependency.get("checkout")
                if not isinstance(checkout, str):
                    raise ExperienceError(f"{dependency.get('id', rel)}: checkout is missing")
                repo = (root / checkout).resolve()
                affected = dependency.get("reviewClaims", dependency.get("review_claims", []))
                try:
                    head = _git(repo, "rev-parse", "HEAD")
                except ExperienceError:
                    warnings.append(f"{dependency.get('id', rel)}: upstream checkout unavailable"); continue
                source_commit = dependency.get("sourceCommit", dependency.get("source_commit"))
                if head != source_commit:
                    warnings.append(f"{dependency.get('id', rel)}: upstream HEAD changed; review Claims {', '.join(affected)}")
                for item in dependency.get("paths", []):
                    path = repo / item["path"]
                    if not path.is_file():
                        warnings.append(f"{dependency.get('id', rel)}: upstream path unavailable: {item['path']}"); continue
                    if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                        warnings.append(f"{dependency.get('id', rel)}: upstream fingerprint changed: {item['path']}; review Claims {', '.join(affected)}")
        except (ExperienceError, KeyError, TypeError) as exc:
            failures.append(f"upstream lock invalid ({rel}): {exc}")
    return warnings, failures


def freshness_markers(root: Path, config: dict[str, Any], counts: dict[str, int]) -> list[str]:
    failures = []
    surfaces = config.get("current_surfaces", [])
    markers = config.get("stale_markers", [])
    for rel in surfaces:
        if not _relative(rel) or not (root / rel).is_file():
            failures.append(f"current surface missing or invalid: {rel}"); continue
        for line_number, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
            for marker in markers:
                declaration = line.strip().rstrip(",") == json.dumps(marker, ensure_ascii=False)
                if isinstance(marker, str) and marker in line and not declaration:
                    failures.append(f"stale marker: {rel}:{line_number}: {marker}")
    expected = f"{counts.get('nodes', 0)} Nodes / {counts.get('topics', 0)} Topics / {counts.get('claims', 0)} Claims"
    for rel in config.get("count_surfaces", []):
        if _relative(rel) and (root / rel).is_file() and expected not in (root / rel).read_text(encoding="utf-8"):
            failures.append(f"count surface {rel} must state: {expected}")
    return failures
