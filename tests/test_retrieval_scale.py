from __future__ import annotations

import statistics
import sys
import time
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

from portable_knowledge.retrieval import build_progressive_scope


class RetrievalScaleGateTests(unittest.TestCase):
    def test_ten_x_neutral_fixture_has_stable_bounded_cost(self):
        # 120 Topics is >10x both acceptance projects' initial Topic counts.
        topics = []
        nodes = []
        links = []
        for node_index in range(12):
            node_id = f"neutral-{node_index:02d}"
            nodes.append({"id": node_id, "name": f"Neutral domain {node_index}", "boundary": f"bounded neutral group {node_index}"})
            links.append({"context_id": "scale", "node_id": node_id})
            for topic_index in range(10):
                topics.append({"id": f"neutral-{node_index:02d}-{topic_index:02d}", "node_id": node_id,
                               "title": f"Neutral token{node_index:02d} item{topic_index:02d}",
                               "summary": f"deterministic scale fixture token{node_index:02d} item{topic_index:02d}",
                               "keywords": [f"token{node_index:02d}", f"item{topic_index:02d}"], "permission": "internal"})
        config = {"memory": {"contexts": [{"id": "scale", "lifecycle": "active"}]},
                  "relations": {"context_nodes": links},
                  "retrieval": {"max_topics": 3, "dynamic": {"candidate_limit": 8, "confidence_threshold": 0.2, "margin_threshold": 0.0}, "intent_routes": []}}
        registry = {"nodes": nodes, "topics": topics}
        latencies = []
        observed = []
        for _ in range(100):
            started = time.perf_counter()
            result = build_progressive_scope(config, registry, context_id="scale", intent="token07 item03", limit=3)
            latencies.append((time.perf_counter() - started) * 1000)
            observed.append(([topic["id"] for topic in result["topics"]], [item["id"] for item in result["candidate_topics"]]))
        self.assertTrue(all(value == observed[0] for value in observed))
        self.assertEqual(observed[0][0][0], "neutral-07-03")
        self.assertLessEqual(len(observed[0][0]), 3)
        self.assertLessEqual(len(observed[0][1]), 8)
        ordered = sorted(latencies)
        p50 = statistics.median(ordered)
        p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
        self.assertLess(p50, 50.0, f"p50={p50:.3f}ms")
        self.assertLess(p95, 100.0, f"p95={p95:.3f}ms")


if __name__ == "__main__":
    unittest.main()
