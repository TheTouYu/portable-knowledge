from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "pkc-project-operator" / "scripts" / "pkc_operator.py"
SPEC = importlib.util.spec_from_file_location("pkc_operator", SCRIPT)
operator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(operator)
from portable_knowledge.authority import FACT_CLASSES, ROLES


class OperatorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Operator Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "operator@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Existing Project\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_global_install_default_source_is_repository_root(self):
        args = operator.parser().parse_args(["install-global"])
        self.assertEqual(args.source.resolve(), ROOT)

    def test_plan_hash_is_stable_and_excludes_its_own_field(self):
        plan = {"schema_version": 1, "writes": [], "plan_hash": "old"}
        first = operator.plan_hash(plan)
        plan["plan_hash"] = first
        self.assertEqual(operator.plan_hash(plan), first)
        plan["writes"].append({"path": "x"})
        self.assertNotEqual(operator.plan_hash(plan), first)

    def test_initial_assets_are_empty_authority_and_locked_remote_commit(self):
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc1-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        writes, links = operator.initial_assets(self.root, "existing-project", "a" * 40, operator.DEFAULT_REMOTE, wheel, "b" * 64, "0.2.0rc1")
        by_path = {item["path"]: item["content"] for item in writes}
        registry = json.loads(by_path["data/knowledge/registry.json"])
        self.assertEqual(registry["nodes"], [])
        self.assertEqual(registry["topics"], [])
        config = json.loads(by_path["project-intelligence.json"])
        self.assertEqual(config["authority"]["authority_refs"], "data/knowledge/authority-refs.json")
        self.assertIn(config["authority"]["authority_refs"], by_path)
        lock = json.loads(by_path["tools/pkc-lock.json"])
        self.assertEqual(lock["source_commit"], "a" * 40)
        self.assertEqual(lock["wheel_sha256"], "b" * 64)
        self.assertEqual(links[0]["path"], ".agents/skills/existing-project-knowledge-adapter")

    def test_plan_adopt_preserves_existing_instance_and_authority(self):
        config = {"schema_version": 1, "instance": {"id": "existing-project"},
                  "pkc": {"version": "0.2.0rc1"},
                  "authority": {"registry": "data/knowledge/registry.json"}}
        (self.root / "project-intelligence.json").write_text(json.dumps(config), encoding="utf-8")
        authority = self.root / "data/knowledge/registry.json"
        authority.parent.mkdir(parents=True)
        authority.write_text('{"schema_version": 1, "nodes": [{"id": "real"}]}\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "existing PKC instance"], cwd=self.root, check=True)
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc1-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        args = type("Args", (), {"target": self.root, "output": Path(self.temp.name) / "adopt.json",
                                  "remote": operator.DEFAULT_REMOTE, "ref": "main"})()
        with mock.patch.object(operator, "resolve_commit", return_value="a" * 40), \
             mock.patch.object(operator, "ensure_wheel", return_value=(wheel, "b" * 64, "0.2.0rc1")):
            result = operator.command_plan_adopt(args)
        plan = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(result["plan_hash"], plan["plan_hash"])
        self.assertEqual(plan["kind"], "pkc-adopt")
        self.assertEqual({item["path"] for item in plan["writes"]}, {"tools/pkc-lock.json", "tools/pkc.py"})
        self.assertIn("project-intelligence.json", plan["preserved"])
        self.assertIn("configured authority and knowledge assets", plan["preserved"])
        self.assertEqual(json.loads(authority.read_text(encoding="utf-8"))["nodes"][0]["id"], "real")
        self.assertFalse((self.root / "tools").exists())

    def test_apply_requires_human_review_before_any_mutation(self):
        plan = {"schema_version": 1, "operator_contract": operator.CONTRACT, "kind": "pkc-install",
                "target_root": str(self.root), "created_from": operator.git_state(self.root),
                "source": {"wheel": str(Path(self.temp.name) / "missing.whl"), "wheel_sha256": "x"},
                "runtime": ".local/pkc/runtimes/x", "writes": [], "links": []}
        plan["plan_hash"] = operator.plan_hash(plan)
        plan_path = Path(self.temp.name) / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        args = type("Args", (), {"plan": plan_path, "plan_hash": plan["plan_hash"], "human_reviewed": False})()
        with self.assertRaisesRegex(operator.OperatorError, "real human"):
            operator.command_apply(args)
        self.assertFalse((self.root / ".local").exists())

    def test_apply_rejects_hash_or_git_state_drift(self):
        plan = {"schema_version": 1, "operator_contract": operator.CONTRACT, "kind": "pkc-install",
                "target_root": str(self.root), "created_from": operator.git_state(self.root),
                "source": {"wheel": str(Path(self.temp.name) / "missing.whl"), "wheel_sha256": "x"},
                "runtime": ".local/pkc/runtimes/x", "writes": [], "links": []}
        plan["plan_hash"] = operator.plan_hash(plan)
        plan_path = Path(self.temp.name) / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        args = type("Args", (), {"plan": plan_path, "plan_hash": "wrong", "human_reviewed": True})()
        with self.assertRaisesRegex(operator.OperatorError, "hash mismatch"):
            operator.command_apply(args)
        args.plan_hash = plan["plan_hash"]
        (self.root / "working.txt").write_text("change", encoding="utf-8")
        with self.assertRaisesRegex(operator.OperatorError, "Git state changed"):
            operator.command_apply(args)

    def test_documented_authority_vocabularies_match_core(self):
        for relative in ("docs/SEMANTIC-CHANGES.md", "skills/pkc-project-operator/references/MODES.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for role in ROLES:
                self.assertIn(f"`{role}`", text, relative)
            for fact_class in FACT_CLASSES:
                self.assertIn(f"`{fact_class}`", text, relative)
            self.assertNotRegex(text, re.compile(r"--role (?:implementation|test|schema|contract|verification)(?:\s|\\)"), relative)
            self.assertNotIn("--fact-class current_implementation", text, relative)

    def test_skill_declares_full_lifecycle_and_no_self_review(self):
        text = (ROOT / "skills/pkc-project-operator/SKILL.md").read_text(encoding="utf-8")
        for mode in ("install", "first-use", "query", "intake", "capture", "memory", "maintain", "doctor", "upgrade", "uninstall", "status", "approve-apply"):
            self.assertIn(mode, text)
        self.assertIn("model may never review its own proposal", text)
        self.assertIn("Never use editable installs", text)
        self.assertIn("Never delete tracked knowledge", text)


if __name__ == "__main__":
    unittest.main()
