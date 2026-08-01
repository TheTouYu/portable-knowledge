from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile
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

    def configure_adapter_fixture(self):
        config = {"adapter": {"skill": "skills/existing-project-knowledge-adapter/SKILL.md"},
                  "authority": {"registry": "data/knowledge/registry.json"},
                  "memory": {"contexts": [{"id": "build"}]}}
        registry = {"nodes": [{"id": "node-runtime"}], "topics": [{"id": "topic-cli"}]}
        files = {
            "project-intelligence.json": json.dumps(config),
            "data/knowledge/registry.json": json.dumps(registry),
            "skills/existing-project-knowledge-adapter/SKILL.md": "name: existing-project-knowledge-adapter\nBootstrap\n",
            "tools/pkc.py": "# wrapper\n",
            "docs/OPERATING.md": "# Operating\n",
        }
        for relative, content in files.items():
            path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "configured Adapter"], cwd=self.root, check=True)

    def test_global_install_default_source_is_repository_root(self):
        args = operator.parser().parse_args(["install-global"])
        self.assertEqual(args.source.resolve(), ROOT)

    def test_global_install_manages_both_repository_skills_and_is_idempotent(self):
        root = Path(self.temp.name) / "skills"
        args = operator.parser().parse_args([
            "install-global", "--source", str(ROOT), "--skill-root", str(root)
        ])
        clean = subprocess.CompletedProcess([], 0, "", "")
        real_run = operator.run
        with mock.patch.object(operator, "CACHE", Path(self.temp.name) / "cache"), \
             mock.patch.object(operator, "run") as run:
            run.side_effect = lambda command, **kwargs: clean if command[-2:] == ["status", "--porcelain"] else real_run(command, **kwargs)
            first = operator.command_install_global(args)
            second = operator.command_install_global(args)
        expected = {str(root / "pkc-project-operator"), str(root / "isolated-model-evaluator")}
        self.assertEqual(set(first["installed"]), expected)
        self.assertEqual(set(second["installed"]), expected)
        manifest = json.loads((Path(self.temp.name) / "cache/operator-install.json").read_text())
        self.assertEqual(set(manifest["skill_sources"]), {"pkc-project-operator", "isolated-model-evaluator"})

    def test_plan_hash_is_stable_and_excludes_its_own_field(self):
        plan = {"schema_version": 1, "writes": [], "plan_hash": "old"}
        first = operator.plan_hash(plan)
        plan["plan_hash"] = first
        self.assertEqual(operator.plan_hash(plan), first)
        plan["writes"].append({"path": "x"})
        self.assertNotEqual(operator.plan_hash(plan), first)

    def test_initial_assets_are_empty_authority_and_locked_remote_commit(self):
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        writes, links = operator.initial_assets(self.root, "existing-project", "a" * 40, operator.DEFAULT_REMOTE, wheel, "b" * 64, "0.2.0rc5")
        by_path = {item["path"]: item["content"] for item in writes}
        registry = json.loads(by_path["data/knowledge/registry.json"])
        self.assertEqual(registry["nodes"], [])
        self.assertEqual(registry["topics"], [])
        config = json.loads(by_path["project-intelligence.json"])
        self.assertEqual(config["adapter"]["skill"], "skills/existing-project-knowledge-adapter/SKILL.md")
        self.assertEqual(config["authority"]["authority_refs"], "data/knowledge/authority-refs.json")
        self.assertIn(config["authority"]["authority_refs"], by_path)
        lock = json.loads(by_path["tools/pkc-lock.json"])
        self.assertEqual(lock["source_commit"], "a" * 40)
        self.assertEqual(lock["wheel_sha256"], "b" * 64)
        self.assertEqual(links[0]["path"], ".agents/skills/existing-project-knowledge-adapter")
        adapter = by_path["skills/existing-project-knowledge-adapter/SKILL.md"]
        self.assertIn("project-owned thin router", adapter)
        self.assertIn("not a second human-facing operator", adapter)

    def test_plan_adopt_preserves_existing_instance_and_authority(self):
        config = {"schema_version": 1, "instance": {"id": "existing-project"},
                  "pkc": {"version": "0.2.0rc5"},
                  "authority": {"registry": "data/knowledge/registry.json"}}
        (self.root / "project-intelligence.json").write_text(json.dumps(config), encoding="utf-8")
        authority = self.root / "data/knowledge/registry.json"
        authority.parent.mkdir(parents=True)
        authority.write_text('{"schema_version": 1, "nodes": [{"id": "real"}]}\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "existing PKC instance"], cwd=self.root, check=True)
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        args = type("Args", (), {"target": self.root, "output": Path(self.temp.name) / "adopt.json",
                                  "remote": operator.DEFAULT_REMOTE, "ref": "main"})()
        with mock.patch.object(operator, "resolve_commit", return_value="a" * 40), \
             mock.patch.object(operator, "ensure_wheel", return_value=(wheel, "b" * 64, "0.2.0rc5")):
            result = operator.command_plan_adopt(args)
        plan = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(result["plan_hash"], plan["plan_hash"])
        self.assertEqual(plan["kind"], "pkc-adopt")
        self.assertEqual({item["path"] for item in plan["writes"]}, {"tools/pkc-lock.json", "tools/pkc.py"})
        self.assertIn("project-intelligence.json", plan["preserved"])
        self.assertIn("configured authority and knowledge assets", plan["preserved"])
        self.assertEqual(json.loads(authority.read_text(encoding="utf-8"))["nodes"][0]["id"], "real")
        self.assertFalse((self.root / "tools").exists())

    def test_plan_adapter_is_deterministic_review_only_and_does_not_mutate_target(self):
        self.configure_adapter_fixture()
        candidate = Path(self.temp.name) / "candidate.md"
        candidate.write_text("name: existing-project-knowledge-adapter\nUse python tools/pkc.py with build, node-runtime, topic-cli, and docs/OPERATING.md.\n", encoding="utf-8")
        output = Path(self.temp.name) / "adapter-plan.json"
        args = type("Args", (), {"target": self.root, "candidate": candidate, "output": output,
                                  "context": ["build"], "node": ["node-runtime"],
                                  "topic": ["topic-cli"], "path": ["docs/OPERATING.md"]})()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        first = operator.command_plan_adapter(args)
        second = operator.command_plan_adapter(args)
        plan = json.loads(output.read_text(encoding="utf-8"))
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(first["plan_hash"], second["plan_hash"])
        self.assertEqual(before, after)
        self.assertEqual(plan["evaluation_status"], "not_evaluated")
        self.assertEqual(plan["target_path"], "skills/existing-project-knowledge-adapter/SKILL.md")
        self.assertEqual(plan["candidate_content"], candidate.read_text(encoding="utf-8"))
        self.assertEqual(plan["current_sha256"], operator.digest_file(self.root / plan["target_path"]))
        self.assertEqual(plan["candidate_sha256"], operator.digest_file(candidate))

    def test_plan_adapter_rejects_output_inside_target_project(self):
        self.configure_adapter_fixture()
        candidate = Path(self.temp.name) / "candidate.md"
        candidate.write_text("name: existing-project-knowledge-adapter\nUse python tools/pkc.py.\n", encoding="utf-8")
        args = type("Args", (), {"target": self.root, "candidate": candidate,
                                  "output": self.root / "adapter-plan.json", "context": [],
                                  "node": [], "topic": [], "path": []})()
        with self.assertRaisesRegex(operator.OperatorError, "proposal output must stay outside"):
            operator.command_plan_adapter(args)
        self.assertFalse(args.output.exists())

    def test_plan_adapter_reports_exact_invalid_references_and_rejects_mutation_commands(self):
        self.configure_adapter_fixture()
        candidate = Path(self.temp.name) / "candidate.md"
        args = type("Args", (), {"target": self.root, "candidate": candidate,
                                  "output": Path(self.temp.name) / "plan.json", "context": [],
                                  "node": [], "topic": [], "path": []})()
        for option, value, message in (
            ("context", "missing-context", "context reference is missing: missing-context"),
            ("node", "missing-node", "node reference is missing: missing-node"),
            ("topic", "missing-topic", "topic reference is missing: missing-topic"),
            ("path", "../outside", "path reference is missing or outside the project: ../outside"),
        ):
            setattr(args, option, [value])
            candidate.write_text(f"name: existing-project-knowledge-adapter\nUse python tools/pkc.py with {value}.\n", encoding="utf-8")
            with self.subTest(option=option), self.assertRaisesRegex(operator.OperatorError, re.escape(message)):
                operator.command_plan_adapter(args)
            setattr(args, option, [])
        candidate.write_text("name: existing-project-knowledge-adapter\nUse python tools/pkc.py.\ngit push\n", encoding="utf-8")
        with self.assertRaisesRegex(operator.OperatorError, "forbidden direct mutation command: git push"):
            operator.command_plan_adapter(args)
        candidate.write_text("name: existing-project-knowledge-adapter\nUse python tools/pkc.py. Never run git push or bundle-apply.\n", encoding="utf-8")
        result = operator.command_plan_adapter(args)
        self.assertTrue(result["ok"])

    def test_apply_plan_cannot_apply_an_adapter_proposal(self):
        plan = {"kind": "pkc-adapter-proposal"}
        path = Path(self.temp.name) / "plan.json"; path.write_text(json.dumps(plan), encoding="utf-8")
        args = type("Args", (), {"plan": path, "plan_hash": "unused", "human_reviewed": True})()
        with self.assertRaisesRegex(operator.OperatorError, "does not support plan kind"):
            operator.command_apply(args)

    def test_plan_upgrade_synchronizes_lock_and_declared_version_and_records_rollback(self):
        old_commit = "a" * 40
        new_commit = "b" * 40
        runtime = self.root / ".local/pkc/runtimes" / old_commit
        runtime.mkdir(parents=True)
        (self.root / "project-intelligence.json").write_text('{"schema_version":1,"pkc":{"version":"0.2.0rc4","projection_path":".local/pkc"}}', encoding="utf-8")
        lock = {"schema_version": 1, "version": "0.2.0rc4", "source_commit": old_commit,
                "runtime": f".local/pkc/runtimes/{old_commit}"}
        (self.root / "tools").mkdir()
        (self.root / "tools/pkc-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "configured"], cwd=self.root, check=True)
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        provenance = {"wheel": str(wheel), "sha256": operator.digest_file(wheel), "version": "0.2.0rc5",
                      "source_commit": new_commit, "python": "/usr/bin/python", "abi": "test",
                      "source_worktree_dirty": ["?? local.txt"],
                      "capabilities": {"semantic_plan": True, "claim_revision_plan": True}}
        args = type("Args", (), {"target": self.root, "source_repository": str(ROOT),
                                  "source_commit": new_commit, "output": Path(self.temp.name) / "upgrade.json",
                                  "representative_query": ["question"], "project_check": ["true"]})()
        current_capabilities = {"semantic_plan": True, "claim_revision_plan": False,
                                "deprecated_route": True}
        with mock.patch.object(operator, "ensure_wheel_provenance", return_value=provenance), \
             mock.patch.object(operator, "installed_capabilities", return_value=current_capabilities):
            result = operator.command_plan_upgrade(args)
        plan = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(plan["kind"], "pkc-upgrade")
        self.assertEqual([item["path"] for item in plan["writes"]], ["tools/pkc-lock.json", "project-intelligence.json"])
        config_write = next(item for item in plan["writes"] if item["path"] == "project-intelligence.json")
        self.assertEqual(json.loads(config_write["content"])["pkc"]["version"], "0.2.0rc5")
        self.assertEqual(plan["rollback_runtime"], lock["runtime"])
        self.assertEqual(plan["source"]["wheel_sha256"], provenance["sha256"])
        self.assertEqual(plan["compatibility"]["capability_diff"], {
            "added": [], "removed": ["deprecated_route"],
            "changed": {"claim_revision_plan": {"current": False, "target": True}},
            "unchanged": ["semantic_plan"],
        })
        self.assertEqual(result["compatibility"], plan["compatibility"])
        self.assertEqual(result["plan_hash"], plan["plan_hash"])
        self.assertEqual(json.loads((self.root / "tools/pkc-lock.json").read_text()), lock)

    def test_plan_upgrade_can_defer_knowledge_check_for_authority_maintenance_bootstrap(self):
        old_commit = "a" * 40
        new_commit = "b" * 40
        runtime = self.root / ".local/pkc/runtimes" / old_commit
        runtime.mkdir(parents=True)
        (self.root / "project-intelligence.json").write_text(
            '{"schema_version":1,"evaluation":{"cases_path":"cases.json"}}', encoding="utf-8")
        lock = {"schema_version": 1, "version": "0.2.0rc4", "source_commit": old_commit,
                "runtime": f".local/pkc/runtimes/{old_commit}"}
        (self.root / "tools").mkdir()
        (self.root / "tools/pkc-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "configured"], cwd=self.root, check=True)
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        provenance = {"wheel": str(wheel), "sha256": operator.digest_file(wheel), "version": "0.2.0rc5",
                      "source_commit": new_commit, "capabilities": {"authority_ref_refresh_plan": True}}
        args = type("Args", (), {"target": self.root, "source_repository": str(ROOT),
                                  "source_commit": new_commit, "output": Path(self.temp.name) / "upgrade.json",
                                  "representative_query": [], "project_check": [],
                                  "defer_knowledge_check_for_authority_maintenance": True})()
        with mock.patch.object(operator, "ensure_wheel_provenance", return_value=provenance), \
             mock.patch.object(operator, "installed_capabilities", return_value={}):
            result = operator.command_plan_upgrade(args)
        plan = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertNotIn("knowledge-check", plan["verification"])
        self.assertEqual(plan["deferred_checks"][0]["command"], "knowledge-check")
        self.assertIn("Authority maintenance Bundle", plan["deferred_checks"][0]["required_after"])
        self.assertEqual(result["deferred_checks"], plan["deferred_checks"])

    def test_plan_upgrade_rejects_authority_bootstrap_without_refresh_capability(self):
        old_commit = "a" * 40
        runtime = self.root / ".local/pkc/runtimes" / old_commit
        runtime.mkdir(parents=True)
        (self.root / "project-intelligence.json").write_text(
            '{"schema_version":1,"evaluation":{"cases_path":"cases.json"}}', encoding="utf-8")
        (self.root / "tools").mkdir()
        (self.root / "tools/pkc-lock.json").write_text(json.dumps({
            "schema_version": 1, "version": "0.2.0rc4", "source_commit": old_commit,
            "runtime": f".local/pkc/runtimes/{old_commit}"}), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "configured"], cwd=self.root, check=True)
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        provenance = {"wheel": str(wheel), "sha256": operator.digest_file(wheel), "version": "0.2.0rc5",
                      "source_commit": "b" * 40, "capabilities": {}}
        args = type("Args", (), {"target": self.root, "source_repository": str(ROOT),
                                  "source_commit": "b" * 40, "output": Path(self.temp.name) / "upgrade.json",
                                  "representative_query": [], "project_check": [],
                                  "defer_knowledge_check_for_authority_maintenance": True})()
        with mock.patch.object(operator, "ensure_wheel_provenance", return_value=provenance), \
             mock.patch.object(operator, "installed_capabilities", return_value={}):
            with self.assertRaisesRegex(operator.OperatorError, "authority_ref_refresh_plan"):
                operator.command_plan_upgrade(args)

    def test_builder_preflight_selects_python_build_when_uv_is_absent(self):
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(operator.shutil, "which", return_value=None), \
             mock.patch.object(operator, "run", return_value=completed), \
             mock.patch.object(operator.importlib.util, "find_spec", return_value=object()):
            environment = operator.build_environment()
        self.assertTrue(environment["pip_available"])
        self.assertTrue(environment["venv_available"])
        self.assertTrue(environment["build_available"])
        self.assertEqual(environment["builder"], "venv-pip-build")

    def test_builder_preflight_fails_actionably_without_usable_backend(self):
        environment = {"python": "/python", "python_version": "3.11", "abi": "abi", "uv": None,
                       "pip_available": True, "venv_available": True, "build_available": False,
                       "builder": "unavailable"}
        with mock.patch.object(operator, "_source_commit", return_value=("c" * 40, [])), \
             mock.patch.object(operator, "build_environment", return_value=environment):
            with self.assertRaisesRegex(operator.OperatorError, "build_available=False"):
                operator.ensure_wheel_provenance(str(ROOT), "c" * 40)

    def test_python_build_backend_uses_clean_checkout_and_output_directory(self):
        checkout = Path(self.temp.name) / "source"
        output = Path(self.temp.name) / "dist"
        environment = {"python": "/python", "builder": "venv-pip-build", "uv": None}
        with mock.patch.object(operator, "run") as run:
            operator.build_wheel(checkout, output, environment, {"SOURCE_DATE_EPOCH": "1"})
        run.assert_called_once_with(
            ["/python", "-m", "build", "--wheel", "--outdir", str(output)],
            cwd=checkout, env={"SOURCE_DATE_EPOCH": "1"})

    def test_wheel_metadata_is_read_from_bytes_not_filename(self):
        wheel = Path(self.temp.name) / "misleading-9.9-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("portable_knowledge-0.2.0rc5.dist-info/METADATA",
                             "Metadata-Version: 2.1\nName: portable-knowledge\nVersion: 0.2.0rc5\n")
        self.assertEqual(operator.wheel_metadata(wheel), {
            "distribution": "portable-knowledge", "version": "0.2.0rc5"})

    def test_wheel_metadata_rejects_wrong_distribution(self):
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("other-1.0.dist-info/METADATA",
                             "Metadata-Version: 2.1\nName: other\nVersion: 1.0\n")
        with self.assertRaisesRegex(operator.OperatorError, "distribution"):
            operator.wheel_metadata(wheel)

    def test_exact_commit_builder_reports_dirty_source_and_build_environment(self):
        environment = {"python": "/python", "python_version": "3.14", "abi": "abi", "uv": "/uv",
                       "pip_available": False, "venv_available": True, "build_available": False,
                       "builder": "uv"}
        with mock.patch.object(operator, "_source_commit", return_value=("c" * 40, [" M local.py"])), \
             mock.patch.object(operator, "build_environment", return_value=environment), \
             mock.patch.object(operator, "CACHE", Path(self.temp.name) / "cache"), \
             mock.patch.object(operator, "wheel_metadata", return_value={"distribution": "portable-knowledge", "version": "0.2.0rc5"}), \
             mock.patch.object(operator, "verify_wheel_runtime", return_value={"package_version": "0.2.0rc5", "capabilities": {"semantic_plan": True}}), \
             mock.patch.object(operator, "run") as run:
            checkout = Path(self.temp.name) / "checkout"
            def fake_run(command, **kwargs):
                if command[:2] == ["git", "clone"]:
                    target = Path(command[-1]); target.mkdir(parents=True)
                if "--out-dir" in command:
                    output = Path(command[command.index("--out-dir") + 1]); output.mkdir()
                    (output / "portable_knowledge-0.2.0rc5-py3-none-any.whl").write_bytes(b"wheel")
                stdout = "1234567890\n" if "--format=%ct" in command else ""
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
            run.side_effect = fake_run
            result = operator.ensure_wheel_provenance(str(ROOT), "c" * 40)
        self.assertEqual(result["source_worktree_dirty"], [" M local.py"])
        self.assertEqual(result["abi"], "abi")
        self.assertEqual(result["distribution"], "portable-knowledge")
        self.assertEqual(result["package_version"], "0.2.0rc5")
        self.assertEqual(result["capabilities"], {"semantic_plan": True})
        self.assertEqual(len(result["sha256"]), 64)

    def test_failed_post_switch_check_restores_lock_and_writes_rollback_receipt(self):
        old_commit = "a" * 40
        new_commit = "b" * 40
        old_lock = {"schema_version": 1, "version": "0.2.0rc4", "source_commit": old_commit,
                    "runtime": f".local/pkc/runtimes/{old_commit}"}
        tools = self.root / "tools"
        tools.mkdir()
        lock_path = tools / "pkc-lock.json"
        lock_path.write_text(json.dumps(old_lock) + "\n", encoding="utf-8")
        wheel = Path(self.temp.name) / "portable_knowledge-0.2.0rc5-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        new_lock = {**old_lock, "version": "0.2.0rc5", "source_commit": new_commit,
                    "runtime": f".local/pkc/runtimes/{new_commit}"}
        write = operator.text_write(self.root, "tools/pkc-lock.json", json.dumps(new_lock) + "\n")
        plan = {"schema_version": 1, "operator_contract": operator.CONTRACT, "kind": "pkc-upgrade",
                "target_root": str(self.root), "created_from": operator.git_state(self.root),
                "source": {"wheel": str(wheel), "wheel_sha256": operator.digest_file(wheel),
                           "version": "0.2.0rc5", "provenance": {"build_environment": {
                               "python": "/python", "python_version": "3.11", "abi": "abi", "builder": "uv"}}},
                "runtime": new_lock["runtime"], "rollback_runtime": old_lock["runtime"],
                "writes": [write], "links": [], "verification": []}
        plan["plan_hash"] = operator.plan_hash(plan)
        plan_path = Path(self.temp.name) / "upgrade.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        args = type("Args", (), {"plan": plan_path, "plan_hash": plan["plan_hash"], "human_reviewed": True})()
        current_environment = {"python": "/python", "python_version": "3.11", "abi": "abi", "builder": "uv"}

        retry = False

        def fake_run(command, **kwargs):
            if command[1:3] == ["-m", "venv"]:
                runtime = Path(command[-1]); (runtime / "bin").mkdir(parents=True)
                (runtime / "bin/python").write_text("", encoding="utf-8")
            if command[-2:] == ["pip", "--version"]:
                return subprocess.CompletedProcess(command, 0, stdout="pip", stderr="")
            if command[-1:] == ["capabilities"]:
                version = "0.2.0rc5" if retry else "9.9"
                return subprocess.CompletedProcess(
                    command, 0,
                    stdout=json.dumps({"ok": True, "runtime_version": version, "capabilities": {}}), stderr="")
            if len(command) >= 2 and command[1] == "-c":
                origin = self.root / new_lock["runtime"] / "lib/portable_knowledge/__init__.py"
                return subprocess.CompletedProcess(command, 0, stdout=f"{origin}\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        with mock.patch.object(operator, "git_state", return_value=plan["created_from"]), \
             mock.patch.object(operator, "build_environment", return_value=current_environment), \
             mock.patch.object(operator, "run", side_effect=fake_run):
            with self.assertRaisesRegex(operator.OperatorError, "rollback_receipt"):
                operator.command_apply(args)
        self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8")), old_lock)
        receipt_path = self.root / ".local/pkc/operator-receipts" / f"upgrade-{plan['plan_hash']}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(receipt["prior_selection_restored"])
        self.assertIn("runtime version mismatch", receipt["failure"])
        self.assertEqual(receipt["retained_runtimes"][0], old_lock["runtime"])
        failed_runtime = receipt["retained_runtimes"][1]
        self.assertNotEqual(failed_runtime, new_lock["runtime"])
        self.assertTrue((self.root / failed_runtime).is_dir())
        self.assertFalse((self.root / new_lock["runtime"]).exists())
        self.assertIn("create a new plan", receipt["next"])

        retry_plan = {**plan, "project_checks": []}
        retry_plan["plan_hash"] = operator.plan_hash(retry_plan)
        self.assertNotEqual(retry_plan["plan_hash"], plan["plan_hash"])
        retry_path = Path(self.temp.name) / "upgrade-retry.json"
        retry_path.write_text(json.dumps(retry_plan), encoding="utf-8")
        retry_args = type("Args", (), {"plan": retry_path, "plan_hash": retry_plan["plan_hash"],
                                        "human_reviewed": True})()
        retry = True
        with mock.patch.object(operator, "git_state", return_value=retry_plan["created_from"]), \
             mock.patch.object(operator, "build_environment", return_value=current_environment), \
             mock.patch.object(operator, "run", side_effect=fake_run):
            result = operator.command_apply(retry_args)
        self.assertTrue(result["ok"])
        self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8")), new_lock)
        self.assertTrue((self.root / new_lock["runtime"]).is_dir())

    def test_failed_runtime_quarantine_does_not_overwrite_earlier_diagnostics(self):
        runtime = self.root / ".local/pkc/runtimes" / ("b" * 40)
        runtime.mkdir(parents=True)
        (runtime / "marker").write_text("candidate", encoding="utf-8")
        quarantine = self.root / ".local/pkc/failed-runtimes"
        quarantine.mkdir(parents=True)
        first = quarantine / f"{'b' * 40}-{'c' * 12}"
        first.mkdir()
        (first / "marker").write_text("earlier", encoding="utf-8")

        retained = operator.quarantine_failed_runtime(self.root, runtime, "c" * 64)

        self.assertEqual(retained, f".local/pkc/failed-runtimes/{'b' * 40}-{'c' * 12}-1")
        self.assertEqual((first / "marker").read_text(encoding="utf-8"), "earlier")
        self.assertEqual((self.root / retained / "marker").read_text(encoding="utf-8"), "candidate")
        self.assertFalse(runtime.exists())

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
        self.assertIn("帮我安装知识树", text)
        self.assertIn("帮我添加知识", text)
        self.assertIn("technical_install", text)
        self.assertIn("retrieval_evaluation", text)
        self.assertIn("single human-facing operator", text)
        self.assertIn("install/update entry for both repository companion Skills", text)
        self.assertIn("Adapter revisions require a separate reviewed project diff", text)
        evaluator = (ROOT / "skills/isolated-model-evaluator/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("optional evaluation companion", evaluator)
        self.assertIn("not a second operator", evaluator)
        self.assertIn("Never use editable installs", text)
        self.assertIn("Never delete tracked knowledge", text)
        self.assertIn("refresh-authority-ref PLAN_ID --authority-ref-id ID --reason REASON", text)
        self.assertIn("does not attach a new Claim", text)
        self.assertIn("use `add-authority-ref` with the Claim ID returned by the plan", text)
        self.assertIn("valid for that purpose-scoped Ref to use a source path already used by another Ref", text)
        self.assertIn("retire-authority-ref PLAN_ID --authority-ref-id ID", text)
        self.assertIn("Execute all Claim, Authority Ref, and necessary stale-ref refresh mutations serially", text)
        self.assertIn("start from an identified committed range or commit", text)
        self.assertIn("do not guess a path or hand-type a variant", text)
        self.assertIn("may not contain PKC's maintainer-only `docs/SEMANTIC-CHANGES.md`", text)
        modes = (ROOT / "skills/pkc-project-operator/references/MODES.md").read_text(encoding="utf-8")
        self.assertIn("complete immutable 64-character `content_hash`", modes)
        self.assertIn("python tools/pkc.py tree --format text", modes)
        self.assertIn("git diff --check", modes)
        self.assertIn("generated/decoded GIA or equivalent artifact", modes)
        self.assertIn("plan-upgrade", text)
        self.assertIn("install/adopt are not upgrade substitutes", text)
        self.assertIn("current/target capability diff", text)
        self.assertIn("rollback receipt", text)
        self.assertIn("Do not add isolated evaluation to routine Claim creation", text)

    def test_documented_operator_commands_exist(self):
        choices = operator.parser()._subparsers._group_actions[0].choices
        for command in ("plan-install", "plan-adopt", "plan-adapter", "plan-upgrade", "apply-plan"):
            self.assertIn(command, choices)


if __name__ == "__main__":
    unittest.main()
