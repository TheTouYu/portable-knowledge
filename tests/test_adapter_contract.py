from __future__ import annotations
import sys, unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))
from portable_knowledge.adapter import route_task_start, task_end_value_gate


class AdapterContractTests(unittest.TestCase):
    def test_high_risk_routes_memory_before_bounded_knowledge(self):
        result = route_task_start(signals=["cross_file_judgment", "historical_constraint"])
        self.assertEqual(result["route"], "memory_then_knowledge")
        self.assertTrue(result["memory"])
        self.assertEqual(result["knowledge_levels"], [1, 2])

    def test_ordinary_mechanical_change_does_not_query(self):
        self.assertEqual(route_task_start(mechanical=True)["route"], "no_query")

    def test_risk_signal_overrides_mechanical_hint(self):
        result = route_task_start(signals=["permission_or_sensitive_data"], mechanical=True)
        self.assertEqual(result["route"], "memory_then_knowledge")

    def test_value_gate_defaults_to_no_write_and_excludes_low_value(self):
        result = task_end_value_gate([
            {"id": "a", "value_signals": ["stable_method"]},
            {"id": "b", "value_signals": ["temporary_note"]},
        ])
        self.assertFalse(result["default_write"])
        self.assertEqual([x["id"] for x in result["proposals"]], ["a"])
        self.assertEqual(result["excluded"][0]["exclusion_reason"], "no_durable_value_signal")

    def test_value_gate_never_displays_more_than_three_bundles(self):
        candidates = [{"id": str(i), "value_signals": ["real_evidence"]} for i in range(5)]
        result = task_end_value_gate(candidates)
        self.assertEqual(len(result["proposals"]), 3)
        self.assertEqual([x["exclusion_reason"] for x in result["excluded"]], ["bundle_limit", "bundle_limit"])


if __name__ == "__main__":
    unittest.main()
