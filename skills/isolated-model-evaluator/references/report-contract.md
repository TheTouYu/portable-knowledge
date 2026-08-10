# Evaluation Report Contract

The evaluator writes deterministic artifacts outside the repository by default.

## `report.json`

Top-level fields:

```json
{
  "schema_version": 1,
  "ok": true,
  "process": {
    "exit_code": 0,
    "elapsed_seconds": 79.65,
    "timed_out": false
  },
  "model": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "thinking": "max"
  },
  "trace": {
    "assistant_turns": 8,
    "tool_calls": 20,
    "tool_errors": 0,
    "final_answer_chars": 3285
  },
  "usage": {
    "input": 42570,
    "output": 2795,
    "cache_read": 61952,
    "cache_write": 0,
    "reasoning": 0,
    "cost_usd": 0.00655352
  },
  "workspace": {
    "changed": false,
    "added": [],
    "removed": [],
    "modified": []
  },
  "assertions": {
    "process_exit_zero": true,
    "final_answer_present": true,
    "no_tool_errors": true,
    "no_workspace_changes": true
  },
  "tools": [],
  "errors": []
}
```

## Tool records

Each `tools` entry preserves execution order:

```json
{
  "index": 1,
  "name": "bash",
  "arguments": {"command": "python3 scripts/example.py --help"},
  "is_error": false,
  "result_excerpt": "usage: ..."
}
```

Arguments can contain project content. Review before sharing a report. The runner does not intentionally record environment variables or API keys, but a child command could print them; prompts must prohibit secret access.

## Workspace comparison

The runner snapshots regular files and symbolic links below the project root. It excludes `.git/` and `.local/` by default because they are Git internals or rebuildable projections. Existing modified files are fingerprinted, so a child editing an already-dirty file is still detected.

- `added`: path did not exist before the child run;
- `removed`: path existed before but not after;
- `modified`: file content/mode or symlink target changed.

This is detection, not prevention. Use an isolated worktree/container for destructive or adversarial tests.

## Interpreting success

`ok=true` means the configured generic assertions passed. It does not automatically verify arbitrary facts in the final answer. The parent evaluator must compare the final answer and tool results to task-specific acceptance criteria.

Recommended comparison order for documentation improvements:

1. task-specific correctness;
2. unexpected workspace changes;
3. tool errors;
4. silent guessing or undocumented recovery seen in trace;
5. tool-call count;
6. elapsed time;
7. cost.

Do not optimize cost by removing necessary validation or evidence.

## Trace inspection

`trace.jsonl` is the authoritative model interaction trace. Search event types and errors with a local script rather than loading the entire trace into normal project context. Typical fields include:

- assistant tool calls and usage;
- tool results with `isError`;
- final assistant text;
- process-level errors.

For large traces, inspect only the failing call and neighboring events first.
