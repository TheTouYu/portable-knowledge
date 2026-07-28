from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

from portable_knowledge.experience import (embed_texts, evaluate_cases, freshness_markers,
                                           search_knowledge, upstream_freshness)


class _Instance:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.projection_path = Path(".local/pkc")
        self.authority = {}
        self.raw = {"evaluation": {"cases_path": "evaluation/cases.json"}}


class ExperienceContractTests(unittest.TestCase):
    def test_embedding_cache_reuses_model_and_input_without_leaking_secret(self) -> None:
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}).encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("VECTORENGINE_API_KEY=secret\nVECTORENGINE_EMBEDDING_MODEL=fixture\nOTHER=ignored\n")
            opener = mock.Mock(return_value=Response())
            first, requests, model = embed_texts(root, Path(".local/pkc"), ["same"], opener=opener, sleep=lambda _: None)
            second, cached_requests, _ = embed_texts(root, Path(".local/pkc"), ["same"], opener=opener, sleep=lambda _: None)
            self.assertEqual(([[1.0, 0.0]], 1, "fixture"), (first, requests, model))
            self.assertEqual(first, second); self.assertEqual(0, cached_requests); self.assertEqual(1, opener.call_count)
            self.assertNotIn("secret", (root / ".local/pkc/vector/embedding-cache.json").read_text())

    def test_semantic_failure_falls_back_and_filters_conflicted_claim(self) -> None:
        root = Path(tempfile.mkdtemp())
        instance = _Instance(root)
        lexical = lambda _term: {"results": [
            {"id": "clm_good", "lifecycle": "active", "conflict": "none"},
            {"id": "clm_bad", "lifecycle": "active", "conflict": "open"},
        ]}
        detail = lambda claim_id: {"claim": {"id": claim_id, "node_id": "n", "topic_id": "t", "title": "Safe",
            "statement": "not returned", "permission": "internal", "lifecycle": "active", "conflict": "none"},
            "authority_support": {"status": "current"}}
        result = search_knowledge(root, instance, "query", [], "internal", 8, True, lexical, detail)
        self.assertEqual("lexical", result["mode"]); self.assertEqual(["clm_good"], [item["id"] for item in result["results"]])
        self.assertTrue(result["warnings"]); self.assertNotIn("not returned", json.dumps(result))

    def test_hybrid_adds_vector_only_candidate_after_live_governance_check(self) -> None:
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}).encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); instance = _Instance(root)
            (root / ".env").write_text("VECTORENGINE_API_KEY=fixture\n")
            vector_dir = root / ".local/pkc/vector"; vector_dir.mkdir(parents=True)
            (vector_dir / "index.json").write_text(json.dumps({"schema_version": 1, "model": "text-embedding-3-small",
                "permission": "internal", "objects": [{"claim": {"id": "vector_only"}, "embedding": [1.0, 0.0]}]}))
            detail = lambda claim_id: {"claim": {"id": claim_id, "node_id": "n", "topic_id": "t", "title": claim_id,
                "statement": "hidden", "permission": "internal", "lifecycle": "active", "conflict": "none"},
                "authority_support": {"status": "current"}}
            with mock.patch("portable_knowledge.experience.embed_texts", return_value=([[1.0, 0.0]], 1, "text-embedding-3-small")):
                result = search_knowledge(root, instance, "query", [], "internal", 8, True, lambda _: {"results": []}, detail)
            self.assertEqual("hybrid", result["mode"]); self.assertEqual(["vector_only"], [item["id"] for item in result["results"]])

    def test_hybrid_rejects_weak_vector_only_noise_relative_to_best_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); instance = _Instance(root)
            (root / ".env").write_text("VECTORENGINE_API_KEY=fixture\n")
            vector_dir = root / ".local/pkc/vector"; vector_dir.mkdir(parents=True)
            (vector_dir / "index.json").write_text(json.dumps({"schema_version": 1, "model": "text-embedding-3-small",
                "permission": "internal", "objects": [
                    {"claim": {"id": "best"}, "embedding": [1.0, 0.0]},
                    {"claim": {"id": "noise"}, "embedding": [0.6, 0.8]},
                ]}))
            detail = lambda claim_id: {"claim": {"id": claim_id, "node_id": "n", "topic_id": "t", "title": claim_id,
                "statement": "hidden", "permission": "internal", "lifecycle": "active", "conflict": "none"},
                "authority_support": {"status": "current"}}
            with mock.patch("portable_knowledge.experience.embed_texts", return_value=([[1.0, 0.0]], 1, "text-embedding-3-small")):
                result = search_knowledge(root, instance, "query", [], "internal", 8, True, lambda _: {"results": []}, detail)
            self.assertEqual(["best"], [item["id"] for item in result["results"]])

    def test_evaluation_enforces_topic_claim_refusal_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "evaluation").mkdir()
            (root / "evaluation/cases.json").write_text(json.dumps({"schema_version": 1, "defaults": {
                "topic_top_n": 3, "claim_top_n": 5, "permission": "internal"}, "cases": [{"id": "bounded",
                "query": "q", "expected_topic_ids": ["t"], "expected_claim_ids": ["good"], "must_not_claim_ids": ["bad"]}]}))
            instance = _Instance(root)
            result = evaluate_cases(root, instance, False, lambda *_: {"mode": "lexical", "warnings": [], "results": [
                {"rank": 1, "id": "good", "topic_id": "t", "permission": "internal", "lifecycle": "active", "conflict": "none"}]})
            self.assertEqual((1, 1), (result["passed"], result["total"]))

    def test_freshness_is_bounded_to_configured_surfaces_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "CURRENT.md").write_text("2 Nodes / 6 Topics / 21 Claims\nold runtime\n")
            (root / "config.json").write_text('  "old runtime",\n')
            failures = freshness_markers(root, {"current_surfaces": ["CURRENT.md", "config.json"], "count_surfaces": ["CURRENT.md"],
                "stale_markers": ["old runtime"]}, {"nodes": 2, "topics": 6, "claims": 21})
            self.assertEqual(1, len(failures)); self.assertIn("CURRENT.md:2", failures[0])
            warnings, invalid = upstream_freshness(root, ["missing.json"])
            self.assertEqual([], warnings); self.assertTrue(invalid)


if __name__ == "__main__": unittest.main()
