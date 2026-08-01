from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))
from portable_knowledge import core

FIXTURE = PACKAGE / "tests/fixtures/minimal"


class FederationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.projects = []
        for project_id in ("game", "compiler"):
            project = self.root / project_id
            shutil.copytree(FIXTURE, project)
            config = json.loads((project / "project-intelligence.json").read_text())
            config["instance"] = {"id": project_id, "name": project_id.title()}
            (project / "project-intelligence.json").write_text(json.dumps(config))
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=project, check=True)
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=project, check=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(core.main(["--root", str(project), "rebuild"]), 0)
            self.projects.append(project)
        self.registry = self.root / "federation.json"
        self.registry.write_text(json.dumps({"schema_version": 1, "projects": [
            {"id": "game", "root": "game", "read_permission": "internal", "evidence_boundary": "Game-owned knowledge only."},
            {"id": "compiler", "root": "compiler", "read_permission": "internal", "evidence_boundary": "Compiler-owned knowledge only."}
        ]}))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *args: str, expected: int = 0) -> dict:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = core.main(["--root", str(self.root), *args])
        payload = json.loads(stream.getvalue())
        self.assertEqual(expected, code, payload)
        return payload

    def test_explicit_projects_are_searched_separately_without_writes(self) -> None:
        before = {project.name: {path.relative_to(project).as_posix(): path.read_bytes()
                                 for path in project.rglob("*") if path.is_file()}
                  for project in self.projects}
        payload = self.cli("federation-search", "deterministic lookup", "--registry", str(self.registry),
                           "--project", "game", "--project", "compiler")
        self.assertEqual("complete", payload["status"])
        self.assertTrue(payload["read_only"]); self.assertFalse(payload["cross_project_writes"])
        self.assertEqual(["game", "compiler"], [item["project_id"] for item in payload["projects"]])
        self.assertTrue(all(item["results"][0]["id"] == "clm_00000000000000000000000000" for item in payload["projects"]))
        after = {project.name: {path.relative_to(project).as_posix(): path.read_bytes()
                                for path in project.rglob("*") if path.is_file()}
                 for project in self.projects}
        self.assertEqual(before, after)

    def test_scope_and_registry_fail_closed(self) -> None:
        missing = self.cli("federation-search", "lookup", "--registry", str(self.registry), expected=1)
        self.assertEqual("FEDERATION_SCOPE", missing["errors"][0]["code"])
        unknown = self.cli("federation-search", "lookup", "--registry", str(self.registry), "--project", "unknown", expected=1)
        self.assertEqual("FEDERATION_PROJECT_UNKNOWN", unknown["errors"][0]["code"])

    def test_target_config_cannot_escape_project_root(self) -> None:
        registry = json.loads(self.registry.read_text())
        registry["projects"][0]["config"] = "../compiler/project-intelligence.json"
        self.registry.write_text(json.dumps(registry))
        payload = self.cli("federation-search", "lookup", "--registry", str(self.registry), "--project", "game", expected=2)
        self.assertEqual("FEDERATION_PROJECT_CONFIG", payload["projects"][0]["errors"][0]["code"])

    def test_unavailable_project_is_visible_without_blocking_available_project(self) -> None:
        shutil.rmtree(self.projects[1] / ".local")
        payload = self.cli("federation-search", "deterministic lookup", "--registry", str(self.registry),
                           "--project", "game", "--project", "compiler")
        self.assertEqual("partial", payload["status"])
        self.assertEqual(["available", "unavailable"], [item["status"] for item in payload["projects"]])
        self.assertIn("run rebuild", payload["projects"][1]["errors"][0]["message"])
        self.assertFalse((self.projects[1] / ".local").exists())

    def test_permission_is_fixed_by_registry(self) -> None:
        registry = json.loads(self.registry.read_text())
        registry["projects"][0]["read_permission"] = "public"
        self.registry.write_text(json.dumps(registry))
        payload = self.cli("federation-search", "deterministic lookup", "--registry", str(self.registry), "--project", "game")
        self.assertEqual([], payload["projects"][0]["results"])
        help_text = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "federation-search", "--help"],
                                   cwd=PACKAGE, env={"PYTHONPATH": str(PACKAGE / "src")}, text=True, capture_output=True).stdout
        self.assertNotIn("--permission", help_text)

    def test_capability_is_advertised(self) -> None:
        self.assertTrue(core.capabilities_command()["capabilities"]["read_only_federation"])


if __name__ == "__main__":
    unittest.main()
