from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))
from portable_knowledge import core

FIXTURE = PACKAGE / "tests/fixtures/semantic-plan"


class SemanticPlanContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "fixture"
        shutil.copytree(FIXTURE, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "neutral baseline"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *argv: str, expected: int = 0) -> dict:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = core.main(["--root", str(self.root), *argv])
        payload = json.loads(stream.getvalue())
        self.assertEqual(result, expected, payload)
        return payload

    def cli_process(self, *argv: str, expected: int = 0) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        completed = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root), *argv],
                                   cwd=PACKAGE, env=env, text=True, encoding="utf-8", capture_output=True)
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, expected, {"payload": payload, "stderr": completed.stderr})
        return payload

    def cli_text(self, *argv: str, expected: int = 0) -> str:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = core.main(["--root", str(self.root), *argv, "--format", "text"])
        self.assertEqual(result, expected, stream.getvalue())
        return stream.getvalue()

    def formal_authority(self) -> dict[str, bytes]:
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for base in (self.root / "data", self.root / "domain")
                for path in base.rglob("*") if path.is_file() and "data/knowledge/bundles/" not in path.relative_to(self.root).as_posix()}

    def init(self) -> dict:
        return self.cli("knowledge-plan", "init", "--intent", "Add neutral software contracts", "--risk", "medium")

    def add_claim(self, plan_id: str, topic: str, title: str, statement: str, facts: tuple[str, ...]) -> dict:
        args = ["knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", f"topic-{topic}",
                "--title", title, "--statement", statement, "--boundary", "Only the committed neutral fixture is in scope."]
        for fact in facts:
            args += ["--fact-class", fact]
        return self.cli(*args)

    def add_ref(self, plan_id: str, claim_id: str, topic: str, path: str, role: str, fact: str) -> dict:
        return self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", claim_id,
                        "--path", path, "--locator", f"{topic} contract", "--role", role,
                        "--change-policy", "invalidate_on_change", "--fact-class", fact,
                        "--diagnostic-hash", "0" * 64)

    def build_complete_plan(self) -> tuple[str, list[str], dict]:
        plan_id = self.init()["plan_id"]
        specs = [
            ("schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.", ("documented_contract", "public_type_surface")),
            ("runtime", "Runtime selection is deterministic", "The runtime selects the same implementation for the same input.", ("documented_contract", "runtime_behavior")),
            ("validation", "Validation fails closed", "Validation rejects incomplete semantic inputs before mutation.", ("documented_contract", "cli_behavior")),
        ]
        claims = []
        for topic, title, statement, facts in specs:
            claims.append(self.add_claim(plan_id, topic, title, statement, facts)["claim_id"])
        second = {"schema": "public_type_surface", "runtime": "runtime_behavior", "validation": "cli_behavior"}
        for claim_id, (topic, _, _, _) in zip(claims, specs):
            self.add_ref(plan_id, claim_id, topic, f"authority/{topic}-contract.md", "documented_contract", "documented_contract")
            self.add_ref(plan_id, claim_id, topic, f"authority/{topic}-contract.md", "current_implementation", second[topic])
        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        return plan_id, claims, delta

    def test_capabilities_are_runtime_machine_readable(self):
        payload = self.cli("capabilities")
        self.assertEqual(payload["runtime_version"], core._runtime_version())
        for name in ("semantic_plan", "provenance", "delta_validation", "authority_ref", "lifecycle", "supersede",
                     "migration_plan", "bundle_orchestration_plan", "bundle_migration_plan",
                     "knowledge_structure_refactor", "claim_revision_plan", "authority_ref_refresh_plan",
                     "authority_ref_retirement_plan"):
            self.assertTrue(payload["capabilities"][name])
        from portable_knowledge import __version__
        self.assertEqual(__version__, payload["runtime_version"])
        self.assertFalse(payload["capabilities"]["routes"])
        self.assertTrue(payload["capabilities"]["evaluation_cases"])
        for name in ("knowledge_health", "hybrid_retrieval", "vector_cache", "upstream_freshness"):
            self.assertTrue(payload["capabilities"][name])

    def test_three_claims_six_refs_delta_and_single_immutable_bundle(self):
        plan_id, claims, delta = self.build_complete_plan()
        self.assertEqual(len(claims), 3)
        self.assertEqual(delta["touched_operations"], 9)
        self.assertTrue(delta["can_finalize"])
        self.assertEqual(self.formal_authority(), self.authority_before)
        open_inspection = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual((open_inspection["approval_recorded"], open_inspection["bundle_state"], open_inspection["bundle_applied"]),
                         (False, "not_finalized", False))
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertFalse(finalized["summary"]["approved"]); self.assertFalse(finalized["summary"]["applied"])
        finalized_inspection = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual((finalized_inspection["approval_recorded"], finalized_inspection["bundle_state"], finalized_inspection["bundle_applied"]),
                         (False, "draft", False))
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text(encoding="utf-8"))
        bundle_inspection = self.cli("bundle-inspect", finalized["bundle_id"])
        self.assertEqual(bundle_inspection["count"], 1)
        self.assertEqual(bundle_inspection["bundles"][0]["lifecycle_files"], {
            "bundle": f"data/knowledge/bundles/{finalized['bundle_id']}.json",
            "approval": f"data/knowledge/bundles/{finalized['bundle_id']}.approval.json",
            "applied": f"data/knowledge/bundles/{finalized['bundle_id']}.applied.json",
        })
        self.assertTrue(all(set(action["provenance"]) == {"plan_id", "operation_id", "operation_type", "operation_digest", "core_version"}
                            for action in bundle["actions"]))
        self.assertNotIn("bundle", finalized)
        replay = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertTrue(replay["summary"]["replayed"])
        self.assertEqual((replay["bundle_id"], replay["content_hash"]), (finalized["bundle_id"], finalized["content_hash"]))
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        # Only the immutable Bundle artifact was created; production authority remains unchanged.
        self.assertEqual(self.formal_authority(), self.authority_before)
        dry = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"])
        self.assertTrue(dry["dry_run"])
        self.assertFalse(dry["applied"])
        self.assertIn("DRY RUN", dry["next_step"])
        self.assertFalse((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.approval.json").exists())
        approved = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.assertTrue(approved["applied"])
        dry_apply = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"])
        self.assertTrue(dry_apply["dry_run"])
        self.assertIn("DRY RUN", dry_apply["next_step"])
        self.assertFalse((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.applied.json").exists())
        self.assertTrue(approved["applied"])
        approved_inspection = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual((approved_inspection["approval_recorded"], approved_inspection["bundle_state"], approved_inspection["bundle_applied"]),
                         (True, "approved", False))

    def test_inspect_previews_closeout_phases_without_mutation(self):
        plan_id = self.init()["plan_id"]
        claim_id = self.add_claim(plan_id, "schema", "Preview contract", "Inspection previews the governed closeout phases.", ("documented_contract",))["claim_id"]
        added_ref = self.add_ref(plan_id, claim_id, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
        before = plan_path.read_bytes()
        preview = self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]
        self.assertTrue(preview["read_only"])
        self.assertEqual([phase["id"] for phase in preview["phases"]],
                         ["claim_capture", "memory_synchronization", "git_commit", "authority_refresh", "final_validation"])
        self.assertEqual([phase["status"] for phase in preview["phases"]],
                         ["planned", "not_configured", "planned", "planned", "pending"])
        self.assertTrue(all(phase["read_only"] for phase in preview["phases"]))
        self.assertEqual(preview["affected_authority_refs"], [{
            "authority_ref_id": added_ref["authority_ref_id"],
            "change": "added",
            "path": "authority/schema-contract.md",
            "old_hash": None,
            "new_hash": added_ref["approved_hash"],
            "linked_claim_ids": [claim_id],
            "human_review_reason": "A new Authority Reference requires exact-hash human review.",
        }])
        self.assertEqual(preview["authority_ref_counts"], {"added": 1, "refreshed": 0, "retired": 0, "affected": 1,
                                                            "plan_affected": 1, "historical": 0})
        self.assertEqual(preview["health"], "FAIL")
        self.assertEqual(plan_path.read_bytes(), before)
        self.assertEqual(list((self.root / "data/knowledge/bundles").glob("bnd_*.json")), [])

        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        self.assertTrue(delta["can_finalize"])
        ready = self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]
        self.assertEqual(ready["health"], "PASS_WITH_REVIEW")
        self.assertEqual(ready["phases"][-1]["status"], "ready")
        self.assertEqual(ready["phases"][-1]["reason"], "Current delta validation permits finalize")
        self.assertEqual(self.cli("knowledge-plan", "inspect", plan_id)["cost_counters"],
                         delta["cost_counters"])

    def test_inspect_previews_claim_count_memory_authority_dependency_without_mutation(self):
        config_path = self.root / "project-intelligence.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["experience"] = {"count_surfaces": ["memory/CURRENT.md"]}
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        memory_path = self.root / "memory/CURRENT.md"
        old_hash = hashlib.sha256(memory_path.read_bytes()).hexdigest()
        refs_path = self.root / "data/store/authority-refs.json"
        refs_path.write_text(json.dumps({"schema_version": 1, "refs": [{
            "id": "aref_current_counts", "path": "memory/CURRENT.md", "locator": "claim counts",
            "role": "documented_contract", "baseline_state": "committed_baseline",
            "change_policy": "invalidate_on_change", "approved_hash": old_hash,
            "claim_ids": ["clm_existing"], "supports_fact_classes": ["documented_contract"],
        }]}, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "project-intelligence.json", "data/store/authority-refs.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "configure count Memory Authority"], cwd=self.root, check=True)

        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Counted Claim", "Claim count changes require Memory synchronization.", ("documented_contract",))
        plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
        before = {path: path.read_bytes() for path in (config_path, memory_path, refs_path, plan_path)}
        preview = self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]

        memory_phase = next(phase for phase in preview["phases"] if phase["id"] == "memory_synchronization")
        self.assertEqual((memory_phase["status"], memory_phase["affected_paths"]), ("planned", ["memory/CURRENT.md"]))
        self.assertEqual(preview["affected_authority_refs"], [{
            "authority_ref_id": "aref_current_counts", "change": "memory_sync_required", "path": "memory/CURRENT.md",
            "old_hash": old_hash, "new_hash": None, "linked_claim_ids": ["clm_existing"],
            "human_review_reason": "Claim-count Memory must be synchronized and committed before this reference can be refreshed.",
        }])
        self.assertEqual([phase["status"] for phase in preview["phases"][:4]], ["planned", "planned", "planned", "planned"])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(list((self.root / "data/knowledge/bundles").glob("bnd_*.json")), [])

    def test_inspect_reports_staged_authority_dependency_without_mutation(self):
        topic = self.root / "domain/topics/schema.md"
        old_hash = hashlib.sha256(topic.read_bytes()).hexdigest()
        refs_path = self.root / "data/store/authority-refs.json"
        refs_path.write_text(json.dumps({"schema_version": 1, "refs": [{
            "id": "aref_schema_topic", "path": "domain/topics/schema.md", "locator": "whole topic",
            "role": "documented_contract", "baseline_state": "committed_baseline",
            "change_policy": "invalidate_on_change", "approved_hash": old_hash,
            "claim_ids": ["clm_existing"], "supports_fact_classes": ["documented_contract"],
        }]}, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "data/store/authority-refs.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add topic Authority dependency"], cwd=self.root, check=True)

        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Dependent preview", "A staged Topic affects its existing Authority Ref.",
                       ("documented_contract",))
        plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
        before = plan_path.read_bytes()
        formal_before = self.formal_authority()
        preview = self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]
        report = preview["affected_authority_refs"]

        self.assertEqual(next(phase for phase in preview["phases"] if phase["id"] == "authority_refresh")["status"], "planned")
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0], {
            "authority_ref_id": "aref_schema_topic",
            "change": "source_path_staged",
            "path": "domain/topics/schema.md",
            "old_hash": old_hash,
            "new_hash": report[0]["new_hash"],
            "linked_claim_ids": ["clm_existing"],
            "human_review_reason": "The staged Authority change requires a committed baseline before this reference can be refreshed or retired.",
        })
        self.assertNotEqual(report[0]["new_hash"], old_hash)
        self.assertEqual(plan_path.read_bytes(), before)
        self.assertEqual(self.formal_authority(), formal_before)
        self.assertEqual(list((self.root / "data/knowledge/bundles").glob("bnd_*.json")), [])

    def test_same_plan_replay_keeps_ids_delta_diff_files_and_bundle(self):
        plan_id, claims, delta = self.build_complete_plan()
        replay = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                                ("documented_contract", "public_type_surface"))
        self.assertTrue(replay["replayed"]); self.assertEqual(replay["claim_id"], claims[0])
        delta_again = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        self.assertEqual(delta_again["delta_digest"], delta["delta_digest"])
        self.assertEqual(delta_again["touched_files"], delta["touched_files"])
        first = self.cli("knowledge-plan", "finalize", plan_id)
        second = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{first['bundle_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(first["changed_files"], bundle["expected_changed_files"])
        self.assertEqual(first["bundle_id"], second["bundle_id"])
        self.assertEqual(first["artifact_path"], second["artifact_path"])

    def test_new_claim_and_plan_share_the_same_core_semantic_function(self):
        original = core.plan_new_claim
        with mock.patch.object(core, "plan_new_claim", wraps=original) as shared:
            plan_id = self.init()["plan_id"]
            self.add_claim(plan_id, "schema", "Shared semantic rule", "One shared pure function creates this planned Claim.", ("documented_contract",))
            self.cli("new-claim", "--node", "software-core", "--topic-id", "topic-runtime", "--title", "Single command rule",
                     "--statement", "The old command calls the same pure function.", "--boundary", "Neutral fixture only.", "--dry-run")
        self.assertEqual(shared.call_count, 2)

    def test_plan_can_create_a_distinct_topic_with_complete_metadata(self):
        plan_id = self.init()["plan_id"]
        added = self.cli(
            "knowledge-plan", "add-claim", plan_id,
            "--node", "software-core", "--topic-id", "topic-observability",
            "--topic-path", "domain/topics/observability.md",
            "--topic-title", "Observability Contract",
            "--topic-summary", "Neutral diagnostic behavior",
            "--topic-keyword", "diagnostics", "--topic-keyword", "tracing",
            "--title", "Diagnostics remain bounded",
            "--statement", "Diagnostics expose bounded neutral state.",
            "--boundary", "Only the committed neutral fixture is in scope.",
            "--duplicate-resolution", "create_distinct_with_boundary",
            "--fact-class", "documented_contract",
        )
        self.assertFalse(added["replayed"])
        text_plan = self.cli("knowledge-plan", "init", "--intent", "Text claim id output", "--risk", "low")["plan_id"]
        text = self.cli_text("knowledge-plan", "add-claim", text_plan, "--node", "software-core", "--topic-id", "topic-runtime",
                             "--title", "Text output", "--statement", "Text output exposes its generated Claim id.",
                             "--boundary", "Neutral fixture only.", "--fact-class", "cli_behavior")
        self.assertIn("Claim ID: clm_", text)
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual(inspected["claim_count"], 1)
        plan = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        registry = json.loads(base64.b64decode(plan["writes"]["data/store/registry.json"]))
        topic = next(item for item in registry["topics"] if item["id"] == "topic-observability")
        self.assertEqual(topic["title"], "Observability Contract")
        self.assertEqual(topic["summary"], "Neutral diagnostic behavior")
        self.assertEqual(topic["keywords"], ["diagnostics", "tracing"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_plan_atomically_creates_node_topic_and_first_claim(self):
        plan_id = self.init()["plan_id"]
        added = self.cli(
            "knowledge-plan", "add-claim", plan_id,
            "--node", "delivery-safety", "--node-name", "Delivery Safety",
            "--node-path", "domain/delivery", "--node-boundary", "Safe delivery contracts",
            "--node-keyword", "delivery", "--node-keyword", "safety",
            "--topic-id", "topic-release-gates", "--topic-path", "domain/delivery/release-gates.md",
            "--topic-title", "Release Gates", "--topic-summary", "Neutral release requirements",
            "--topic-keyword", "release",
            "--title", "Release gates fail closed",
            "--statement", "A release stops when a required gate is incomplete.",
            "--boundary", "This does not establish any external deployment result.",
            "--duplicate-resolution", "create_distinct_with_boundary",
            "--fact-class", "documented_contract",
        )
        self.assertTrue(added["claim_id"].startswith("clm_"))
        plan = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        registry = json.loads(base64.b64decode(plan["writes"]["data/store/registry.json"]))
        node = next(item for item in registry["nodes"] if item["id"] == "delivery-safety")
        self.assertEqual(node, {"id": "delivery-safety", "name": "Delivery Safety", "path": "domain/delivery",
                               "boundary": "Safe delivery contracts", "keywords": ["delivery", "safety"],
                               "migration_status": "pilot"})
        topic = next(item for item in registry["topics"] if item["id"] == "topic-release-gates")
        self.assertEqual(topic["node_id"], "delivery-safety")
        self.assertEqual(topic["path"], "domain/delivery/release-gates.md")
        self.add_ref(plan_id, added["claim_id"], "release-gates", "authority/validation-contract.md",
                     "documented_contract", "documented_contract")
        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        self.assertTrue(delta["can_finalize"])
        self.assertEqual(delta["touched_operations"], 2)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_structural_creation_rejects_implicit_or_partial_metadata(self):
        cases = [
            (["--node", "software-core", "--topic-id", "topic-new", "--topic-path", "domain/topics/new.md"],
             "PLAN_TOPIC_INVALID", "duplicate-resolution"),
            (["--node", "new-node", "--node-name", "Incomplete", "--topic-id", "topic-new",
              "--topic-path", "domain/new/topic.md", "--duplicate-resolution", "create_distinct_with_boundary"],
             "PLAN_TOPIC_INVALID", "node-path"),
            (["--node", "new-node", "--node-name", "New Node", "--node-path", "domain/new",
              "--node-boundary", "New contracts", "--topic-id", "topic-new", "--topic-path", "domain/outside/topic.md",
              "--duplicate-resolution", "create_distinct_with_boundary"],
             "PLAN_TOPIC_INVALID", "under its node path"),
            (["--node", "software-core", "--node-name", "Renamed", "--topic-id", "topic-schema"],
             "PLAN_TOPIC_INVALID", "node metadata"),
            (["--node", "software-core", "--topic-id", "topic-schema", "--topic-title", "Renamed"],
             "PLAN_TOPIC_INVALID", "topic metadata"),
        ]
        for index, (structural_args, code, message) in enumerate(cases):
            with self.subTest(index=index):
                plan_id = self.cli("knowledge-plan", "init", "--intent", f"Rejected structure {index}", "--risk", "medium")["plan_id"]
                failed = self.cli(
                    "knowledge-plan", "add-claim", plan_id, *structural_args,
                    "--title", f"Rejected claim {index}", "--statement", f"Rejected statement {index}.",
                    "--boundary", "Neutral fixture only.", "--fact-class", "documented_contract", expected=1,
                )
                self.assertEqual(failed["errors"][0]["code"], code)
                self.assertIn(message, failed["errors"][0]["message"])
                self.assertEqual(self.formal_authority(), self.authority_before)

    def test_cli_delta_rejects_authority_path_modified_by_same_plan(self):
        existing = self.root / "domain/topics/existing-contract.md"
        existing.write_text("# Existing committed contract\n", encoding="utf-8")
        subprocess.run(["git", "add", existing.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add existing contract"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()
        plan_id = self.cli_process("knowledge-plan", "init", "--intent", "Reject staged self-reference", "--risk", "medium")["plan_id"]
        added = self.cli_process(
            "knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-existing-contract",
            "--topic-path", "domain/topics/existing-contract.md", "--topic-title", "Existing Contract",
            "--topic-summary", "Neutral bounded summary", "--topic-keyword", "neutral",
            "--duplicate-resolution", "create_distinct_with_boundary", "--title", "Bounded documented Claim",
            "--statement", "One neutral documented assertion.", "--boundary", "Does not establish runtime behavior.",
            "--permission", "internal", "--fact-class", "documented_contract")
        self.cli_process("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", added["claim_id"],
                         "--path", "domain/topics/existing-contract.md", "--locator", "section:existing-contract",
                         "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                         "--fact-class", "documented_contract")
        delta = self.cli_process("knowledge-plan", "check", plan_id, "--mode", "delta", expected=1)
        finding = next(item for item in delta["findings"] if item["code"] == "PLAN_AUTHORITY_STAGED_DRIFT")
        self.assertEqual(finding["path"], "domain/topics/existing-contract.md")
        self.assertTrue(finding["staged_by_current_plan"])
        denied = self.cli_process("knowledge-plan", "finalize", plan_id, expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_DELTA_REQUIRED")
        inspected = self.cli_process("knowledge-plan", "inspect", plan_id)
        self.assertEqual((inspected["state"], inspected["cost_counters"]["candidate_bundles"]), ("open", 0))
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_cli_finalize_warns_on_historical_stale_refs_and_completes(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
        refs["refs"].append({"id": "aref_stale_fixture", "path": "authority/schema-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "0" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs["refs"].append({"id": "aref_stale_fixture_2", "path": "authority/validation-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "1" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs_path.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", refs_path.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add stale authority fixtures"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()
        plan_id = self.cli_process("knowledge-plan", "init", "--intent", "Expose Authority diagnostics", "--risk", "medium")["plan_id"]
        added = self.cli_process("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-schema",
                                 "--title", "Diagnostic contract", "--statement", "Full preflight reports its failed component.",
                                 "--boundary", "Neutral fixture only.", "--fact-class", "documented_contract")
        self.cli_process("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", added["claim_id"],
                         "--path", "authority/schema-contract.md", "--locator", "diagnostic contract",
                         "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                         "--fact-class", "documented_contract")
        self.assertTrue(self.cli_process("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli_process("knowledge-plan", "finalize", plan_id)
        self.assertTrue(finalized["summary"]["finalized"])
        warnings = finalized["warnings"]
        self.assertEqual(len(warnings), 2)
        warning = next(item for item in warnings if item["authority_ref_id"] == "aref_stale_fixture")
        self.assertEqual(warning["code"], "PLAN_FULL_AUTHORITY_NOT_CURRENT")
        self.assertEqual(warning["effective_status"], "invalidated")
        self.assertEqual(warning["expected_hash"], "0" * 64)
        self.assertEqual(len(warning["observed_hash"]), 64)
        self.assertFalse(warning["staged_by_current_plan"])
        self.assertEqual(warning["authority_scope"], "historical")
        self.assertFalse(warning["blocking"])
        self.assertIn("separate authority-maintenance plan", warning["recommended_action"])
        maintenance = finalized["authority_maintenance"]
        self.assertEqual(maintenance["historical_count"], 2)
        self.assertEqual(sorted(maintenance["historical_ref_ids"]), ["aref_stale_fixture", "aref_stale_fixture_2"])
        self.assertFalse(maintenance["blocking"])
        self.assertIn("separate authority-maintenance plan", maintenance["recommended_action"])
        full = json.loads((self.root / finalized["artifact_path"]).read_text(encoding="utf-8"))
        self.assertTrue(full["ok"])
        self.assertEqual(len(full["authority_warnings"]), 2)
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        replay = self.cli_process("knowledge-plan", "finalize", plan_id)
        self.assertTrue(replay["summary"]["replayed"])
        self.assertEqual(len(replay["warnings"]), 2)
        inspected = self.cli_process("knowledge-plan", "inspect", plan_id)
        self.assertEqual((inspected["state"], inspected["cost_counters"]["candidate_bundles"]), ("finalized", 1))
        self.assertFalse(inspected["closeout_preview"]["authority_maintenance"]["blocking"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_historical_stale_refs_warn_but_plan_affected_stale_ref_still_blocks_finalize(self):
        # Establish a governed Claim + Ref, apply it, and commit the applied authority as baseline.
        initial = self.init()["plan_id"]
        added = self.add_claim(initial, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))
        original = self.add_ref(initial, added["claim_id"], "schema", "authority/schema-contract.md",
                                "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", initial, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", initial)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "governed schema baseline"], cwd=self.root, check=True)

        # Two unrelated historical stale refs and one stale ref linked to the plan's revised Claim.
        refs_path = self.root / "data/store/authority-refs.json"
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
        refs["refs"].append({"id": "aref_historical_a", "path": "authority/validation-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "0" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs["refs"].append({"id": "aref_historical_b", "path": "authority/runtime-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "1" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs_path.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", refs_path.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add stale fixture refs"], cwd=self.root, check=True)

        # The committed source of the plan-linked Ref changes, so that Ref is stale AND plan-affected.
        authority = self.root / "authority/schema-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "\nChanged source.\n", encoding="utf-8")
        subprocess.run(["git", "add", "authority/schema-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change schema authority source"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()

        plan_id = self.init()["plan_id"]
        unrelated = self.add_claim(plan_id, "validation", "Unrelated validation claim",
                                   "This claim is unrelated to stale authority.", ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, unrelated, "validation", "authority/validation-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "revise-claim", plan_id, "--claim-id", added["claim_id"],
                 "--title", "Schema input is explicit and versioned",
                 "--statement", "The schema parser accepts explicit versioned fields with a version marker.",
                 "--boundary", "Only the committed neutral fixture is in scope.",
                 "--semantic-declaration", "clarify", "--reason", "Sharpen the statement.")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        failed = self.cli_process("knowledge-plan", "finalize", plan_id, expected=1)
        affected = next(item for item in failed["errors"] if item["authority_ref_id"] == original["authority_ref_id"])
        self.assertEqual(affected["code"], "PLAN_FULL_AUTHORITY_NOT_CURRENT")
        self.assertEqual(affected["authority_scope"], "plan_affected")
        self.assertTrue(affected["blocking"])
        self.assertEqual(affected["effective_status"], "invalidated")
        self.assertEqual(affected["claim_ids"], [added["claim_id"]])
        historical = [item for item in failed["errors"] if item["authority_ref_id"].startswith("aref_historical_")]
        self.assertEqual(len(historical), 2)
        self.assertTrue(all(item["authority_scope"] == "historical" and not item["blocking"] for item in historical))
        bundles = [path for path in (self.root / "data/knowledge/bundles").glob("bnd_*.json") if path.name.count(".") == 1]
        self.assertEqual(len(bundles), 1)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_knowledge_check_skips_unconfigured_retrieval_evaluation(self):
        config_path = self.root / "project-intelligence.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config.pop("evaluation")
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        self.cli("rebuild")
        checked = self.cli("knowledge-check")
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["retrieval"]["status"], "NOT_CONFIGURED")
        self.assertTrue(checked["retrieval"]["skipped"])

    def test_semantic_plan_error_with_empty_findings_uses_top_level_cli_error(self):
        with mock.patch("portable_knowledge.semantic_plan.dispatch_plan_command",
                        side_effect=core.SemanticPlanError("PLAN_FORCED_EMPTY", "forced empty findings", [])):
            failed = self.cli("knowledge-plan", "init", "--intent", "Defensive serialization", "--risk", "low", expected=1)
        self.assertEqual(failed["errors"], [{"code": "PLAN_FORCED_EMPTY", "path": ".", "message": "forced empty findings"}])

    def test_authority_registry_alias_is_read_and_normalized_to_canonical_refs(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs_path.write_text('{"schema_version":1,"authority_refs":[]}\n', encoding="utf-8")
        subprocess.run(["git", "add", refs_path.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "legacy Authority registry alias"], cwd=self.root, check=True)
        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Alias normalization", "Legacy registry input is normalized.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        plan = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text())
        staged = json.loads(base64.b64decode(plan["writes"]["data/store/authority-refs.json"]))
        self.assertIn("refs", staged); self.assertNotIn("authority_refs", staged)

    def test_conflicting_authority_registry_keys_fail_closed(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs_path.write_text('{"schema_version":1,"refs":[],"authority_refs":[{"id":"conflict"}]}\n', encoding="utf-8")
        failed = self.cli("validate", expected=1)
        self.assertEqual(failed["errors"][0]["code"], "AUTHORITY_REFS_SCHEMA")

    def test_fail_closed_matrix_and_zero_formal_authority_writes(self):
        plan_id = self.init()["plan_id"]
        first = self.add_claim(plan_id, "schema", "Unique schema contract", "A unique schema statement is validated.", ("documented_contract",))
        failures = [
            (lambda: self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "missing-topic",
                              "--title", "Bad topic", "--statement", "Cannot route this claim.", "--boundary", "None.",
                              "--fact-class", "documented_contract", expected=1), "PLAN_TOPIC_INVALID"),
            (lambda: self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-runtime",
                              "--title", "Unique schema contract", "--statement", "A unique schema statement is validated.", "--boundary", "Only the committed neutral fixture is in scope.",
                              "--fact-class", "documented_contract", expected=1), "PLAN_DUPLICATE"),
            (lambda: self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", first["claim_id"], "--path", "untracked.md",
                              "--locator", "x", "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                              "--fact-class", "documented_contract", expected=1), "PLAN_AUTHORITY_NOT_COMMITTED"),
            (lambda: self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", "clm_00000000000000000000000000", "--path", "domain/topics/schema.md",
                              "--locator", "x", "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                              "--fact-class", "documented_contract", expected=1), "PLAN_CLAIM_MISSING"),
            (lambda: self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", first["claim_id"], "--path", "domain/topics/schema.md",
                              "--locator", "x", "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                              "--fact-class", "runtime_behavior", expected=1), "PLAN_FACT_COVERAGE"),
        ]
        (self.root / "untracked.md").write_text("working tree only\n", encoding="utf-8")
        for invoke, code in failures:
            failure = invoke()
            self.assertEqual(failure["errors"][0]["code"], code)
            if code == "PLAN_CLAIM_MISSING":
                self.assertIn(f".local/pkc/semantic-plans/{plan_id}.json", failure["errors"][0]["message"])
                self.assertIn("'claims'", failure["errors"][0]["message"])
            self.assertEqual(self.formal_authority(), self.authority_before)

        public_plan = self.cli("knowledge-plan", "init", "--intent", "Permission expansion", "--risk", "high")["plan_id"]
        denied = self.cli("knowledge-plan", "add-claim", public_plan, "--node", "software-core", "--topic-id", "topic-runtime",
                          "--title", "Public runtime", "--statement", "This attempts public expansion.", "--boundary", "None.",
                          "--permission", "public", "--fact-class", "runtime_behavior", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_PERMISSION_EXPANSION")
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_missing_fact_class_dirty_authority_and_stale_baseline_fail_closed(self):
        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "runtime", "Runtime baseline", "Runtime bytes are committed.", ("runtime_behavior",))["claim_id"]
        missing = self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-schema",
                           "--title", "No facts", "--statement", "Missing facts.", "--boundary", "None.", expected=1)
        self.assertEqual(missing["errors"][0]["code"], "PLAN_FACT_CLASS_REQUIRED")
        authority = self.root / "authority/runtime-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")
        dirty = self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", claim, "--path", "authority/runtime-contract.md",
                         "--locator", "x", "--role", "current_implementation", "--change-policy", "invalidate_on_change",
                         "--fact-class", "runtime_behavior", expected=1)
        self.assertEqual(dirty["errors"][0]["code"], "PLAN_AUTHORITY_WORKTREE_DIRTY")
        self.assertIn("restore the committed baseline, commit it and start a new plan", dirty["errors"][0]["message"])
        subprocess.run(["git", "checkout", "--", "authority/runtime-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-qm", "advance baseline"], cwd=self.root, check=True)
        stale = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual(stale["state"], "open")
        failed = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta", expected=1)
        self.assertEqual(failed["errors"][0]["code"], "PLAN_STALE_BASELINE")
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_inspect_abandon_and_interruption_leave_authority_unchanged(self):
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "validation", "Interrupted plan", "The operation remains only in the local overlay.", ("cli_behavior",))
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual(inspected["operation_count"], 1)
        self.assertTrue(all(path.startswith(".local/") for path in [f".local/pkc/semantic-plans/{plan_id}.json"]))
        abandoned = self.cli("knowledge-plan", "abandon", plan_id, "--reason", "Contract interruption test")
        self.assertEqual(abandoned["state"], "abandoned")
        self.assertEqual(self.formal_authority(), self.authority_before)
        denied = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_NOT_OPEN")
        restarted = self.cli("knowledge-plan", "init", "--intent", "Add neutral software contracts", "--risk", "medium", expected=1)
        self.assertEqual(restarted["errors"][0]["code"], "PLAN_ABANDONED")
        self.assertIn(plan_id, restarted["errors"][0]["message"])
        self.assertIn("different intent", restarted["errors"][0]["message"])

    def test_finalize_requires_delta_and_tampered_provenance_fails_closed(self):
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Provenance contract", "Provenance is bound to canonical action bytes.", ("documented_contract",))
        denied = self.cli("knowledge-plan", "finalize", plan_id, expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_DELTA_REQUIRED")
        self.add_ref(plan_id, self.cli("knowledge-plan", "inspect", plan_id)["plan_id"] if False else
                     json.loads(next((self.root / ".local/pkc/semantic-plans").glob("*.json")).read_text())["operations"][0]["claim_id"],
                     "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle_path = self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["actions"][0]["provenance"]["operation_digest"] = "0" * 64
        body = {key: value for key, value in bundle.items() if key not in {"bundle_id", "content_hash"}}
        from portable_knowledge.bundle import digest
        bundle["content_hash"] = digest(body); bundle["bundle_id"] = f"bnd_{bundle['content_hash'][:26]}"
        tampered_path = self.root / "data/knowledge/bundles" / f"{bundle['bundle_id']}.json"
        tampered_path.write_text(json.dumps(bundle), encoding="utf-8")
        rejected = self.cli("bundle-approve", bundle["bundle_id"], "--content-hash", bundle["content_hash"], expected=1)
        self.assertIn(rejected["errors"][0]["code"], {"BUNDLE_PROVENANCE_MISMATCH", "KNOWLEDGE_ERROR"})
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_exact_hash_approve_apply_post_full_recover_and_rollback(self):
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        before = self.formal_authority()
        wrong = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", "0" * 64, "--apply", expected=1)
        self.assertIn("exact content hash", wrong["errors"][0]["message"])
        self.assertEqual(self.formal_authority(), before)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        applied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.assertTrue(applied["post_apply_full_receipt"]["ok"])
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        counters = inspected["cost_counters"]
        self.assertEqual((counters["delta_checks"], counters["full_checks"], counters["full_preflight_checks"], counters["post_apply_full_checks"]), (1, 2, 1, 1))
        self.assertTrue(self.cli("bundle-recover", finalized["bundle_id"])["ok"])
        rolled = self.cli("bundle-rollback", finalized["bundle_id"], "--apply")
        self.assertTrue(rolled["ok"])
        self.assertEqual(self.formal_authority(), before)

    def test_concurrent_baseline_and_worktree_drift_fail_before_approval_or_apply(self):
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        preview = self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]
        self.assertIn(preview["health"], {"PASS", "PASS_WITH_REVIEW"})
        before = self.formal_authority()
        topic = self.root / "domain/topics/schema.md"
        topic.write_text(topic.read_text(encoding="utf-8") + "concurrent\n", encoding="utf-8")
        denied = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply", expected=1)
        self.assertIn(denied["errors"][0]["code"], {"PLAN_WORKTREE_DRIFT", "BUNDLE_PROVENANCE_MISMATCH"})
        subprocess.run(["git", "checkout", "--", "domain/topics/schema.md"], cwd=self.root, check=True)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        (self.root / "authority/schema-contract.md").write_text("uncommitted authority drift\n", encoding="utf-8")
        denied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_AUTHORITY_WORKTREE_DIRTY")
        subprocess.run(["git", "checkout", "--", "authority/schema-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-qm", "advance committed baseline"], cwd=self.root, check=True)
        denied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_STALE_BASELINE")
        self.assertEqual(self.formal_authority(), before)

    def test_missing_finalized_artifact_and_plan_tamper_fail_closed(self):
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        before = self.formal_authority()
        artifact = self.root / finalized["artifact_path"]
        artifact.unlink()
        denied = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_FINALIZED_ARTIFACT_MISSING")
        self.assertEqual(self.formal_authority(), before)
        # Restore the artifact, then forge an operation while retaining the old finalized identity.
        artifact.write_text("{}\n", encoding="utf-8")
        plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["operations"][0]["input"]["title"] = "forged"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        denied = self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_PROVENANCE_MISMATCH")
        self.assertEqual(self.formal_authority(), before)

    def test_camel_case_evaluation_contract_is_shared_by_check_delta_and_finalize(self):
        baseline_plan, _, _ = self.build_complete_plan()
        baseline = self.cli("knowledge-plan", "finalize", baseline_plan)
        self.cli("bundle-approve", baseline["bundle_id"], "--content-hash", baseline["content_hash"], "--apply")
        self.cli("bundle-apply", baseline["bundle_id"], "--content-hash", baseline["content_hash"], "--apply")
        self.cli("rebuild")
        subprocess.run(["git", "add", "data/store", "domain/topics"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "governed evaluation baseline"], cwd=self.root, check=True)

        fixture_path = self.root / "evaluation/cases-v1.json"
        fixture_path.write_text(json.dumps({
            "schemaVersion": 1,
            "defaults": {"topicTopN": 3, "claimTopN": 5, "permission": "internal"},
            "cases": [{
                "id": "camel-schema",
                "query": "Schema Contract",
                "expectedTopicIds": ["topic-schema"],
                "searchTerms": ["explicit versioned fields"],
            }],
        }), encoding="utf-8")
        subprocess.run(["git", "add", "evaluation/cases-v1.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "camel case evaluation fixture"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()
        self.assertEqual(self.cli("knowledge-check")["status"], "PASS")

        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Additional schema boundary",
                               "Additional schema behavior remains deterministic.", ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        self.assertTrue(delta["can_finalize"])
        self.assertEqual(delta["affected_case_ids"], ["camel-schema"])
        artifact = json.loads((self.root / delta["artifact_path"]).read_text(encoding="utf-8"))
        self.assertEqual(artifact["records"][0]["expected_topic_ids"], ["topic-schema"])
        self.assertEqual(artifact["records"][0]["terms"], ["explicit versioned fields"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertTrue(finalized["summary"]["finalized"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_conflicting_evaluation_aliases_fail_with_structured_cli_error(self):
        fixture_path = self.root / "evaluation/cases-v1.json"
        fixture_path.write_text(json.dumps({
            "schema_version": 1,
            "schemaVersion": 2,
            "cases": [],
        }), encoding="utf-8")
        plan_id = self.init()["plan_id"]
        failed = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta", expected=1)
        error = failed["errors"][0]
        self.assertEqual(error["code"], "PLAN_EVALUATION_SCHEMA")
        self.assertEqual(error["path"], "evaluation/cases-v1.json")
        self.assertIn("conflicting evaluation aliases", error["message"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_alternate_terms_claim_and_forbidden_assertions_share_cli_semantics(self):
        plan_id = self.init()["plan_id"]
        expected = self.add_claim(plan_id, "schema", "Alternate vocabulary",
                                  "Load bearing alternate token zephyrquartz identifies this contract.",
                                  ("documented_contract",))["claim_id"]
        forbidden = self.add_claim(plan_id, "runtime", "Tempting unrelated result",
                                   "A different runtime statement must remain outside the bounded result.",
                                   ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, expected, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.add_ref(plan_id, forbidden, "runtime", "authority/runtime-contract.md", "documented_contract", "documented_contract")
        fixture_path = self.root / "evaluation/cases-v1.json"
        fixture_path.write_text(json.dumps({
            "schemaVersion": 1,
            "defaults": {"topicTopN": 3, "claimTopN": 5, "permission": "internal"},
            "cases": [{
                "id": "alternate-claim-refusal",
                "query": "words absent from all claims",
                "searchTerms": ["zephyrquartz"],
                "expectedTopicIds": ["topic-schema"],
                "expectedClaimIds": [expected],
                "mustNotClaimIds": ["clm_not_returned_fixture"],
            }],
        }), encoding="utf-8")
        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        record = json.loads((self.root / delta["artifact_path"]).read_text(encoding="utf-8"))["records"][0]
        self.assertTrue(record["ok"])
        self.assertIn(expected, record["returned_claim_ids"])
        self.assertEqual(record["forbidden_claim_ids_encountered"], [])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        full = json.loads((self.root / finalized["artifact_path"]).read_text(encoding="utf-8"))
        full_record = full["records"]["evaluation_records"][0]
        self.assertEqual(full_record["failed_assertions"], [])
        self.assertEqual(full_record["returned_claim_ids"], record["returned_claim_ids"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_full_evaluation_failure_is_actionable_and_fail_closed(self):
        plan_id, _, _ = self.build_complete_plan()
        fixture_path = self.root / "evaluation/cases-v1.json"
        # Finalize always evaluates the complete current fixture, even when a
        # case was not present at delta time.
        fixture_path.write_text(json.dumps({
            "schema_version": 1,
            "cases": [{
                "id": "deliberate-regression",
                "query": "Schema Contract",
                "expected_claim_ids": ["clm_missing_fixture"],
            }],
        }), encoding="utf-8")
        failed = self.cli("knowledge-plan", "finalize", plan_id, expected=1)
        finding = next(item for item in failed["errors"] if item["code"] == "PLAN_FULL_EVALUATION_FAILED")
        artifact_path = finding["artifact_path"]
        artifact = json.loads((self.root / artifact_path).read_text(encoding="utf-8"))
        record = artifact["records"]["evaluation_records"][0]
        self.assertEqual(record["failed_assertions"], ["expected_claim_missing"])
        self.assertIn("returned_claim_ids", record)
        self.assertEqual(finding["evaluator_contract_version"], 1)
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def _rewrite_evaluation_fixture(self, cases: list[dict]) -> None:
        (self.root / "evaluation/cases-v1.json").write_text(
            json.dumps({"schema_version": 1, "cases": cases}), encoding="utf-8")

    def test_post_apply_unrelated_failing_case_is_advisory_not_blocking(self):
        # R10: a blocking case whose affected_by is disjoint from the plan must not
        # block post-apply; it surfaces as a non-blocking warning instead.
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self._rewrite_evaluation_fixture([
            {"id": "eval-schema-v1", "query": "Schema Contract", "affected_by": {"topic_ids": ["topic-schema"]}},
            {"id": "eval-unrelated-regression", "query": "Schema Contract",
             "affected_by": {"topic_ids": ["topic-deployment"]},
             "expected_claim_ids": ["clm_missing_fixture"]},
        ])
        applied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.assertTrue(applied["ok"])
        self.assertTrue(applied["post_apply_full_receipt"]["ok"])
        warnings = applied["post_apply_full_receipt"]["authority_warnings"]
        advisory = [item for item in warnings if item.get("case_id") == "eval-unrelated-regression"]
        self.assertEqual(len(advisory), 1)
        self.assertFalse(advisory[0].get("blocking", True))
        self.assertEqual(advisory[0]["code"], "PLAN_EVALUATION_NON_BLOCKING")

    def test_post_apply_affected_failing_case_blocks_with_transaction_state_and_detail(self):
        # R10+R11: an affected failing case still blocks, but the error names the
        # transaction state (applied, not rolled back) and carries the ranking detail.
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self._rewrite_evaluation_fixture([
            {"id": "eval-schema-v1", "query": "Schema Contract", "affected_by": {"topic_ids": ["topic-schema"]},
             "expected_claim_ids": ["clm_missing_fixture"]},
        ])
        before = self.formal_authority()
        failed = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply", expected=1)
        state = next(item for item in failed["errors"] if item["code"] == "PLAN_POST_APPLY_TRANSACTION_STATE")
        self.assertTrue(state["applied"])
        self.assertFalse(state["rolled_back"])
        self.assertIn("NOT rolled back", state["message"])
        self.assertIn("bundle-status", state["message"])
        finding = next(item for item in failed["errors"] if item["code"] == "PLAN_POST_APPLY_EVALUATION_FAILED")
        self.assertEqual(finding["case_id"], "eval-schema-v1")
        self.assertEqual(finding["query"], "Schema Contract")
        self.assertEqual(finding["topic_top_n"], 3)
        self.assertEqual(finding["expected_claim_ids"], ["clm_missing_fixture"])
        self.assertIn("returned_topic_ids", finding)
        self.assertIn("failed_assertions", finding)
        # The transaction landed even though the gate failed.
        receipt = self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.applied.json"
        self.assertTrue(receipt.is_file())
        self.assertNotEqual(self.formal_authority(), before)

    def test_capture_repeated_topic_metadata_idempotent_and_conflict_rejected(self):
        # R12: batch capture tolerates an exact repeat of the first claim's topic metadata
        # for the same topic (idempotent strip) and rejects a conflicting repeat.
        draft = {
            "schema_version": 1,
            "intent": "Batch topic metadata rule",
            "risk": "medium",
            "claims": [
                {"id": "c1", "node": "software-core", "topic_id": "topic-batch-meta",
                 "topic_path": "domain/topics/batch-meta.md", "topic_title": "Batch Metadata",
                 "topic_summary": "Captures the topic-metadata-only-once rule.",
                 "topic_keywords": ["batch"], "duplicate_resolution": "create_distinct_with_boundary",
                 "title": "Batch metadata claim one", "statement": "First claim creates the topic with metadata.",
                 "boundary": "Neutral fixture.", "fact_classes": ["documented_contract"],
                 "authority_refs": [{"claim_id": "c1", "path": "authority/schema-contract.md",
                                     "locator": "schema", "role": "documented_contract",
                                     "change_policy": "invalidate_on_change", "fact_classes": ["documented_contract"]}]},
                {"id": "c2", "node": "software-core", "topic_id": "topic-batch-meta",
                 "topic_title": "Batch Metadata", "topic_summary": "Captures the topic-metadata-only-once rule.",
                 "topic_keywords": ["batch"],
                 "title": "Batch metadata claim two", "statement": "Second claim repeats identical metadata and is tolerated.",
                 "boundary": "Neutral fixture.", "fact_classes": ["documented_contract"],
                 "authority_refs": [{"claim_id": "c2", "path": "authority/runtime-contract.md",
                                     "locator": "runtime", "role": "documented_contract",
                                     "change_policy": "invalidate_on_change", "fact_classes": ["documented_contract"]}]},
            ],
        }
        draft_path = self.root / "DRAFT.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        captured = self.cli("knowledge-plan", "capture", "--file", "DRAFT.json")
        self.assertTrue(captured["ok"])
        self.assertEqual(len(captured["semantic_diff"]["claims_created"]), 2)
        # Conflicting repeat must fail with the exact draft field.
        draft["claims"][1]["topic_keywords"] = ["different"]
        draft["intent"] = "Batch topic metadata conflict"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        failed = self.cli("knowledge-plan", "capture", "--file", "DRAFT.json", expected=1)
        finding = next(item for item in failed["errors"] if item["code"] == "PLAN_TOPIC_METADATA_CONFLICT")
        self.assertEqual(finding["draft_field"], "claims[1]")
        self.assertIn("topic-batch-meta", finding["message"])

    def test_proposals_append_does_not_block_replay_and_preserves_appended_lines(self):
        # R13: appending an unrelated event to the shared proposals log after finalize must
        # not look like authority drift; idempotent replay applies and keeps the appended line.
        plan_id, _, _ = self.build_complete_plan()
        plan = json.loads(next((self.root / ".local/pkc/semantic-plans").glob("*.json")).read_text(encoding="utf-8"))
        ref = next(item for item in plan["authority_refs"] if item["path"] == "authority/schema-contract.md")
        self.cli("knowledge-plan", "update-authority-ref", plan_id, "--authority-ref-id", ref["id"],
                 "--path", "authority/runtime-contract.md", "--reason", "Re-point to runtime contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        staged = [path for path in finalized["changed_files"]
                  if path.startswith("data/store/proposals/") and path.endswith(".jsonl")]
        self.assertTrue(staged)
        target = self.root / staged[0]
        # The Bundle's own append event has landed (applied state), then an unrelated
        # operation appended one more line — that is the R13 drift false-positive scene.
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text(encoding="utf-8"))
        action = next(item for item in bundle["actions"] if item["path"] in staged)
        target.write_bytes(base64.b64decode(action["content"], validate=True))
        event = {"schema_version": 1, "actor": "owner-channel", "performed_by": "test-agent",
                 "event_id": "evt_" + "A" * 26, "event_type": "proposal_created", "proposal_id": "prp_" + "A" * 26,
                 "proposal_type": "test", "target_id": None, "summary": "unrelated appended event",
                 "rationale": "drift replay test", "status": "open", "created_at": "2026-08-29T00:00:00+00:00"}
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        applied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.assertTrue(applied["ok"])
        self.assertIn("unrelated appended event", target.read_text(encoding="utf-8"))

    def test_authority_ref_missing_names_uncommitted_worktree_cause(self):
        # R3 verification update: a Ref applied but not committed exists in the working tree
        # yet is invisible to a new plan's committed baseline; the error must say commit-first.
        plan_id, _, _ = self.build_complete_plan()
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        worktree_refs = json.loads((self.root / "data/store/authority-refs.json").read_text(encoding="utf-8"))
        added = [item for item in worktree_refs["refs"] if item["path"].startswith("authority/")]
        self.assertTrue(added)
        new_plan = self.cli("knowledge-plan", "init", "--intent", "Follow-up maintenance", "--risk", "medium")["plan_id"]
        failed = self.cli("knowledge-plan", "update-authority-ref", new_plan, "--authority-ref-id", added[0]["id"],
                          "--path", "authority/schema-contract.md", "--reason", "follow-up", expected=1)
        finding = failed["errors"][0]
        self.assertEqual(finding["code"], "PLAN_AUTHORITY_REF_MISSING")
        self.assertTrue(finding.get("working_tree_visible"))
        self.assertFalse(finding.get("committed_baseline_visible"))
        self.assertIn("uncommitted", finding["message"])
        self.assertIn("recommended_action", finding)

    def test_delta_affected_cases_compact_stdout_and_finalize_receipt_reuse(self):
        plan_id, _, delta = self.build_complete_plan()
        self.assertEqual(delta["affected_case_ids"], ["eval-schema-v1", "eval-runtime-v1", "eval-validation-v1"])
        self.assertEqual(delta["failed_case_ids"], [])
        self.assertGreater(delta["cost_counters"]["semantic_amplification"], 0)
        self.assertLessEqual(len(json.dumps(delta, ensure_ascii=False, separators=(",", ":"))), 4096)
        artifact = json.loads((self.root / delta["artifact_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(artifact["records"]), 3)
        first = self.cli("knowledge-plan", "finalize", plan_id)
        second = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertEqual(first["artifact_path"], second["artifact_path"])
        self.assertEqual(second["cost_counters"]["candidate_bundles"], 1)
        self.assertEqual(second["cost_counters"]["full_preflight_checks"], 1)
        self.assertNotIn("bundle", first)

    def test_delta_failure_does_not_consume_full_preflight_and_new_claim_apply_is_closed(self):
        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Coverage budget", "Coverage is required before finalize.", ("documented_contract",))["claim_id"]
        failed = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta", expected=1)
        self.assertFalse(failed["summary"]["can_finalize"])
        self.assertEqual(failed["cost_counters"]["full_preflight_checks"], 0)
        self.assertEqual(failed["cost_counters"]["candidate_bundles"], 0)
        denied = self.cli("new-claim", "--node", "software-core", "--topic-id", "topic-runtime", "--title", "Legacy apply denied",
                          "--statement", "Normal legacy apply cannot write Claim authority.", "--boundary", "Neutral fixture.", "--apply", expected=1)
        self.assertIn("disabled", denied["errors"][0]["message"])
        self.assertEqual(self.formal_authority(), self.authority_before)
        self.assertTrue(claim.startswith("clm_"))

        # The pre-parser Python API remains a deliberate compatibility seam. It
        # lacks the switch entirely, unlike every normal CLI Namespace.
        legacy = argparse.Namespace(actor="owner-channel", node="software-core", topic_id="topic-runtime", topic_path=None,
                                    topic_title=None, topic_summary="", keywords=[], title="Legacy Python compatibility",
                                    statement="A direct Python caller remains compatible for recovery.", boundary="Neutral fixture only.",
                                    permission="internal", duplicate_resolution="cancel", apply=False)
        self.assertTrue(core.new_claim_command(self.root, legacy)["dry_run"])

    def test_all_stop_budgets_fail_before_extra_bundle_or_full_check(self):
        for counter, value in (("candidate_bundles", 2), ("full_preflight_checks", 1), ("tool_gap", 2), ("noop_actions", 1)):
            with self.subTest(counter=counter):
                if counter in {"tool_gap", "noop_actions"}:
                    plan_id = self.init()["plan_id"]
                else:
                    plan_id, _, _ = self.build_complete_plan()
                plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
                plan = json.loads(plan_path.read_text(encoding="utf-8")); plan["counters"][counter] = value
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                command = ("knowledge-plan", "check", plan_id, "--mode", "delta") if counter in {"tool_gap", "noop_actions"} else ("knowledge-plan", "finalize", plan_id)
                failed = self.cli(*command, expected=1)
                self.assertEqual(failed["errors"][0]["code"], "PLAN_BUDGET_EXCEEDED")
                self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
                self.assertEqual(self.formal_authority(), self.authority_before)
                shutil.rmtree(self.root / ".local", ignore_errors=True)

    def test_governed_move_topic_create_node_revise_apply_and_rollback(self):
        # Establish one governed Claim + Authority Ref, then commit that applied
        # authority as the immutable baseline for a maintenance plan.
        initial = self.init()["plan_id"]
        added = self.add_claim(initial, "schema", "Schema ownership", "Schema structures are authored manually.",
                               ("documented_contract",))
        self.add_ref(initial, added["claim_id"], "schema", "authority/schema-contract.md",
                     "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", initial, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", initial)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "governed claim baseline"], cwd=self.root, check=True)
        before = self.formal_authority()

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Separate reusable schema tooling", "--risk", "high")["plan_id"]
        moved = self.cli(
            "knowledge-plan", "move-topic", plan_id, "--topic-id", "topic-schema",
            "--to-node", "schema-toolchain", "--node-name", "Schema Toolchain",
            "--node-path", "domain/toolchain", "--node-boundary", "Reusable schema authoring contracts",
            "--node-keyword", "schema", "--to-path", "domain/toolchain/schema.md",
            "--reason", "The Topic lifecycle is broader than the software core.",
        )
        self.assertEqual(moved["moved_claim_ids"], [added["claim_id"]])
        revised = self.cli(
            "knowledge-plan", "revise-claim", plan_id, "--claim-id", added["claim_id"],
            "--title", "Schema ownership has a bounded automation exception",
            "--statement", "Schema structures remain authored assets, while verified static assembly may generate bounded structures.",
            "--boundary", "Static assembly still requires committed templates and identifiers.",
            "--semantic-declaration", "correct", "--reason", "Verified assembly narrows the manual-only wording.",
        )
        self.assertNotEqual(revised["before_hash"], revised["after_hash"])
        plan_value = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        with mock.patch.object(core, "content_hash", wraps=core.content_hash):
            overlay = base64.b64decode(plan_value["writes"]["domain/toolchain/schema.md"]).decode("utf-8")
        registry_overlay = json.loads(base64.b64decode(plan_value["writes"]["data/store/registry.json"]))
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary)
            shutil.copytree(self.root, staged, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".local"))
            (staged / "data/store/registry.json").write_bytes(base64.b64decode(plan_value["writes"]["data/store/registry.json"]))
            (staged / "domain/toolchain").mkdir(parents=True, exist_ok=True)
            (staged / "domain/toolchain/schema.md").write_text(overlay, encoding="utf-8")
            (staged / "domain/topics/schema.md").unlink()
            parsed = next(item for item in core.parse_claims(staged, registry_overlay)[0] if item["id"] == added["claim_id"])
        self.assertEqual(revised["after_hash"], parsed["content_hash"])
        delta = self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        self.assertTrue(delta["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle["bundle_type"], "knowledge_refactor")
        self.assertEqual({action["operation"] for action in bundle["actions"]}, {"replace", "delete"})
        provenance = {action["provenance"]["operation_type"] for action in bundle["actions"]}
        self.assertIn("semantic_overlay:move_topic", provenance)
        self.assertIn("semantic_overlay:revise_claim", provenance)
        self.assertEqual(self.formal_authority(), before)

        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        applied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.assertTrue(applied["post_apply_full_receipt"]["ok"])
        registry = json.loads((self.root / "data/store/registry.json").read_text(encoding="utf-8"))
        topic = next(item for item in registry["topics"] if item["id"] == "topic-schema")
        self.assertEqual((topic["node_id"], topic["path"]), ("schema-toolchain", "domain/toolchain/schema.md"))
        self.assertFalse((self.root / "domain/topics/schema.md").exists())
        self.assertTrue((self.root / "domain/toolchain/schema.md").is_file())
        self.assertTrue(self.cli("bundle-recover", finalized["bundle_id"])["ok"])
        rolled = self.cli("bundle-rollback", finalized["bundle_id"], "--apply")
        self.assertTrue(rolled["ok"])
        self.assertEqual(self.formal_authority(), before)

    def test_refresh_authority_ref_is_governed_audited_and_unblocks_stale_preflight(self):
        initial = self.init()["plan_id"]
        added = self.add_claim(initial, "runtime", "Refreshable runtime", "Runtime behavior follows the committed contract.",
                               ("runtime_behavior",))
        original = self.add_ref(initial, added["claim_id"], "runtime", "authority/runtime-contract.md",
                                "current_implementation", "runtime_behavior")
        self.cli("knowledge-plan", "check", initial, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", initial)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/runtime.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "governed runtime baseline"], cwd=self.root, check=True)

        authority = self.root / "authority/runtime-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "\nRefreshed behavior.\n", encoding="utf-8")
        subprocess.run(["git", "add", "authority/runtime-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change runtime authority"], cwd=self.root, check=True)
        before = self.formal_authority()

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Refresh changed runtime Authority", "--risk", "medium")["plan_id"]
        refreshed = self.cli("knowledge-plan", "refresh-authority-ref", plan_id,
                             "--authority-ref-id", original["authority_ref_id"],
                             "--reason", "Committed implementation changed and was reviewed.")
        self.assertEqual(refreshed["authority_ref_id"], original["authority_ref_id"])
        self.assertNotEqual(refreshed["old_approved_hash"], refreshed["new_approved_hash"])
        self.assertEqual(refreshed["affected_claim_ids"], [added["claim_id"]])
        self.assertEqual(self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]["affected_authority_refs"], [{
            "authority_ref_id": original["authority_ref_id"],
            "change": "refreshed",
            "path": "authority/runtime-contract.md",
            "old_hash": refreshed["old_approved_hash"],
            "new_hash": refreshed["new_approved_hash"],
            "linked_claim_ids": [added["claim_id"]],
            "human_review_reason": "Committed implementation changed and was reviewed.",
        }])
        replay = self.cli("knowledge-plan", "refresh-authority-ref", plan_id,
                          "--authority-ref-id", original["authority_ref_id"],
                          "--reason", "Committed implementation changed and was reviewed.")
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.formal_authority(), before)
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text())
        refresh_diff = bundle["semantic_diff"]["authority_refs_refreshed"]
        self.assertEqual(refresh_diff, [{"authority_ref_id": original["authority_ref_id"],
                                         "old_hash": refreshed["old_approved_hash"],
                                         "new_hash": refreshed["new_approved_hash"],
                                         "affected_claim_ids": [added["claim_id"]]}])
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        refs = json.loads((self.root / "data/store/authority-refs.json").read_text())["refs"]
        current = next(ref for ref in refs if ref["id"] == original["authority_ref_id"])
        self.assertEqual(current["approved_hash"], refreshed["new_approved_hash"])
        events = [json.loads(line) for line in (self.root / "data/store/proposals" / f"{dt.datetime.now():%Y-%m}-owner-channel.jsonl").read_text().splitlines() if line]
        event = next(item for item in events if item["event_type"] == "authority_ref_refreshed")
        self.assertEqual((event["old_approved_hash"], event["new_approved_hash"]),
                         (refreshed["old_approved_hash"], refreshed["new_approved_hash"]))

    def test_refresh_authority_ref_rejects_missing_noop_and_dirty_sources(self):
        missing_plan = self.init()["plan_id"]
        missing = self.cli("knowledge-plan", "refresh-authority-ref", missing_plan,
                           "--authority-ref-id", "aref_missing", "--reason", "Review missing Ref.", expected=1)
        self.assertEqual(missing["errors"][0]["code"], "PLAN_AUTHORITY_REF_MISSING")

        initial = self.init()["plan_id"]
        added = self.add_claim(initial, "runtime", "Refresh guards", "Runtime guards use committed Authority.",
                               ("runtime_behavior",))
        original = self.add_ref(initial, added["claim_id"], "runtime-guards", "authority/runtime-contract.md",
                                "current_implementation", "runtime_behavior")
        self.cli("knowledge-plan", "check", initial, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", initial)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/runtime.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "refresh guard baseline"], cwd=self.root, check=True)

        noop_plan = self.cli("knowledge-plan", "init", "--intent", "Reject Authority no-op", "--risk", "low")["plan_id"]
        noop = self.cli("knowledge-plan", "refresh-authority-ref", noop_plan,
                        "--authority-ref-id", original["authority_ref_id"], "--reason", "No source change.", expected=1)
        self.assertEqual(noop["errors"][0]["code"], "PLAN_STRUCTURE_NOOP")

        authority = self.root / "authority/runtime-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "\nCommitted change.\n", encoding="utf-8")
        subprocess.run(["git", "add", "authority/runtime-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change guarded authority"], cwd=self.root, check=True)
        dirty_plan = self.cli("knowledge-plan", "init", "--intent", "Reject dirty Authority refresh", "--risk", "medium")["plan_id"]
        authority.write_text(authority.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")
        dirty = self.cli("knowledge-plan", "refresh-authority-ref", dirty_plan,
                         "--authority-ref-id", original["authority_ref_id"], "--reason", "Review changed source.", expected=1)
        self.assertEqual(dirty["errors"][0]["code"], "PLAN_AUTHORITY_WORKTREE_DIRTY")

    def test_retire_authority_ref_requires_reason_and_replacement_and_preserves_audit(self):
        initial = self.init()["plan_id"]
        added = self.add_claim(initial, "schema", "Retirable schema authority", "Two contracts support this schema surface.",
                               ("documented_contract",))
        retiring = self.add_ref(initial, added["claim_id"], "schema-old", "authority/schema-contract.md",
                                "documented_contract", "documented_contract")
        replacement = self.add_ref(initial, added["claim_id"], "schema-new", "authority/validation-contract.md",
                                   "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", initial, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", initial)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "two Authority refs"], cwd=self.root, check=True)
        before = self.formal_authority()

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Retire superseded Authority", "--risk", "medium")["plan_id"]
        denied = self.cli("knowledge-plan", "retire-authority-ref", plan_id,
                          "--authority-ref-id", retiring["authority_ref_id"], "--reason", "Superseded.", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_AUTHORITY_REPLACEMENT_REQUIRED")
        retired = self.cli("knowledge-plan", "retire-authority-ref", plan_id,
                           "--authority-ref-id", retiring["authority_ref_id"],
                           "--replacement-authority-ref-id", replacement["authority_ref_id"],
                           "--reason", "The validation contract is now the canonical source.")
        self.assertEqual(retired["affected_claim_ids"], [added["claim_id"]])
        self.assertEqual(self.cli("knowledge-plan", "inspect", plan_id)["closeout_preview"]["affected_authority_refs"], [{
            "authority_ref_id": retiring["authority_ref_id"],
            "change": "retired",
            "path": "authority/schema-contract.md",
            "old_hash": retiring["approved_hash"],
            "new_hash": None,
            "linked_claim_ids": [added["claim_id"]],
            "human_review_reason": "The validation contract is now the canonical source.",
        }])
        replay = self.cli("knowledge-plan", "retire-authority-ref", plan_id,
                          "--authority-ref-id", retiring["authority_ref_id"],
                          "--replacement-authority-ref-id", replacement["authority_ref_id"],
                          "--reason", "The validation contract is now the canonical source.")
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.formal_authority(), before)
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text())
        self.assertEqual(bundle["bundle_type"], "authority_maintenance")
        self.assertEqual(bundle["semantic_diff"]["authority_refs_retired"][0]["replacement_authority_ref_id"],
                         replacement["authority_ref_id"])
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        refs = json.loads((self.root / "data/store/authority-refs.json").read_text())["refs"]
        self.assertNotIn(retiring["authority_ref_id"], {ref["id"] for ref in refs})
        events = [json.loads(line) for line in (self.root / "data/store/proposals" / f"{dt.datetime.now():%Y-%m}-owner-channel.jsonl").read_text().splitlines() if line]
        event = next(item for item in events if item["event_type"] == "authority_ref_retired")
        self.assertEqual(event["replacement_authority_ref_id"], replacement["authority_ref_id"])

    def test_batch_refresh_all_stale_refreshes_multiple_stale_refs(self):
        seed = self.init()["plan_id"]
        schema_claim = self.add_claim(seed, "schema", "Batch schema authority", "Schema batch target.", ("documented_contract",))["claim_id"]
        runtime_claim = self.add_claim(seed, "runtime", "Batch runtime authority", "Runtime batch target.", ("documented_contract",))["claim_id"]
        schema_ref = self.add_ref(seed, schema_claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        runtime_ref = self.add_ref(seed, runtime_claim, "runtime", "authority/runtime-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", seed, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", seed)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md", "domain/topics/runtime.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "batch authority baseline"], cwd=self.root, check=True)
        for rel in ("authority/schema-contract.md", "authority/runtime-contract.md"):
            path = self.root / rel
            path.write_text(path.read_text(encoding="utf-8") + f"\n{rel} changed.\n", encoding="utf-8")
            subprocess.run(["git", "add", rel], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change both authority sources"], cwd=self.root, check=True)

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Batch refresh stale Authority", "--risk", "medium")["plan_id"]
        batch = self.cli("knowledge-plan", "refresh-authority-ref", plan_id, "--all-stale", "--reason", "Committed sources changed and were reviewed.")
        self.assertEqual(batch["refreshed_count"], 2)
        self.assertEqual(batch["skipped_count"], 0)
        self.assertEqual({item["authority_ref_id"] for item in batch["refreshed"]},
                         {schema_ref["authority_ref_id"], runtime_ref["authority_ref_id"]})
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text())
        self.assertEqual(len(bundle["semantic_diff"]["authority_refs_refreshed"]), 2)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        refs = json.loads((self.root / "data/store/authority-refs.json").read_text())["refs"]
        for ref in refs:
            if ref["id"] in {schema_ref["authority_ref_id"], runtime_ref["authority_ref_id"]}:
                self.assertEqual(ref["approved_hash"], hashlib.sha256((self.root / ref["path"]).read_bytes()).hexdigest())

    def test_update_topic_metadata_governed_and_preserves_claims(self):
        seed = self.init()["plan_id"]
        claim = self.add_claim(seed, "schema", "Topic metadata target", "This claim survives a metadata-only topic update.", ("documented_contract",))["claim_id"]
        self.add_ref(seed, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", seed, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", seed)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "topic metadata baseline"], cwd=self.root, check=True)
        before_markdown = (self.root / "domain/topics/schema.md").read_text(encoding="utf-8")

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Retune schema Topic metadata", "--risk", "low")["plan_id"]
        updated = self.cli("knowledge-plan", "update-topic", plan_id, "--topic-id", "topic-schema",
                           "--title", "Schema Contract (CN)", "--summary", "中文可检索的 Schema 契约。",
                           "--keyword", "schema", "--keyword", "契约", "--alias", "契约规范",
                           "--reason", "Improve Chinese retrieval.")
        self.assertEqual(updated["topic_id"], "topic-schema")
        self.assertEqual(updated["changed_fields"], ["title", "summary", "keywords", "aliases"])
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text())
        self.assertEqual(bundle["bundle_type"], "knowledge_structure_change")
        self.assertEqual(bundle["semantic_diff"]["topics_updated"][0]["topic_id"], "topic-schema")
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        registry = json.loads((self.root / "data/store/registry.json").read_text())
        topic = next(item for item in registry["topics"] if item["id"] == "topic-schema")
        self.assertEqual(topic["title"], "Schema Contract (CN)")
        self.assertEqual(topic["summary"], "中文可检索的 Schema 契约。")
        self.assertEqual(topic["aliases"], ["契约规范"])
        markdown = (self.root / "domain/topics/schema.md").read_text(encoding="utf-8")
        self.assertTrue(markdown.startswith("# Schema Contract (CN)\n\n中文可检索的 Schema 契约。"))
        self.assertIn(f"<!-- CLAIM:START {claim}", markdown)
        self.assertIn(before_markdown.split("<!-- CLAIM:START")[1], markdown)

    def test_update_authority_ref_repoints_path_and_recomputes_hash(self):
        seed = self.init()["plan_id"]
        claim = self.add_claim(seed, "schema", "Re-point authority", "This claim follows its Authority file.", ("documented_contract",))["claim_id"]
        original = self.add_ref(seed, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", seed, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", seed)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "re-point baseline"], cwd=self.root, check=True)

        plan_id = self.cli("knowledge-plan", "init", "--intent", "Re-point schema Authority to validation contract", "--risk", "medium")["plan_id"]
        updated = self.cli("knowledge-plan", "update-authority-ref", plan_id,
                           "--authority-ref-id", original["authority_ref_id"],
                           "--path", "authority/validation-contract.md", "--locator", "validation contract",
                           "--reason", "The rule now lives in the validation contract.")
        self.assertEqual(updated["old_path"], "authority/schema-contract.md")
        self.assertEqual(updated["new_path"], "authority/validation-contract.md")
        new_hash = hashlib.sha256((self.root / "authority/validation-contract.md").read_bytes()).hexdigest()
        self.assertEqual(updated["new_approved_hash"], new_hash)
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text())
        self.assertEqual(bundle["bundle_type"], "authority_maintenance")
        self.assertEqual(bundle["semantic_diff"]["authority_refs_updated"][0]["new_path"], "authority/validation-contract.md")
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        refs = json.loads((self.root / "data/store/authority-refs.json").read_text())["refs"]
        current = next(ref for ref in refs if ref["id"] == original["authority_ref_id"])
        self.assertEqual(current["path"], "authority/validation-contract.md")
        self.assertEqual(current["approved_hash"], new_hash)

    def test_finalize_ignores_unrelated_and_non_blocking_and_deferred_failing_cases(self):
        plan_id, _, _ = self.build_complete_plan()
        fixture_path = self.root / "evaluation/cases-v1.json"
        fixture_path.write_text(json.dumps({
            "schema_version": 1,
            "cases": [
                {"id": "unrelated-fail", "query": "Schema Contract", "affected_by": {"topic_ids": ["topic-deployment"]},
                 "expected_claim_ids": ["clm_missing_fixture"]},
                {"id": "advisory-fail", "query": "Schema Contract", "affected_by": {"topic_ids": ["topic-schema"]},
                 "expected_claim_ids": ["clm_missing_fixture"], "blocking": False},
                {"id": "deferred-fail", "query": "Schema Contract", "affected_by": {"topic_ids": ["topic-schema"]},
                 "expected_claim_ids": ["clm_missing_fixture"]},
            ],
        }), encoding="utf-8")
        finalized = self.cli("knowledge-plan", "finalize", plan_id, "--defer-evaluation", "deferred-fail")
        self.assertTrue(finalized["summary"]["finalized"])
        self.assertIn("advisory-fail", {item["case_id"] for item in finalized["warnings"]})
        full = json.loads((self.root / finalized["artifact_path"]).read_text(encoding="utf-8"))
        selections = full["records"]["case_selection"]
        self.assertIn({"case_id": "deferred-fail", "decision": "deferred_user", "reason": "explicit_defer_evaluation"}, selections)
        self.assertIn({"case_id": "unrelated-fail", "decision": "deferred", "reason": "explicit_scope_unaffected"}, selections)

    def test_overlay_sparse_copy_skips_unrelated_root_files(self):
        from portable_knowledge import semantic_plan
        transient = self.root / "tmp-transient.ts"
        transient.write_text("// transient build artifact\n", encoding="utf-8")
        unrelated = self.root / "unrelated-cache.bin"
        unrelated.write_bytes(b"\x00" * 4096)
        instance = core.load_instance(self.root)
        plan_id = self.init()["plan_id"]
        _, plan = semantic_plan._load(self.root, instance, plan_id)
        temporary, staging = semantic_plan._with_overlay(self.root, instance, plan)
        try:
            self.assertTrue((staging / "project-intelligence.json").is_file())
            self.assertTrue((staging / "data/store/registry.json").is_file())
            self.assertTrue((staging / "data/store/actors.json").is_file())
            self.assertTrue((staging / "domain/topics/schema.md").is_file())
            self.assertTrue((staging / "evaluation/cases-v1.json").is_file())
            self.assertFalse((staging / "tmp-transient.ts").exists())
            self.assertFalse((staging / "unrelated-cache.bin").exists())
        finally:
            temporary.cleanup()
        # After adding an Authority Ref, its source file is part of the sparse overlay.
        claim = self.add_claim(plan_id, "schema", "Overlay authority", "Authority source is copied into staging.", ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        _, plan = semantic_plan._load(self.root, instance, plan_id)
        temporary, staging = semantic_plan._with_overlay(self.root, instance, plan)
        try:
            self.assertTrue((staging / "authority/schema-contract.md").is_file())
        finally:
            temporary.cleanup()


    def test_low_level_manifest_requires_explicit_compatibility_mode(self):
        manifest = {"bundle_type": "claim_create", "intent": "Low-level compatibility test", "semantic_diff": {"before": "same", "after": "same"},
                    "evidence_refs": [], "authority_refs": [], "permission_effect": "none", "risk": "low",
                    "actions": [{"operation": "replace", "path": "domain/topics/schema.md",
                                 "content": (self.root / "domain/topics/schema.md").read_text(encoding="utf-8")}]}
        path = self.root / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8")
        denied = self.cli("bundle-create", "--manifest", "manifest.json", expected=1)
        self.assertIn("provenance", denied["errors"][0]["message"])
        allowed = self.cli("bundle-create", "--manifest", "manifest.json", "--compatibility-mode")
        self.assertFalse(allowed["applied"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_rebase_recovers_stale_baseline_without_replay(self):
        plan_id = self.init()["plan_id"]
        added = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "note.md").write_text("Committed after init.\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/note.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "unrelated docs commit"], cwd=self.root, check=True)
        stale = self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-schema",
                         "--title", "Blocked by staleness", "--statement", "This must not land.", "--boundary", "Neutral fixture only.",
                         "--fact-class", "documented_contract", expected=1)
        self.assertEqual(stale["errors"][0]["code"], "PLAN_STALE_BASELINE")
        self.assertIn("rebase", stale["errors"][0]["message"])
        rebased = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Unrelated docs commit moved HEAD")
        self.assertEqual(rebased["plan_id"], plan_id)
        self.assertEqual(rebased["baseline_commit"],
                         subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, text=True, capture_output=True).stdout.strip())
        self.assertEqual(rebased["rebase_count"], 1)
        plan_value = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(plan_value["rebase_history"][0]["from"], rebased["old_baseline_commit"])
        self.assertEqual(plan_value["delta"], None)
        self.add_ref(plan_id, added["claim_id"], "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        noop = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Already current.", expected=1)
        self.assertEqual(noop["errors"][0]["code"], "PLAN_REBASE_NOOP")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])

    def test_rebase_rejects_plan_referenced_authority_changes(self):
        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        authority = self.root / "authority/schema-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "\nChanged after ref.\n", encoding="utf-8")
        subprocess.run(["git", "add", "authority/schema-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change referenced authority"], cwd=self.root, check=True)
        failed = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Try anyway.", expected=1)
        self.assertEqual(failed["errors"][0]["code"], "PLAN_REBASE_CONFLICT")
        self.assertIn("authority/schema-contract.md", failed["errors"][0]["message"])
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_rebase_rejects_missing_reason_and_approved_finalized_plan(self):
        plan_id = self.init()["plan_id"]
        missing = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "", expected=1)
        self.assertEqual(missing["errors"][0]["code"], "PLAN_INPUT_INVALID")
        claim = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        # A finalized-but-not-applied plan with an unchanged baseline is a no-op rebase,
        # not an immutability error: the operator can re-anchor once HEAD moves.
        noop = self.cli("knowledge-plan", "rebase", finalized["plan_id"], "--reason", "Baseline unchanged.", expected=1)
        self.assertEqual(noop["errors"][0]["code"], "PLAN_REBASE_NOOP")
        # An approval record makes the plan truly immutable.
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        denied = self.cli("knowledge-plan", "rebase", finalized["plan_id"], "--reason", "Approved.", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_FINALIZED_IMMUTABLE")

    def test_rebase_reanchors_finalized_unapplied_plan_preserving_identity(self):
        plan_id = self.init()["plan_id"]
        claim_id = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                                  ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim_id, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        bundle_path = self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json"
        self.assertTrue(bundle_path.is_file())
        # Move HEAD with an unrelated commit, then rebase the finalized-but-unapplied plan.
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "note.md").write_text("Committed after finalize.\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/note.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "unrelated docs commit"], cwd=self.root, check=True)
        rebased = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Re-anchor before approval.")
        self.assertEqual(rebased["plan_id"], plan_id)
        self.assertTrue(rebased["un_finalized"])
        plan_value = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(plan_value["state"], "open")
        self.assertIsNone(plan_value["finalized_bundle"])
        self.assertEqual(plan_value["operations"][0]["claim_id"], claim_id)
        self.assertEqual(plan_value["claims"][claim_id]["claim_id"], claim_id)
        self.assertEqual(plan_value["claims"][claim_id]["title"], "Schema input is explicit")
        # The stale immutable Bundle artifact is removed so it cannot be approved.
        self.assertFalse(bundle_path.exists())
        # Operations and Claim identity survive; the plan can be re-finalized on the new baseline.
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        refinalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertTrue(refinalized["summary"]["finalized"])
        self.assertNotEqual(refinalized["bundle_id"], finalized["bundle_id"])
        self.assertEqual(self.cli("knowledge-plan", "inspect", plan_id)["claims"][0]["claim_id"], claim_id)

    def _establish_committed_ref(self, *, change_source: bool = True) -> dict:
        """Commit one Authority Ref; optionally also commit a change of its source on a new
        commit so the registry no longer approves the source hash. Returns the Ref summary."""
        plan_a = self.cli("knowledge-plan", "init", "--intent", "Establish schema authority", "--risk", "medium")["plan_id"]
        added = self.add_claim(plan_a, "schema", "Schema authority", "Schema contracts are authoritative.", ("documented_contract",))
        original = self.add_ref(plan_a, added["claim_id"], "schema", "authority/schema-contract.md",
                                "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_a, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", plan_a)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "establish schema authority"], cwd=self.root, check=True)
        if change_source:
            self._change_committed_authority_source()
        return original

    def _change_committed_authority_source(self) -> None:
        authority = self.root / "authority/schema-contract.md"
        authority.write_text(authority.read_text(encoding="utf-8") + "\nMaintained behavior.\n", encoding="utf-8")
        subprocess.run(["git", "add", "authority/schema-contract.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "change schema authority source"], cwd=self.root, check=True)

    def _apply_uncommitted_maintenance(self, ref: dict) -> dict:
        """Finalize, approve, and apply a maintenance Bundle that refreshes the Ref, leaving the
        working-tree registry modified WITHOUT a commit. Returns the refresh summary."""
        maintenance = self.cli("knowledge-plan", "init", "--intent", "Refresh schema Authority", "--risk", "medium")["plan_id"]
        refreshed = self.cli("knowledge-plan", "refresh-authority-ref", maintenance,
                             "--authority-ref-id", ref["authority_ref_id"],
                             "--reason", "Committed source changed and was reviewed.")
        self.assertTrue(self.cli("knowledge-plan", "check", maintenance, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", maintenance)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        status = subprocess.run(["git", "status", "--porcelain", "--", "data/store/authority-refs.json"],
                                cwd=self.root, text=True, capture_output=True).stdout
        self.assertTrue(status.startswith(" M "))
        return refreshed

    def test_maintenance_applied_uncommitted_rebase_finalize_and_inspect_diagnose_snapshot_expiry(self):
        """Issue #2: with HEAD unchanged but the working-tree registry refreshed by an applied
        (uncommitted) maintenance Bundle, rebase/check/finalize return the commit-then-abandon
        recovery path instead of PLAN_REBASE_NOOP or refresh-advice, and inspect distinguishes
        the worktree-refreshed state from never-refreshed debt."""
        original = self._establish_committed_ref()
        # The old open plan is created at the current HEAD and depends on the snapshot.
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Old snapshot dependent plan", "--risk", "medium")["plan_id"]
        claim = self.add_claim(plan_id, "runtime", "Runtime contract", "Runtime follows the committed schema contract.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "runtime", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        plan_path = self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json"
        plan_value = json.loads(plan_path.read_text(encoding="utf-8"))
        baseline = plan_value["baseline_commit"]

        refreshed = self._apply_uncommitted_maintenance(original)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, text=True, capture_output=True).stdout.strip()
        self.assertEqual(head, baseline)
        registry = json.loads((self.root / "data/store/authority-refs.json").read_text(encoding="utf-8"))
        current = next(ref for ref in registry["refs"] if ref["id"] == original["authority_ref_id"])
        self.assertEqual(current["approved_hash"], refreshed["new_approved_hash"])

        # rebase must not answer with the context-less PLAN_REBASE_NOOP.
        denied = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Maintenance was applied.", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")
        message = denied["errors"][0]["message"]
        for fragment in ("working tree", "plan snapshot", "commit", "knowledge-plan abandon", "abandon"):
            self.assertIn(fragment, message)
        self.assertEqual(denied["errors"][0]["uncommitted_paths"], ["data/store/authority-refs.json"])

        # check and finalize fail with the same single recovery path.
        for command in (("knowledge-plan", "check", plan_id, "--mode", "delta"),
                        ("knowledge-plan", "finalize", plan_id)):
            failed = self.cli(*command, expected=1)
            self.assertEqual(failed["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")
            self.assertIn("abandon", failed["errors"][0]["message"])

        # inspect distinguishes the worktree-refreshed state from never-refreshed debt.
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        affected = inspected["closeout_preview"]["affected_authority_refs"]
        external = next(item for item in affected if item["authority_ref_id"] == original["authority_ref_id"])
        self.assertEqual(external["change"], "worktree_refreshed_uncommitted")
        self.assertIn("not committed", external["human_review_reason"])
        maintenance_block = inspected["closeout_preview"]["authority_maintenance"]
        self.assertEqual(maintenance_block["snapshot_state"], "maintenance_uncommitted")
        self.assertEqual(maintenance_block["uncommitted_paths"], ["data/store/authority-refs.json"])
        self.assertIn("abandon", maintenance_block["recommended_action"])

        # The failed rebase did not mutate the snapshot, and the plan snapshot never absorbed
        # the uncommitted working-tree registry content.
        plan_value = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(plan_value["baseline_commit"], baseline)
        self.assertEqual(plan_value.get("rebase_history", []), [])
        snapshot_refs = json.loads(base64.b64decode(plan_value["writes"]["data/store/authority-refs.json"]).decode("utf-8"))["refs"]
        snapshot_ref = next(ref for ref in snapshot_refs if ref["id"] == original["authority_ref_id"])
        self.assertEqual(snapshot_ref["approved_hash"], original["approved_hash"])

        # The recovery path is executable without any further refresh: the human commits the
        # maintenance, then abandons and rebuilds the old-snapshot plan.
        subprocess.run(["git", "add", "data/store"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "authorize maintenance commit"], cwd=self.root, check=True)
        conflict = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Maintenance committed.", expected=1)
        self.assertEqual(conflict["errors"][0]["code"], "PLAN_REBASE_CONFLICT")
        abandoned = self.cli("knowledge-plan", "abandon", plan_id, "--reason", "Snapshot is stale after maintenance.")
        self.assertEqual(abandoned["state"], "abandoned")
        rebuilt = self.cli("knowledge-plan", "init", "--intent", "Rebuild on the new committed baseline", "--risk", "medium")["plan_id"]
        rebuilt_claim = self.add_claim(rebuilt, "schema", "Schema contract after maintenance",
                                       "Schema contracts are authoritative after maintenance.", ("documented_contract",))["claim_id"]
        self.add_ref(rebuilt, rebuilt_claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", rebuilt, "--mode", "delta")["can_finalize"])

    def test_maintenance_applied_uncommitted_with_moved_head_diagnoses_snapshot_expiry(self):
        """Issue #2: when the old plan predates the committed source change, rebase and finalize
        must name the uncommitted maintenance (commit then abandon/rebuild) instead of a generic
        PLAN_STALE_BASELINE or a refresh-the-refs conflict, and inspect flips the same Ref from
        never-refreshed to worktree-refreshed-uncommitted once the Bundle is applied."""
        # The old open plan predates the source change: its Ref approves the old hash.
        original = self._establish_committed_ref(change_source=False)
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Old snapshot dependent plan", "--risk", "medium")["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        self._change_committed_authority_source()

        # Before the maintenance is applied the committed debt reads as never-refreshed.
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        affected = inspected["closeout_preview"]["affected_authority_refs"]
        external = next(item for item in affected if item["authority_ref_id"] == original["authority_ref_id"])
        self.assertEqual(external["change"], "external_invalidated")
        self.assertIn("refresh the reference", external["human_review_reason"])

        # Apply the maintenance Bundle without committing: HEAD has moved since plan init and the
        # registry is now drifted in the working tree.
        self._apply_uncommitted_maintenance(original)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, text=True, capture_output=True).stdout.strip()
        plan_value = json.loads((self.root / ".local/pkc/semantic-plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
        self.assertNotEqual(head, plan_value["baseline_commit"])

        # rebase previously answered PLAN_REBASE_CONFLICT / finalize answered PLAN_STALE_BASELINE;
        # both now return the maintenance recovery path.
        denied = self.cli("knowledge-plan", "rebase", plan_id, "--reason", "Maintenance was applied.", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")
        self.assertIn("knowledge-plan abandon", denied["errors"][0]["message"])
        failed = self.cli("knowledge-plan", "finalize", plan_id, expected=1)
        self.assertEqual(failed["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")

        # The same Ref now reads as already refreshed in the working tree.
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        affected = inspected["closeout_preview"]["affected_authority_refs"]
        external = next(item for item in affected if item["authority_ref_id"] == original["authority_ref_id"])
        self.assertEqual(external["change"], "worktree_refreshed_uncommitted")
        self.assertEqual(inspected["closeout_preview"]["authority_maintenance"]["snapshot_state"], "maintenance_uncommitted")

    def test_finalized_plan_approval_is_blocked_while_maintenance_is_uncommitted(self):
        """Issue #2 safety: an already-finalized old plan cannot be re-finalized, approved, or
        applied while an uncommitted maintenance Bundle has refreshed the working-tree registry;
        its baseline-derived registry write would otherwise silently revert the maintenance."""
        original = self._establish_committed_ref(change_source=False)
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Old snapshot dependent plan", "--risk", "medium")["plan_id"]
        claim = self.add_claim(plan_id, "runtime", "Runtime contract", "Runtime follows the committed schema contract.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "runtime", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self._change_committed_authority_source()
        self._apply_uncommitted_maintenance(original)

        replay = self.cli("knowledge-plan", "finalize", plan_id, expected=1)
        self.assertEqual(replay["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")
        for command in (("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply"),
                        ("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")):
            denied = self.cli(*command, expected=1)
            self.assertEqual(denied["errors"][0]["code"], "PLAN_AUTHORITY_MAINTENANCE_UNCOMMITTED")
            self.assertIn("abandon", denied["errors"][0]["message"])

    def test_add_authority_ref_distinguishes_revised_from_missing_claim(self):
        first_plan = self.init()["plan_id"]
        first = self.add_claim(first_plan, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))
        self.add_ref(first_plan, first["claim_id"], "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.assertTrue(self.cli("knowledge-plan", "check", first_plan, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", first_plan)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain", "authority"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "apply first plan"], cwd=self.root, check=True)
        plan_id = self.init()["plan_id"]
        self.cli("knowledge-plan", "revise-claim", plan_id, "--claim-id", first["claim_id"],
                 "--title", "Schema input is explicit and versioned",
                 "--statement", "The schema parser accepts explicit versioned fields.",
                 "--boundary", "Only the committed neutral fixture is in scope.",
                 "--semantic-declaration", "clarify", "--reason", "Sharpen the title.")
        revised_hint = self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", first["claim_id"],
                                "--path", "authority/schema-contract.md", "--locator", "schema contract",
                                "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                                "--fact-class", "documented_contract", expected=1)
        self.assertEqual(revised_hint["errors"][0]["code"], "PLAN_CLAIM_REVISED_NEEDS_REFRESH")
        self.assertIn("refresh-authority-ref", revised_hint["errors"][0]["message"])
        missing = self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", "clm_ABSENT",
                           "--path", "authority/schema-contract.md", "--locator", "schema contract",
                           "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                           "--fact-class", "documented_contract", expected=1)
        self.assertEqual(missing["errors"][0]["code"], "PLAN_CLAIM_MISSING")

    def test_inspect_preview_lists_externally_invalidated_refs(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
        refs["refs"].append({"id": "aref_external_stale", "path": "authority/schema-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "0" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs_path.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", refs_path.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add externally stale fixture ref"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()
        plan_id = self.init()["plan_id"]
        inspected = self.cli_process("knowledge-plan", "inspect", plan_id)
        affected = inspected["closeout_preview"]["affected_authority_refs"]
        external = next(item for item in affected if item["authority_ref_id"] == "aref_external_stale")
        self.assertEqual(external["change"], "external_invalidated")
        self.assertEqual(external["scope"], "historical")
        self.assertFalse(external["blocking"])
        self.assertEqual(inspected["closeout_preview"]["authority_ref_counts"]["historical"], 1)
        maintenance = inspected["closeout_preview"]["authority_maintenance"]
        self.assertEqual(maintenance["historical_ref_ids"], ["aref_external_stale"])
        self.assertEqual(maintenance["historical_count"], 1)
        self.assertFalse(maintenance["blocking"])
        self.assertIn("separate authority-maintenance plan", maintenance["recommended_action"])
        self.assertEqual(external["old_hash"], "0" * 64)
        self.assertEqual(len(external["new_hash"]), 64)
        self.assertIn("outside this plan", external["human_review_reason"])

    def test_inspect_summary_and_text_output(self):
        plan_id = self.init()["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        inspected = self.cli("knowledge-plan", "inspect", plan_id)
        self.assertEqual([item["claim_id"] for item in inspected["claims"]], [claim])
        self.assertEqual(inspected["claims"][0]["title"], "Schema input is explicit")
        self.assertEqual(inspected["operations"][0]["operation_type"], "add_claim")
        self.assertEqual(inspected["authority_refs"][0]["path"], "authority/schema-contract.md")
        text = self.cli_text("knowledge-plan", "inspect", plan_id)
        self.assertIn("Claims:", text)
        self.assertIn("Baseline:", text)
        self.assertIn(claim, text)
        self.assertIn("add_authority_ref", text)
        self.assertIn("Closeout health:", text)

    def test_fact_class_enum_is_surfaced_in_cli_help(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        help_text = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                    "knowledge-plan", "add-claim", "--help"], cwd=PACKAGE, env=env,
                                   text=True, encoding="utf-8", capture_output=True).stdout
        for value in ("runtime_behavior", "public_type_surface", "cli_behavior", "documented_contract",
                      "external_game_evidence", "transform_defaults", "writeback_behavior", "evidence_scope"):
            self.assertIn(value, help_text)
        ref_help = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                   "knowledge-plan", "add-authority-ref", "--help"], cwd=PACKAGE, env=env,
                                  text=True, encoding="utf-8", capture_output=True).stdout
        for value in ("existence_only", "review_on_change", "invalidate_on_change", "manual_review"):
            self.assertIn(value, ref_help)

    def test_authority_ref_role_enum_is_surfaced_in_cli_help(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        help_text = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                    "knowledge-plan", "add-authority-ref", "--help"], cwd=PACKAGE, env=env,
                                   text=True, encoding="utf-8", capture_output=True).stdout
        for value in ("design_intent", "current_implementation", "documented_contract", "external_environment_behavior"):
            self.assertIn(value, help_text)
        self.assertIn("legal values", help_text)

    def test_plan_check_help_lists_mode_values(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        help_text = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                    "knowledge-plan", "check", "--help"], cwd=PACKAGE, env=env,
                                   text=True, encoding="utf-8", capture_output=True).stdout
        self.assertIn("--mode", help_text)
        self.assertIn("delta", help_text)
        self.assertIn("legal values", help_text)

    def test_capture_help_points_to_the_draft_format_contract(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        help_text = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                    "knowledge-plan", "capture", "--help"], cwd=PACKAGE, env=env,
                                   text=True, encoding="utf-8", capture_output=True).stdout
        self.assertIn("--file", help_text)
        self.assertIn("capture-draft-format.md", help_text)
        self.assertIn("--draft-format", help_text)
        self.assertIn("--preview-only", help_text)

    def test_invalid_enum_values_are_rejected_at_cli_parse_time(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        base = [sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                "knowledge-plan", "add-authority-ref", "plan_x", "--claim-id", "clm_x",
                "--path", "a.py", "--locator", "x"]
        cases = (
            base + ["--role", "not_a_role", "--change-policy", "existence_only", "--fact-class", "runtime_behavior"],
            base + ["--role", "design_intent", "--change-policy", "not_a_policy", "--fact-class", "runtime_behavior"],
            base + ["--role", "design_intent", "--change-policy", "existence_only", "--fact-class", "not_a_class"],
            [sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
             "knowledge-plan", "check", "plan_x", "--mode", "full"],
        )
        for argv in cases:
            completed = subprocess.run(argv, cwd=PACKAGE, env=env, text=True, encoding="utf-8", capture_output=True)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("invalid choice", completed.stderr)

    def test_init_worktree_baseline_accepts_uncommitted_authority_and_pins_snapshot(self):
        """T1/R3: --baseline worktree pins the working-tree authority snapshot at init and refuses later drift,
        while the snapshot itself reflects applied-but-uncommitted maintenance."""
        self._configure_authority_refs()
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.", ("documented_contract",))
        self.add_ref(plan_id, self.cli("knowledge-plan", "inspect", plan_id)["claims"][0]["claim_id"],
                     "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        # authority registry is now modified in the working tree but not committed
        plan2 = self.cli("knowledge-plan", "init", "--intent", "Second plan on uncommitted authority", "--risk", "low", "--baseline", "worktree")
        self.assertEqual(plan2["baseline_mode"], "worktree")
        self.assertIsNotNone(plan2.get("worktree_authority_hash"))
        # a mutation on the worktree-baseline plan succeeds (snapshot pinned at init, no committed-drift guard needed)
        self.add_claim(plan2["plan_id"], "runtime", "Runtime selection is deterministic", "The runtime selects the same implementation.", ("documented_contract",))

    def test_worktree_baseline_drift_after_init_fails_closed(self):
        """T1/R3: if the working-tree authority changes after a worktree-baseline plan is initialized, mutation is refused."""
        self._configure_authority_refs()
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.", ("documented_contract",))
        self.add_ref(plan_id, self.cli("knowledge-plan", "inspect", plan_id)["claims"][0]["claim_id"],
                     "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        plan2 = self.cli("knowledge-plan", "init", "--intent", "Worktree baseline plan", "--risk", "low", "--baseline", "worktree")
        # mutate the authority registry again after init (simulating another applied bundle)
        refs_path = self.root / "data/store/authority-refs.json"
        current = json.loads(refs_path.read_text(encoding="utf-8"))
        refs_path.write_text(json.dumps(current, indent=1) + "\n", encoding="utf-8")
        denied = self.cli("knowledge-plan", "add-claim", plan2["plan_id"], "--node", "software-core", "--topic-id", "topic-runtime",
                          "--title", "Runtime selection is deterministic", "--statement", "The runtime selects the same implementation.",
                          "--boundary", "Only the committed neutral fixture is in scope.", "--fact-class", "documented_contract",
                          expected=1)
        self.assertTrue(any(error["code"] == "PLAN_WORKTREE_SNAPSHOT_DRIFT" for error in denied["errors"]))

    def test_worktree_baseline_accepts_new_untracked_authority_doc(self):
        """Obstacle 1/5: --baseline worktree lets a plan reference a newly written,
        not-yet-committed design document as Authority and still pass delta/finalize."""
        self._configure_authority_refs()
        design = self.root / "authority/design-intent.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# Design intent\n\nThe schema parser accepts explicit versioned fields.\n", encoding="utf-8")
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Capture design intent with its own document",
                           "--risk", "low", "--baseline", "worktree")["plan_id"]
        claim = self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.",
                               ("documented_contract",))["claim_id"]
        self.add_ref(plan_id, claim, "schema", "authority/design-intent.md", "design_intent", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertTrue(finalized["ok"])
        self.assertEqual(finalized["bundle_id"][:4], "bnd_")

    def _configure_authority_refs(self) -> None:
        config_path = self.root / "project-intelligence.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config.setdefault("authority", {})["authority_refs"] = "data/store/authority-refs.json"
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        refs_path = self.root / "data/store/authority-refs.json"
        refs_path.write_text('{"schema_version": 1, "refs": []}\n', encoding="utf-8")
        subprocess.run(["git", "add", "project-intelligence.json", "data/store/authority-refs.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "configure authority refs"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()

    def test_finalize_warns_on_same_intent_existing_bundle(self):
        """T3/R6: finalize surfaces a non-blocking PLAN_INTENT_OVERLAP warning when another Bundle shares the intent."""
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.", ("documented_contract",))
        self.add_ref(plan_id, self.cli("knowledge-plan", "inspect", plan_id)["claims"][0]["claim_id"],
                     "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        # finalize a second plan with the same intent text but different risk (different plan_id, same intent)
        plan2 = self.cli("knowledge-plan", "init", "--intent", "Add neutral software contracts", "--risk", "low")
        self.add_claim(plan2["plan_id"], "runtime", "Runtime selection is deterministic", "The runtime selects the same implementation.", ("documented_contract",))
        self.add_ref(plan2["plan_id"], self.cli("knowledge-plan", "inspect", plan2["plan_id"])["claims"][0]["claim_id"],
                     "runtime", "authority/runtime-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan2["plan_id"], "--mode", "delta")
        finalized2 = self.cli("knowledge-plan", "finalize", plan2["plan_id"])
        self.assertTrue(any(warning.get("code") == "PLAN_INTENT_OVERLAP" for warning in finalized2.get("warnings", [])))

    def test_bundle_apply_suggests_commit_unit(self):
        """T2/R3: bundle-apply success returns a commit_suggestion (git add + message) so the operator commits before the next plan."""
        plan_id = self.init()["plan_id"]
        self.add_claim(plan_id, "schema", "Schema input is explicit", "The schema parser accepts explicit versioned fields.", ("documented_contract",))
        self.add_ref(plan_id, self.cli("knowledge-plan", "inspect", plan_id)["claims"][0]["claim_id"],
                     "schema", "authority/schema-contract.md", "documented_contract", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        applied = self.cli("bundle-apply", finalized["bundle_id"], "--content-hash", finalized["content_hash"], "--apply")
        suggestion = applied.get("commit_suggestion")
        self.assertIsNotNone(suggestion)
        self.assertIn("git_add", suggestion)
        self.assertIn("commit unit", suggestion["note"])
        self.assertIn("knowledge: apply", suggestion["git_commit_message"])

class CaptureContractTests(unittest.TestCase):
    """File-driven batch Claim capture: one command, typed semantics, fail-closed drafts."""

    LONG_STATEMENT = ("The schema parser accepts explicit versioned fields and rejects ambiguous input "
                      "deterministically while preserving stable identifiers across the committed neutral "
                      "fixture so that repeated captures of identical drafts produce identical reviewable "
                      "bundles without any automatic approval or application.")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "fixture"
        shutil.copytree(FIXTURE, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "neutral baseline"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *argv: str, expected: int = 0) -> dict:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = core.main(["--root", str(self.root), *argv])
        payload = json.loads(stream.getvalue())
        self.assertEqual(result, expected, payload)
        return payload

    def formal_authority(self) -> dict[str, bytes]:
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for base in (self.root / "data", self.root / "domain")
                for path in base.rglob("*") if path.is_file() and "data/knowledge/bundles/" not in path.relative_to(self.root).as_posix()}

    def write_draft(self, name: str, intent: str, claims: list[dict], risk: str = "medium") -> Path:
        draft = {"schema_version": 1, "intent": intent, "risk": risk, "claims": claims}
        path = self.root / name
        path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        return path

    def schema_claim(self, statement: str | None = None) -> dict:
        return {"id": "schema", "node": "software-core", "topic_id": "topic-schema",
                "title": "Schema input is explicit",
                "statement": statement or self.LONG_STATEMENT,
                "boundary": "Only the committed neutral fixture is in scope.",
                "fact_classes": ["documented_contract"],
                "authority_refs": [{"path": "authority/schema-contract.md", "locator": "schema contract",
                                    "role": "documented_contract", "change_policy": "invalidate_on_change",
                                    "fact_classes": ["documented_contract"]}]}

    def test_capture_long_claim_matches_interactive_plan_bundle(self):
        self.assertGreaterEqual(len(self.LONG_STATEMENT), 200)
        # The identical interactive typed sequence produces the same immutable Bundle.
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Capture equivalence draft", "--risk", "medium")["plan_id"]
        added = self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-schema",
                         "--title", "Schema input is explicit", "--statement", self.LONG_STATEMENT,
                         "--boundary", "Only the committed neutral fixture is in scope.", "--fact-class", "documented_contract")
        self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", added["claim_id"],
                 "--path", "authority/schema-contract.md", "--locator", "schema contract",
                 "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                 "--fact-class", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        interactive = self.cli("knowledge-plan", "finalize", plan_id)
        draft = self.write_draft("draft.json", "Capture equivalence draft", [self.schema_claim()])
        captured = self.cli("knowledge-plan", "capture", "--file", draft.name)
        self.assertEqual(captured["command"], "knowledge-plan capture")
        self.assertEqual(captured["plan_state"], "finalized")
        self.assertEqual(captured["plan_id"], plan_id)
        self.assertTrue(captured["bundle_id"].startswith("bnd_"))
        self.assertEqual(len(captured["content_hash"]), 64)
        self.assertEqual(captured["risk"], "medium")
        self.assertEqual(captured["permission_effect"], "none")
        self.assertEqual(captured["operation_count"], 2)
        self.assertEqual(len(captured["semantic_diff"]["claims_created"]), 1)
        self.assertEqual(len(captured["semantic_diff"]["authority_refs_added"]), 1)
        self.assertIn("data/store/authority-refs.json", captured["expected_changed_files"])
        self.assertIn("data/store/registry.json", captured["expected_changed_files"])
        self.assertIn("domain/topics/schema.md", captured["expected_changed_files"])
        self.assertFalse(captured["approved"]); self.assertFalse(captured["applied"])
        self.assertEqual(interactive["bundle_id"], captured["bundle_id"])
        self.assertEqual(interactive["content_hash"], captured["content_hash"])
        self.assertEqual(interactive["changed_files"], captured["expected_changed_files"])
        # Only the immutable draft Bundle artifact exists; formal authority is untouched.
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        self.assertFalse((self.root / "data/knowledge/bundles" / f"{captured['bundle_id']}.approval.json").exists())
        self.assertEqual(self.formal_authority(), self.authority_before)
        replay = self.cli("knowledge-plan", "capture", "--file", draft.name)
        self.assertEqual((replay["bundle_id"], replay["content_hash"]), (captured["bundle_id"], captured["content_hash"]))
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)

    def test_capture_batch_two_claims_single_command(self):
        second = {"id": "runtime", "node": "software-core", "topic_id": "topic-runtime",
                  "title": "Runtime selection is deterministic",
                  "statement": "The runtime selects the same implementation for the same input under identical conditions.",
                  "boundary": "Only the committed neutral fixture is in scope.",
                  "fact_classes": ["runtime_behavior", "documented_contract"],
                  "authority_refs": [
                      {"path": "authority/runtime-contract.md", "locator": "runtime contract",
                       "role": "current_implementation", "change_policy": "invalidate_on_change",
                       "fact_classes": ["runtime_behavior"]},
                      {"path": "authority/runtime-contract.md", "locator": "runtime contract",
                       "role": "documented_contract", "change_policy": "invalidate_on_change",
                       "fact_classes": ["documented_contract"]}]}
        draft = self.write_draft("batch.json", "Batch capture draft", [self.schema_claim(), second])
        captured = self.cli("knowledge-plan", "capture", "--file", draft.name)
        self.assertEqual(captured["operation_count"], 5)
        self.assertEqual(len(captured["semantic_diff"]["claims_created"]), 2)
        self.assertEqual(len(captured["semantic_diff"]["authority_refs_added"]), 3)
        self.assertEqual(captured["semantic_diff"]["operations"], 5)
        self.assertEqual(len(captured["expected_changed_files"]), 4)
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{captured['bundle_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle["bundle_type"], "claim_create")
        self.assertEqual(bundle["content_hash"], captured["content_hash"])
        self.assertEqual(self.formal_authority(), self.authority_before)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(core.main(["--root", str(self.root), "knowledge-plan", "capture", "--file", draft.name, "--format", "text"]), 0)
        text = stream.getvalue()
        self.assertIn(captured["bundle_id"], text)
        self.assertIn(captured["content_hash"], text)
        self.assertIn("Risk: medium", text)

    def test_capture_worktree_baseline_accepts_untracked_authority_doc(self):
        """Obstacle 4/5: one-command batch intake can opt into worktree baseline and
        reference a not-yet-committed design document as Authority."""
        design = self.root / "authority/design-intent.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# Design intent\n\nBatch capture may reference this uncommitted file.\n", encoding="utf-8")
        claim = self.schema_claim()
        claim["authority_refs"] = [{"path": "authority/design-intent.md", "locator": "design intent",
                                    "role": "design_intent", "change_policy": "invalidate_on_change",
                                    "fact_classes": ["documented_contract"]}]
        draft = self.write_draft("worktree-batch.json", "Batch worktree capture", [claim], risk="low")
        captured = self.cli("knowledge-plan", "capture", "--file", draft.name, "--baseline", "worktree")
        self.assertEqual(captured["command"], "knowledge-plan capture")
        self.assertEqual(captured["plan_state"], "finalized")
        self.assertTrue(captured["bundle_id"].startswith("bnd_"))
        self.assertEqual(len(captured["semantic_diff"]["claims_created"]), 1)
        self.assertEqual(len(captured["semantic_diff"]["authority_refs_added"]), 1)
        # draft baseline_mode field is also honored without the CLI flag
        draft2 = self.root / "worktree-batch-2.json"
        draft2.write_text(json.dumps({"schema_version": 1, "intent": "Batch worktree capture 2", "risk": "low",
                                      "baseline_mode": "worktree", "claims": [claim]}, indent=2) + "\n", encoding="utf-8")
        captured2 = self.cli("knowledge-plan", "capture", "--file", draft2.name)
        self.assertEqual(captured2["plan_state"], "finalized")
        self.assertTrue(captured2["bundle_id"].startswith("bnd_"))

    def test_capture_draft_schema_error_reports_field_and_creates_nothing(self):
        claim = self.schema_claim()
        claim["authority_refs"][0]["role"] = "not_a_role"
        draft = self.write_draft("bad-role.json", "Invalid role draft", [claim])
        failed = self.cli("knowledge-plan", "capture", "--file", draft.name, expected=1)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["plan_id"], None)
        self.assertEqual(failed["retained_plan"], None)
        error = failed["errors"][0]
        self.assertEqual(error["code"], "PLAN_DRAFT_INVALID")
        self.assertEqual(error["draft_field"], "claims[0].authority_refs[0].role")
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        self.assertEqual(list((self.root / ".local/pkc/semantic-plans").glob("*.json")), [])
        self.assertEqual(self.formal_authority(), self.authority_before)
        typo = self.schema_claim(); typo["fact_class"] = typo.pop("fact_classes")
        typo_draft = self.write_draft("typo.json", "Typo draft", [typo])
        typo_failed = self.cli("knowledge-plan", "capture", "--file", typo_draft.name, expected=1)
        self.assertEqual(typo_failed["errors"][0]["draft_field"], "claims[0].fact_class")
        self.assertIn("unknown claim field", typo_failed["errors"][0]["message"])

        target = self.schema_claim(); target["id"] = "target"
        target["authority_refs"] = []
        source = self.schema_claim(); source["id"] = "source"
        source["fact_classes"] = ["runtime_behavior"]
        source["authority_refs"][0]["claim_id"] = "target"
        source["authority_refs"][0]["fact_classes"] = ["runtime_behavior"]
        target_failed = self.cli("knowledge-plan", "capture", "--file",
                                 self.write_draft("target-facts.json", "Target fact mismatch", [source, target]).name,
                                 expected=1)
        self.assertEqual(target_failed["errors"][-1]["draft_field"], "claims[0].authority_refs[0].fact_classes")
        self.assertIn("target claim", target_failed["errors"][-1]["message"])

    def test_capture_operation_failure_abandons_plan_and_reports_reason(self):
        claim = self.schema_claim()
        claim["authority_refs"][0]["path"] = "authority/not-committed.md"
        draft = self.write_draft("bad-path.json", "Uncommitted authority draft", [claim])
        failed = self.cli("knowledge-plan", "capture", "--file", draft.name, expected=1)
        self.assertFalse(failed["ok"])
        self.assertTrue(failed["plan_id"].startswith("pln_"))
        self.assertEqual(failed["errors"][0]["code"], "PLAN_AUTHORITY_NOT_COMMITTED")
        self.assertEqual(failed["errors"][0]["draft_field"], "claims[0].authority_refs[0]")
        retained = failed["retained_plan"]
        self.assertEqual(retained["plan_id"], failed["plan_id"])
        self.assertEqual(retained["state"], "abandoned")
        self.assertIn("PLAN_AUTHORITY_NOT_COMMITTED", retained["reason"])
        plan = json.loads((self.root / ".local/pkc/semantic-plans" / f"{failed['plan_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["state"], "abandoned")
        self.assertEqual(plan["writes"], {})
        self.assertIn("capture failed", plan["abandon_reason"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        denied = self.cli("knowledge-plan", "check", failed["plan_id"], "--mode", "delta", expected=1)
        self.assertEqual(denied["errors"][0]["code"], "PLAN_NOT_OPEN")
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_capture_ref_can_target_claim_declared_later_in_draft(self):
        first = {"id": "first", "node": "software-core", "topic_id": "topic-schema",
                 "title": "Forward reference", "statement": "The first claim delegates its Authority to a later claim.",
                 "boundary": "Only the committed neutral fixture is in scope.",
                 "fact_classes": ["documented_contract"],
                 "authority_refs": [{"claim_id": "later", "path": "authority/validation-contract.md",
                                      "locator": "forward ref", "role": "documented_contract",
                                      "change_policy": "invalidate_on_change",
                                      "fact_classes": ["documented_contract"]},
                                     {"path": "authority/validation-contract.md", "locator": "own ref",
                                      "role": "documented_contract", "change_policy": "invalidate_on_change",
                                      "fact_classes": ["documented_contract"]}]}
        second = {"id": "later", "node": "software-core", "topic_id": "topic-validation",
                  "title": "Validation fails closed",
                  "statement": "Validation rejects incomplete semantic inputs before mutation.",
                  "boundary": "Only the committed neutral fixture is in scope.",
                  "fact_classes": ["cli_behavior", "documented_contract"],
                  "authority_refs": [{"path": "authority/validation-contract.md", "locator": "validation contract",
                                       "role": "current_implementation", "change_policy": "invalidate_on_change",
                                       "fact_classes": ["cli_behavior"]},
                                      {"path": "authority/validation-contract.md", "locator": "validation contract",
                                       "role": "documented_contract", "change_policy": "invalidate_on_change",
                                       "fact_classes": ["documented_contract"]}]}
        draft = self.write_draft("forward.json", "Forward reference draft", [first, second])
        captured = self.cli("knowledge-plan", "capture", "--file", draft.name)
        self.assertEqual(captured["operation_count"], 6)
        self.assertEqual(len(captured["semantic_diff"]["authority_refs_added"]), 4)
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_capture_delta_failure_reports_findings_and_abandons_plan(self):
        first = {"id": "a", "node": "software-core", "topic_id": "topic-schema",
                 "title": "Schema input is explicit",
                 "statement": "The schema parser accepts explicit versioned fields deterministically.",
                 "boundary": "Only the committed neutral fixture is in scope.",
                 "fact_classes": ["documented_contract"],
                 "authority_refs": [{"claim_id": "b", "path": "authority/validation-contract.md",
                                      "locator": "cross", "role": "documented_contract",
                                      "change_policy": "invalidate_on_change",
                                      "fact_classes": ["documented_contract"]}]}
        second = {"id": "b", "node": "software-core", "topic_id": "topic-validation",
                  "title": "Validation fails closed",
                  "statement": "Validation rejects incomplete semantic inputs before mutation.",
                  "boundary": "Only the committed neutral fixture is in scope.",
                  "fact_classes": ["cli_behavior", "documented_contract"],
                  "authority_refs": [{"path": "authority/validation-contract.md", "locator": "cli",
                                       "role": "current_implementation", "change_policy": "invalidate_on_change",
                                       "fact_classes": ["cli_behavior"]},
                                      {"path": "authority/validation-contract.md", "locator": "doc",
                                       "role": "documented_contract", "change_policy": "invalidate_on_change",
                                       "fact_classes": ["documented_contract"]}]}
        draft = self.write_draft("coverage.json", "Coverage failure draft", [first, second])
        failed = self.cli("knowledge-plan", "capture", "--file", draft.name, expected=1)
        self.assertEqual(failed["errors"][0]["code"], "AUTHORITY_FACT_COVERAGE")
        self.assertEqual(failed["errors"][0]["draft_field"], "claims[0].a")
        self.assertEqual(failed["errors"][0]["missing_fact_classes"], ["documented_contract"])
        self.assertIn("knowledge-plan add-authority-ref", failed["errors"][0].get("recommended_action", ""))
        self.assertEqual(failed["retained_plan"]["state"], "abandoned")
        self.assertIn("PLAN_DELTA_FAILED", failed["retained_plan"]["reason"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_capture_full_preflight_failure_abandons_plan_without_bundle(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
        refs["refs"].append({"id": "aref_stale_capture", "path": "data/store/registry.json", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "0" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs_path.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "data/store/authority-refs.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add stale authority fixture"], cwd=self.root, check=True)
        self.authority_before = self.formal_authority()
        draft = self.write_draft("stale.json", "Stale authority draft", [self.schema_claim()])
        failed = self.cli("knowledge-plan", "capture", "--file", draft.name, expected=1)
        self.assertTrue(any(error["code"] == "PLAN_AUTHORITY_STAGED_DRIFT" for error in failed["errors"]))
        self.assertEqual(failed["retained_plan"]["state"], "abandoned")
        self.assertIn("PLAN_FULL_PREFLIGHT_FAILED", failed["retained_plan"]["reason"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        self.assertEqual(self.formal_authority(), self.authority_before)

    def test_capture_markdown_draft_and_preview_only(self):
        path = self.root / "draft.md"
        path.write_text(
            "- intent: Markdown preview draft\n- risk: low\n\n"
            "## Schema Draft\n\n"
            "- node: software-core\n- topic_id: topic-schema\n"
            "- title: Schema draft claim\n- statement: A markdown draft claim.\n- boundary: Only the committed neutral fixture is in scope.\n"
            "- fact_class: documented_contract\n\n"
            "### authority_ref\n\n"
            "- path: authority/schema-contract.md\n- locator: draft\n- role: documented_contract\n"
            "- change_policy: invalidate_on_change\n- fact_class: documented_contract\n", encoding="utf-8")
        preview = self.cli("knowledge-plan", "capture", "--file", "draft.md", "--draft-format", "markdown", "--preview-only")
        self.assertTrue(preview["preview_only"])
        self.assertFalse(preview["finalized"])
        self.assertEqual(preview["plan_state"], "open")
        self.assertTrue(preview["content_hash"])
        self.assertEqual(len(preview["semantic_diff"]["claims_created"]), 1)
        # Preview writes nothing.
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 0)
        # The retained open plan can be finalized afterwards.
        pid = preview["plan_id"]
        self.assertTrue(self.cli("knowledge-plan", "check", pid, "--mode", "delta")["can_finalize"])
        finalized = self.cli("knowledge-plan", "finalize", pid)
        self.assertTrue(finalized["summary"]["finalized"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)

    def test_bundle_status_flags_orphan_draft_supersede_candidates(self):
        plan_id = self.cli("knowledge-plan", "init", "--intent", "Add neutral software contracts", "--risk", "medium")["plan_id"]
        claim = self.cli("knowledge-plan", "add-claim", plan_id, "--node", "software-core", "--topic-id", "topic-schema",
                         "--title", "First intent claim", "--statement", "First claim statement.",
                         "--boundary", "Only the committed neutral fixture is in scope.",
                         "--fact-class", "documented_contract")["claim_id"]
        self.cli("knowledge-plan", "add-authority-ref", plan_id, "--claim-id", claim,
                 "--path", "authority/schema-contract.md", "--locator", "schema contract",
                 "--role", "documented_contract", "--change-policy", "invalidate_on_change",
                 "--fact-class", "documented_contract")
        self.cli("knowledge-plan", "check", plan_id, "--mode", "delta")
        first = self.cli("knowledge-plan", "finalize", plan_id)
        self.cli("bundle-approve", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        self.cli("bundle-apply", first["bundle_id"], "--content-hash", first["content_hash"], "--apply")
        subprocess.run(["git", "add", "data/store", "domain/topics/schema.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "applied first"], cwd=self.root, check=True)
        # An orphan draft with the SAME intent is now covered by the applied Bundle.
        draft = self.write_draft("orphan.json", "Add neutral software contracts",
                                 [self.schema_claim("Orphan duplicate statement.")])
        self.cli("knowledge-plan", "capture", "--file", draft.name)
        health = self.cli("bundle-status")["health"]
        candidates = [item for item in health["supersede_candidates"] if item["intent"] == "Add neutral software contracts"]
        self.assertTrue(candidates)
        self.assertIn("bundle-supersede", candidates[0]["next_step"])

    def test_knowledge_check_eval_coverage_reports_uncovered_topics(self):
        self.cli("rebuild")
        cov = self.cli("knowledge-check", "--eval-coverage")["eval_coverage"]
        self.assertEqual(cov["status"], "COVERED")
        self.assertEqual(sorted(cov["covered_topics"]), ["topic-runtime", "topic-schema", "topic-validation"])
        # Add a genuinely uncovered Topic -> GAP.
        registry = json.loads((self.root / "data/store/registry.json").read_text())
        registry["topics"].append({"id": "topic-experience", "node_id": "software-core", "title": "Experience Contract",
                                   "path": "domain/topics/experience.md", "summary": "Experience behavior",
                                   "keywords": ["experience"], "permission": "internal"})
        (self.root / "data/store/registry.json").write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        (self.root / "domain/topics/experience.md").write_text("# Experience Contract\n\nExperience behavior.\n", encoding="utf-8")
        subprocess.run(["git", "add", "data/store/registry.json", "domain/topics/experience.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add experience topic"], cwd=self.root, check=True)
        self.cli("rebuild")
        cov = self.cli("knowledge-check", "--eval-coverage")["eval_coverage"]
        self.assertEqual(cov["status"], "GAP")
        self.assertIn("topic-experience", cov["uncovered_topics"])


if __name__ == "__main__":
    unittest.main()
