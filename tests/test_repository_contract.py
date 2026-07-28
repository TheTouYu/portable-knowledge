from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "minimal-project"


class RepositoryContractTests(unittest.TestCase):
    def test_fresh_agent_entry_documents_exist_and_link_to_each_other(self):
        for relative in (
            "README.md",
            "AGENTS.md",
            "INSTALL.md",
            "docs/QUICKSTART.md",
            "docs/SEMANTIC-CHANGES.md",
            "skills/pkc-project-operator/SKILL.md",
            "skills/pkc-project-operator/references/MODES.md",
            "skills/pkc-project-operator/scripts/pkc_operator.py",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for relative in ("AGENTS.md", "INSTALL.md", "docs/QUICKSTART.md", "docs/SEMANTIC-CHANGES.md"):
            self.assertIn(relative, readme)
        repository_url = "https://github.com/TheTouYu/portable-knowledge"
        self.assertIn(repository_url, readme)
        self.assertIn(repository_url, (ROOT / "INSTALL.md").read_text(encoding="utf-8"))
        self.assertIn(repository_url, (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_example_is_complete_and_ignores_projection(self):
        config = json.loads((EXAMPLE / "project-intelligence.json").read_text(encoding="utf-8"))
        self.assertEqual(config["pkc"]["version"], "0.2.0rc3")
        for role in config["memory"]["roles"]:
            self.assertTrue((EXAMPLE / role["path"]).is_file(), role)
        authority = config["authority"]
        for key in ("registry", "actors"):
            self.assertTrue((EXAMPLE / authority[key]).is_file(), key)
        self.assertIn(".local/", (EXAMPLE / ".gitignore").read_text(encoding="utf-8"))

    def test_public_assets_contain_no_source_project_names_or_personal_absolute_paths(self):
        excluded = {".git", ".venv", "dist", "build", "__pycache__"}
        patterns = (
            re.compile(r"AI Brand Lab", re.IGNORECASE),
            re.compile(r"Genshin", re.IGNORECASE),
            re.compile(r"/home/[A-Za-z0-9_.-]+/"),
            re.compile(r"[A-Z]:\\Users\\", re.IGNORECASE),
        )
        public_roots = [ROOT / name for name in ("src", "schemas", "domain-packs", "docs", "examples", "skills")]
        paths = [ROOT / name for name in ("README.md", "AGENTS.md", "INSTALL.md", "pyproject.toml")]
        paths.extend(path for base in public_roots for path in base.rglob("*") if path.is_file())
        for path in paths:
            if any(part in excluded for part in path.parts):
                continue
            if path.suffix not in {".md", ".json", ".toml", ".py", ".gitignore"} and path.name != ".gitignore":
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                self.assertIsNone(pattern.search(text), f"{pattern.pattern} in {path.relative_to(ROOT)}")

    def test_agent_contract_forbids_known_bypass_paths(self):
        contract = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for required in (
            "Do not set `PYTHONPATH`",
            "Never read or modify SQLite directly",
            "`bundle-create --manifest`",
            "exact content hash",
            "knowledge-plan",
        ):
            self.assertIn(required, contract)


if __name__ == "__main__":
    unittest.main()
