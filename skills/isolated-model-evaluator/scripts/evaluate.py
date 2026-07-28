#!/usr/bin/env python3
"""Run and summarize an isolated Pi model evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_EXCLUDES = {".git", ".local", "__pycache__"}
SAFETY_SUFFIX = """

EVALUATION SAFETY BOUNDARY:
- Treat this as an isolated verification, not permission to change the project.
- Do not use --apply or perform Git mutations unless the task explicitly requires them.
- Report tool/documentation inconsistencies instead of silently guessing.
- Do not read or print credentials, secrets, raw private mappings, or unrestricted sensitive materials.
""".strip()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path, extra_excludes: set[str]) -> dict[str, dict[str, Any]]:
    excluded = DEFAULT_EXCLUDES | extra_excludes
    result: dict[str, dict[str, Any]] = {}
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in excluded]
        names = files + [name for name in dirs if (current_path / name).is_symlink()]
        for name in names:
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    result[rel] = {"type": "symlink", "target": os.readlink(path)}
                elif stat.S_ISREG(info.st_mode):
                    result[rel] = {
                        "type": "file", "sha256": file_digest(path),
                        "mode": stat.S_IMODE(info.st_mode),
                    }
            except FileNotFoundError:
                continue
    return result


def workspace_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_paths, after_paths = set(before), set(after)
    modified = sorted(path for path in before_paths & after_paths if before[path] != after[path])
    added, removed = sorted(after_paths - before_paths), sorted(before_paths - after_paths)
    return {"changed": bool(added or removed or modified), "added": added,
            "removed": removed, "modified": modified}


def text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content
                          if isinstance(item, dict) and item.get("type") == "text")
    return ""


def parse_trace(raw: str) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    final_text = ""
    assistant_turns = 0
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
             "reasoning": 0, "cost_usd": 0.0}
    malformed = 0

    for line_number, line in enumerate(raw.splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if event.get("type") != "message_end":
            continue
        message = event.get("message", {})
        role = message.get("role")
        if role == "assistant":
            assistant_turns += 1
            for item in message.get("content", []):
                if item.get("type") == "toolCall":
                    record = {
                        "index": len(calls) + 1,
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "arguments": item.get("arguments", {}),
                        "is_error": None,
                        "result_excerpt": "",
                    }
                    calls.append(record)
                    if record["id"]:
                        by_id[record["id"]] = record
                elif item.get("type") == "text":
                    final_text = item.get("text", "")
            current = message.get("usage", {})
            usage["input"] += int(current.get("input", 0) or 0)
            usage["output"] += int(current.get("output", 0) or 0)
            usage["cache_read"] += int(current.get("cacheRead", 0) or 0)
            usage["cache_write"] += int(current.get("cacheWrite", 0) or 0)
            usage["reasoning"] += int(current.get("reasoning", 0) or 0)
            usage["cost_usd"] += float((current.get("cost") or {}).get("total", 0) or 0)
        elif role == "toolResult":
            call_id = message.get("toolCallId")
            output = text_content(message.get("content"))
            is_error = bool(message.get("isError", False))
            record = by_id.get(call_id)
            if record:
                record["is_error"] = is_error
                record["result_excerpt"] = output[:2000]
            if is_error:
                errors.append({"tool_call_id": call_id, "tool": message.get("toolName"),
                               "output_excerpt": output[:4000]})

    usage["cost_usd"] = round(usage["cost_usd"], 8)
    return {
        "assistant_turns": assistant_turns,
        "tool_calls": len(calls),
        "tool_errors": len(errors),
        "final_answer_chars": len(final_text),
        "malformed_trace_lines": malformed,
        "usage": usage,
        "tools": calls,
        "errors": errors,
        "final_text": final_text,
    }


def resolve_skill(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.is_dir():
        path = path / "SKILL.md"
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"skill not found: {value}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task")
    task_group.add_argument("--task-file", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--provider", default="aijws", help="Pi provider (default: aijws)")
    parser.add_argument("--model", default="gpt-5.6-luna", help="Pi model (default: gpt-5.6-luna)")
    parser.add_argument("--thinking", default="medium", help="Pi thinking level (default: medium)")
    parser.add_argument("--tools", default="read,bash")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(f"/tmp/isolated-model-eval-{int(time.time())}"))
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--assert-no-changes", action="store_true")
    parser.add_argument("--allow-tool-errors", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"project root not found: {root}")
    try:
        skills = [resolve_skill(root, value) for value in args.skill]
    except ValueError as exc:
        parser.error(str(exc))
    task = args.task if args.task is not None else args.task_file.expanduser().read_text("utf-8")
    prompt = task.rstrip() + "\n\n" + SAFETY_SUFFIX
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    before = snapshot(root, set(args.exclude))
    command = [
        "pi", "--print", "--mode", "json", "--no-session",
        "--tools", args.tools, "--no-context-files", "--no-skills",
    ]
    if args.provider:
        command.extend(["--provider", args.provider])
    if args.model:
        command.extend(["--model", args.model])
    if args.thinking:
        command.extend(["--thinking", args.thinking])
    for skill in skills:
        command.extend(["--skill", str(skill)])
    command.extend(["--no-extensions", "--no-prompt-templates", "--no-themes",
                    "--approve", prompt])

    invocation = {
        "schema_version": SCHEMA_VERSION, "root": str(root),
        "provider": args.provider, "model": args.model, "thinking": args.thinking,
        "tools": args.tools.split(","), "skills": [str(path) for path in skills],
        "assert_no_changes": args.assert_no_changes,
        "command": command[:-1] + ["<TASK_WITH_SAFETY_BOUNDARY>"],
    }
    (output_dir / "task.md").write_text(prompt + "\n", "utf-8")
    (output_dir / "invocation.json").write_text(
        json.dumps(invocation, ensure_ascii=False, indent=2) + "\n", "utf-8")

    started = time.monotonic()
    timed_out = False
    try:
        process = subprocess.run(
            command, cwd=root, text=True, encoding="utf-8",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=args.timeout, check=False,
        )
        exit_code, raw, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        raw = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    elapsed = round(time.monotonic() - started, 2)
    (output_dir / "trace.jsonl").write_text(raw, "utf-8")
    parsed = parse_trace(raw)
    (output_dir / "final.md").write_text(parsed["final_text"] + ("\n" if parsed["final_text"] else ""), "utf-8")

    after = snapshot(root, set(args.exclude))
    workspace = workspace_diff(before, after)
    assertions = {
        "process_exit_zero": exit_code == 0,
        "final_answer_present": bool(parsed["final_text"].strip()),
        "no_tool_errors": parsed["tool_errors"] == 0,
        "no_workspace_changes": not workspace["changed"],
    }
    ok = assertions["process_exit_zero"] and assertions["final_answer_present"]
    if not args.allow_tool_errors:
        ok = ok and assertions["no_tool_errors"]
    if args.assert_no_changes:
        ok = ok and assertions["no_workspace_changes"]

    report = {
        "schema_version": SCHEMA_VERSION, "ok": ok,
        "process": {"exit_code": exit_code, "elapsed_seconds": elapsed,
                    "timed_out": timed_out, "stderr_excerpt": stderr[-4000:]},
        "model": {"provider": args.provider, "model": args.model,
                  "thinking": args.thinking},
        "trace": {key: parsed[key] for key in (
            "assistant_turns", "tool_calls", "tool_errors",
            "final_answer_chars", "malformed_trace_lines")},
        "usage": parsed["usage"], "workspace": workspace,
        "assertions": assertions, "tools": parsed["tools"], "errors": parsed["errors"],
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({
        "ok": ok, "output_dir": str(output_dir), "exit_code": exit_code,
        "elapsed_seconds": elapsed, "tool_calls": parsed["tool_calls"],
        "tool_errors": parsed["tool_errors"], "cost_usd": parsed["usage"]["cost_usd"],
        "workspace_changed": workspace["changed"],
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
