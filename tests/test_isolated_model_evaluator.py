from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills/isolated-model-evaluator/scripts/evaluate.py"
SPEC = importlib.util.spec_from_file_location("isolated_model_evaluator", MODULE_PATH)
evaluator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(evaluator)


class IsolatedModelEvaluatorTests(unittest.TestCase):
    def test_load_dotenv_parses_values_without_overwriting_environment(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
                evaluator.os.environ, {"EXISTING": "keep"}, clear=True):
            dotenv = Path(tmp) / ".env"
            dotenv.write_text(
                "# comment\nEXISTING=replace\nPLAIN=value\nQUOTED=\"quoted value\"\nEQUALS=a=b\n",
                encoding="utf-8",
            )
            evaluator.load_dotenv(dotenv)
            self.assertEqual(evaluator.os.environ["EXISTING"], "keep")
            self.assertEqual(evaluator.os.environ["PLAIN"], "value")
            self.assertEqual(evaluator.os.environ["QUOTED"], "quoted value")
            self.assertEqual(evaluator.os.environ["EQUALS"], "a=b")

    def test_snapshot_detects_existing_file_change_and_ignores_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("before", encoding="utf-8")
            (root / ".local").mkdir()
            (root / ".local/cache.txt").write_text("one", encoding="utf-8")
            before = evaluator.snapshot(root, set())
            (root / "a.txt").write_text("after", encoding="utf-8")
            (root / "b.txt").write_text("new", encoding="utf-8")
            (root / ".local/cache.txt").write_text("two", encoding="utf-8")
            after = evaluator.snapshot(root, set())
            self.assertEqual(
                evaluator.workspace_diff(before, after),
                {"changed": True, "added": ["b.txt"], "removed": [], "modified": ["a.txt"]},
            )

    def test_parse_trace_collects_tools_errors_usage_and_final(self):
        events = [
            {"type": "message_end", "message": {
                "role": "assistant",
                "content": [{"type": "toolCall", "id": "c1", "name": "bash",
                             "arguments": {"command": "false"}}],
                "usage": {"input": 10, "output": 2, "cacheRead": 3, "cacheWrite": 4,
                          "reasoning": 1, "cost": {"total": 0.01}},
            }},
            {"type": "message_end", "message": {
                "role": "toolResult", "toolCallId": "c1", "toolName": "bash",
                "content": [{"type": "text", "text": "failed"}], "isError": True,
            }},
            {"type": "message_end", "message": {
                "role": "assistant", "content": [{"type": "text", "text": "final"}],
                "usage": {"input": 5, "output": 1, "cost": {"total": 0.02}},
            }},
        ]
        parsed = evaluator.parse_trace("\n".join(json.dumps(event) for event in events))
        self.assertEqual(parsed["assistant_turns"], 2)
        self.assertEqual(parsed["tool_calls"], 1)
        self.assertEqual(parsed["tool_errors"], 1)
        self.assertEqual(parsed["final_text"], "final")
        self.assertEqual(parsed["usage"]["input"], 15)
        self.assertEqual(parsed["usage"]["cost_usd"], 0.03)
        self.assertTrue(parsed["tools"][0]["is_error"])

    def test_resolve_skill_accepts_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills/example"
            skill.mkdir(parents=True)
            target = skill / "SKILL.md"
            target.write_text("---\nname: example\ndescription: test\n---\n", encoding="utf-8")
            self.assertEqual(evaluator.resolve_skill(root, "skills/example"), target.resolve())

    def test_main_uses_cost_effective_evaluation_defaults_when_model_options_are_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            trace = json.dumps({"type": "message_end", "message": {
                "role": "assistant", "content": [{"type": "text", "text": "done"}], "usage": {}}}) + "\n"
            completed = subprocess.CompletedProcess([], 0, stdout=trace, stderr="")
            argv = ["evaluate.py", "--root", str(root), "--task", "verify", "--output-dir", str(output)]
            with mock.patch("sys.argv", argv), mock.patch.object(evaluator.subprocess, "run", return_value=completed) as run:
                self.assertEqual(evaluator.main(), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--provider") + 1], "opencode-go")
            self.assertEqual(command[command.index("--model") + 1], "deepseek-v4-flash")
            self.assertEqual(command[command.index("--thinking") + 1], "max")
            self.assertIn("--no-context-files", command)
            self.assertIn("--no-skills", command)
            prompt = (output / "task.md").read_text(encoding="utf-8")
            self.assertIn("Reversible plans and candidate artifacts are allowed", prompt)
            self.assertNotIn("This evaluation is read-only", prompt)
            self.assertEqual(json.loads((output / "report.json").read_text(encoding="utf-8"))["ok"], True)

    def test_assert_no_changes_adds_explicit_read_only_boundary(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as output_tmp:
            root = Path(tmp)
            output = Path(output_tmp)
            trace = json.dumps({"type": "message_end", "message": {
                "role": "assistant", "content": [{"type": "text", "text": "done"}], "usage": {}}}) + "\n"
            completed = subprocess.CompletedProcess([], 0, stdout=trace, stderr="")
            argv = ["evaluate.py", "--root", str(root), "--task", "verify",
                    "--assert-no-changes", "--output-dir", str(output)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    evaluator.subprocess, "run", return_value=completed):
                self.assertEqual(evaluator.main(), 0)
            prompt = (output / "task.md").read_text(encoding="utf-8")
            self.assertIn("This evaluation is read-only: do not change the workspace", prompt)


if __name__ == "__main__":
    unittest.main()
