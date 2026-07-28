from __future__ import annotations

import argparse
import base64
import contextlib
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
                     "knowledge_structure_refactor", "claim_revision_plan"):
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
        finalized = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertFalse(finalized["summary"]["approved"]); self.assertFalse(finalized["summary"]["applied"])
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        bundle = json.loads((self.root / "data/knowledge/bundles" / f"{finalized['bundle_id']}.json").read_text(encoding="utf-8"))
        self.assertTrue(all(set(action["provenance"]) == {"plan_id", "operation_id", "operation_type", "operation_digest", "core_version"}
                            for action in bundle["actions"]))
        self.assertNotIn("bundle", finalized)
        replay = self.cli("knowledge-plan", "finalize", plan_id)
        self.assertTrue(replay["summary"]["replayed"])
        self.assertEqual((replay["bundle_id"], replay["content_hash"]), (finalized["bundle_id"], finalized["content_hash"]))
        self.assertEqual(len(list((self.root / "data/knowledge/bundles").glob("bnd_*.json"))), 1)
        # Only the immutable, unapproved Bundle artifact was created; production authority remains unchanged.
        self.assertEqual(self.formal_authority(), self.authority_before)

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

    def test_cli_finalize_reports_non_current_authority_with_status_and_hashes(self):
        refs_path = self.root / "data/store/authority-refs.json"
        refs = json.loads(refs_path.read_text(encoding="utf-8"))
        refs["refs"].append({"id": "aref_stale_fixture", "path": "authority/schema-contract.md", "locator": "fixture",
                             "role": "documented_contract", "baseline_state": "committed_baseline",
                             "change_policy": "invalidate_on_change", "approved_hash": "0" * 64,
                             "claim_ids": [], "supports_fact_classes": []})
        refs_path.write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", refs_path.relative_to(self.root).as_posix()], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "add stale authority fixture"], cwd=self.root, check=True)
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
        failed = self.cli_process("knowledge-plan", "finalize", plan_id, expected=1)
        finding = next(item for item in failed["errors"] if item["authority_ref_id"] == "aref_stale_fixture")
        self.assertEqual(finding["code"], "PLAN_FULL_AUTHORITY_NOT_CURRENT")
        self.assertEqual(finding["effective_status"], "invalidated")
        self.assertEqual(finding["expected_hash"], "0" * 64)
        self.assertEqual(len(finding["observed_hash"]), 64)
        self.assertFalse(finding["staged_by_current_plan"])
        inspected = self.cli_process("knowledge-plan", "inspect", plan_id)
        self.assertEqual((inspected["state"], inspected["cost_counters"]["candidate_bundles"]), ("open", 0))
        self.assertEqual(self.formal_authority(), self.authority_before)

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
            self.assertEqual(invoke()["errors"][0]["code"], code)
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


if __name__ == "__main__":
    unittest.main()
