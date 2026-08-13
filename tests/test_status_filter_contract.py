"""CLI-level contract tests for Claim identifiers and Authority status filtering.

Covers the shared ``--status`` vocabulary of ``query`` and ``knowledge-search``,
the ``claim_id`` field of ``knowledge-search`` results, filter-before-limit
behavior on both the deterministic and the semantic/hybrid path, and the
non-disclosure boundary for restricted Claims.
"""
from __future__ import annotations

import argparse
import contextlib
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

FIXTURE = PACKAGE / "tests/fixtures/status-filter"
CURRENT = "clm_00000000000000000000000001"
PENDING = "clm_00000000000000000000000002"
UNREGISTERED = "clm_00000000000000000000000003"
RESTRICTED = "clm_00000000000000000000000004"
CURRENT2 = "clm_00000000000000000000000005"


class StatusFilterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "fixture"
        shutil.copytree(FIXTURE, self.root)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "neutral baseline"], cwd=self.root, check=True)
        self.cli("rebuild")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *argv: str, expected: int = 0) -> dict:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = core.main(["--root", str(self.root), *argv])
        payload = json.loads(stream.getvalue())
        self.assertEqual(result, expected, payload)
        return payload

    def cli_text(self, *argv: str, expected: int = 0) -> str:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = core.main(["--root", str(self.root), *argv, "--format", "text"])
        self.assertEqual(result, expected, stream.getvalue())
        return stream.getvalue()

    def write_vector_index(self) -> None:
        index = {"schema_version": 1, "model": "text-embedding-3-small", "permission": "internal", "objects": [
            {"claim": {"id": CURRENT}, "embedding": [0.8, 0.6]},
            {"claim": {"id": PENDING}, "embedding": [1.0, 0.0]},
            {"claim": {"id": UNREGISTERED}, "embedding": [0.5, 0.87]},
            {"claim": {"id": CURRENT2}, "embedding": [0.7, 0.71]},
        ]}
        directory = self.root / ".local/pkc/vector"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.json").write_text(json.dumps(index), encoding="utf-8")

    def test_query_status_filter_uses_shared_vocabulary_and_compatible_default(self) -> None:
        # Unfiltered behavior: identical result set and ordering to the legacy path.
        unfiltered = self.cli("query", "statusfilter", "--level", "2", "--limit", "12")
        self.assertEqual([item["id"] for item in unfiltered["results"]], [PENDING, CURRENT, UNREGISTERED, CURRENT2])
        self.assertNotIn(RESTRICTED, [item["id"] for item in unfiltered["results"]])
        explicit_any = self.cli("query", "statusfilter", "--level", "2", "--limit", "12", "--status", "any")
        self.assertEqual([item["id"] for item in explicit_any["results"]], [item["id"] for item in unfiltered["results"]])
        # Each status value keeps exactly the Claims with that claim-level status.
        self.assertEqual([item["id"] for item in self.cli("query", "statusfilter", "--level", "2", "--limit", "12", "--status", "current")["results"]], [CURRENT, CURRENT2])
        self.assertEqual([item["id"] for item in self.cli("query", "statusfilter", "--level", "2", "--limit", "12", "--status", "pending_review")["results"]], [PENDING])
        self.assertEqual([item["id"] for item in self.cli("query", "statusfilter", "--level", "2", "--limit", "12", "--status", "not_registered")["results"]], [UNREGISTERED])
        # Non-claim kinds at level 1 are not dropped by the status filter.
        level_one = self.cli("query", "triage", "--level", "1", "--status", "current")
        self.assertEqual([(item["kind"], item["id"]) for item in level_one["results"]], [("topic", "topic-triage")])

    def test_query_status_filter_applies_before_limit_and_cursor(self) -> None:
        # The pending Claim ranks first lexically; a current-only page must still
        # return the current Claim instead of an empty truncated page.
        first = self.cli("query", "statusfilter", "--level", "2", "--limit", "1", "--status", "current")
        self.assertEqual([item["id"] for item in first["results"]], [CURRENT])
        second = self.cli("query", "statusfilter", "--level", "2", "--limit", "1", "--cursor", "1", "--status", "current")
        self.assertEqual([item["id"] for item in second["results"]], [CURRENT2])

    def test_knowledge_search_claim_id_equals_id_and_status_filters(self) -> None:
        unfiltered = self.cli("knowledge-search", "statusfilter", "--limit", "12")
        for item in unfiltered["results"]:
            self.assertEqual(item["claim_id"], item["id"])
        self.assertEqual([(item["claim_id"], item["authority_status"]) for item in unfiltered["results"]],
                         [(PENDING, "pending_review"), (CURRENT, "current"), (UNREGISTERED, "not_registered"), (CURRENT2, "current")])
        for status, expected in (("any", [PENDING, CURRENT, UNREGISTERED, CURRENT2]),
                                 ("current", [CURRENT, CURRENT2]),
                                 ("pending_review", [PENDING]),
                                 ("not_registered", [UNREGISTERED])):
            payload = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--status", status)
            self.assertEqual([item["claim_id"] for item in payload["results"]], expected)
            self.assertTrue(all(item["claim_id"] == item["id"] for item in payload["results"]))

    def test_knowledge_search_status_filter_applies_before_limit(self) -> None:
        # PENDING ranks first lexically; the limited current-only page must not be empty.
        payload = self.cli("knowledge-search", "statusfilter", "--limit", "1", "--status", "current")
        self.assertEqual([item["claim_id"] for item in payload["results"]], [CURRENT])

    def test_hybrid_status_filter_matches_lexical_path(self) -> None:
        self.write_vector_index()
        with mock.patch("portable_knowledge.experience.embed_texts", return_value=([[1.0, 0.0]], 1, "text-embedding-3-small")):
            unfiltered = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--semantic")
            self.assertEqual("hybrid", unfiltered["mode"])
            # Without a filter the pending Claim tops the hybrid ranking.
            self.assertEqual(unfiltered["results"][0]["claim_id"], PENDING)
            current = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--semantic", "--status", "current")
            self.assertEqual("hybrid", current["mode"])
            self.assertEqual([item["claim_id"] for item in current["results"]], [CURRENT, CURRENT2])
            pending = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--semantic", "--status", "pending_review")
            self.assertEqual([item["claim_id"] for item in pending["results"]], [PENDING])
            limited = self.cli("knowledge-search", "statusfilter", "--limit", "1", "--semantic", "--status", "current")
            self.assertEqual([item["claim_id"] for item in limited["results"]], [CURRENT])
        lexical = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--status", "current")
        self.assertEqual({item["claim_id"] for item in lexical["results"]}, {item["claim_id"] for item in current["results"]})

    def test_status_option_contract_is_shared_and_rejects_unknown_values(self) -> None:
        parser = core.parser_build()
        subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))

        def status_choices(name: str) -> tuple[str, ...]:
            sub = subparsers.choices[name]
            return tuple(action.choices for action in sub._actions if action.dest == "status")[0]

        self.assertEqual(status_choices("query"), status_choices("knowledge-search"))
        self.assertEqual(status_choices("query"), core.STATUS_FILTERS)
        with self.assertRaises(SystemExit):
            core.main(["--root", str(self.root), "query", "statusfilter", "--level", "2", "--status", "bogus"])

    def test_cli_process_entry_accepts_status_filter(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE / "src")
        completed = subprocess.run([sys.executable, "-m", "portable_knowledge.cli", "--root", str(self.root),
                                    "knowledge-search", "statusfilter", "--limit", "12", "--status", "current"],
                                   cwd=PACKAGE, env=env, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual([item["claim_id"] for item in payload["results"]], [CURRENT, CURRENT2])

    def test_status_filter_never_discloses_restricted_claims(self) -> None:
        for command in (("query", "statusfilter", "--level", "2", "--limit", "12", "--status", "pending_review"),
                        ("knowledge-search", "statusfilter", "--limit", "12", "--status", "pending_review")):
            payload = self.cli(*command)
            self.assertNotIn(RESTRICTED, [item.get("claim_id", item.get("id")) for item in payload["results"]])
            self.assertNotIn(RESTRICTED, json.dumps(payload))
        denied = self.cli("show-claim", RESTRICTED, expected=1)
        self.assertIn("not available", denied["errors"][0]["message"])
        # An authorized restricted reader still benefits from the same filter.
        authorized = self.cli("knowledge-search", "statusfilter", "--limit", "12", "--status", "pending_review", "--permission", "restricted")
        self.assertEqual([item["claim_id"] for item in authorized["results"]], [PENDING, RESTRICTED])

    def test_knowledge_search_text_output_lists_claim_id_and_status(self) -> None:
        text = self.cli_text("knowledge-search", "statusfilter", "--limit", "3", "--status", "current")
        self.assertIn(CURRENT, text)
        self.assertIn("[current]", text)
        self.assertNotIn(PENDING, text)


if __name__ == "__main__":
    unittest.main()
