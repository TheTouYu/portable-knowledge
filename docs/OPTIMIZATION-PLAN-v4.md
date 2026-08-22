# PKC Optimization Plan v4

Status: implemented
Updated: 2026-08-22
Supersedes: not a replacement for v3; v4 is a separate feedback round
Evidence: `docs/FEEDBACK-pkc-knowledge-tree-usage-blocks-2026-08-22.md`

This is an ordinary plan, not PKC Authority. It does not create Claims,
Authority References, Project Memory, project registry, Bundle, or approval to
change another project. It addresses the real-world Genshin-TS multi-agent
shared git worktree feedback against `portable-knowledge 0.2.0rc1`.

## 1. Why v4

The governed `knowledge-plan` loop was correct but too rigid for the first
real multi-agent shared-worktree usage: a design doc and its first Claim are
written in the same working session, so the "Authority must be committed first"
rule deadlocks. The user asked for easy intake and easy query. v4 makes the
existing `--baseline worktree` opt-in real (not just help text), keeps the
default committed-baseline gate unchanged, and makes failures actionable.

## 2. Outcome

- `--baseline worktree` accepts applied-but-uncommitted maintenance and newly
  written working-tree files as Authority for that plan.
- `knowledge-plan capture` supports the same opt-in for one-command batch
  intake.
- Delta coverage errors carry a concrete repair command.
- CLI help no longer promises `--apply` for normal `new-claim` use.

## 3. Workstreams

### WS-A: Worktree baseline actually reads the working tree (implemented)

- `_authority_bytes(root, plan, path)` selects working-tree bytes for
  `baseline_mode == "worktree"` and git baseline bytes for `committed`.
- All Authority path reads switched to it:
  `add-authority-ref`, `_authority_registry_overlay`,
  `refresh-authority-ref` (all-stale + single), `_validate_authority_path`,
  `check_delta`, `_assert_finalized_environment`,
  `_overlay_authority_rel_paths`, `_affected_authority_refs`.
- Committed-mode dirty checks are preserved and their error message now
  mentions `--baseline worktree` as an explicit alternative.
- `init --help` now says worktree accepts newly written working-tree files.

### WS-B: Same-batch doc + claim ingestion (implemented)

- `knowledge-plan capture --file` gains `--baseline {committed,worktree}`.
- Capture draft JSON/Markdown supports optional `baseline_mode`.
- New regression test: one-command capture with an untracked design doc
  finalizes successfully in worktree mode.

### WS-C: Actionable failure guidance (implemented)

- `AUTHORITY_FACT_COVERAGE` delta findings now include:
  - `message`: names the Claim and missing fact classes;
  - `recommended_action`: a ready-to-run `knowledge-plan add-authority-ref`
    command template.
- `PLAN_FACT_COVERAGE` at `add-authority-ref` time names the undeclared fact
  classes and suggests `revise-claim` or dropping those `--fact-class` values.

### WS-D: CLI honesty (implemented)

- `new-claim`/`revise-claim` `--apply` help states it is disabled in normal
  production mode and only for maintainer recovery with `--compatibility-mode`.

## 4. Acceptance

- Focused contract tests:
  - `test_worktree_baseline_accepts_new_untracked_authority_doc`;
  - `test_capture_worktree_baseline_accepts_untracked_authority_doc`;
  - capture delta failure asserts `recommended_action`.
- Full test suite passes (`189 tests`).
- Default `committed` behavior unchanged: untracked/dirty Authority paths still
  fail closed with `PLAN_AUTHORITY_NOT_COMMITTED` / `PLAN_AUTHORITY_WORKTREE_DIRTY`.

## 5. Exclusions and invariants

- No weakening of committed-mode permission, lifecycle, Authority coverage,
  provenance, staged validation, or exact-hash checks.
- Worktree mode is explicit opt-in only; it does not change the default or
  legacy behavior.
- No Git mutation was performed by this plan's implementation; the user
  explicitly requested the follow-up commit separately.
- The pre-existing query `--level` default 1→2 change (already committed in
  `541c289`) remains outside this plan's scope.
