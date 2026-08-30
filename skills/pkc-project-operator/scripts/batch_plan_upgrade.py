#!/usr/bin/env python3
"""Batch plan-upgrade for projects locked to one Portable Knowledge Core source.

Contract-preserving convenience wrapper: planning is side-effect-free for
targets (it may build/cache a wheel from the exact source commit) and apply
stays an explicit, human-reviewed, per-project confirmation even with --apply.

Example:
  batch_plan_upgrade.py \
    --operator /path/to/pkc_operator.py \
    --projects /path/to/project-a /path/to/project-b \
    --source-repository /path/to/portable-knowledge \
    --source-commit <40-char commit> \
    --representative-query "bounded project question" \
    --project-check "make test"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_one(operator: Path, project: Path, args: argparse.Namespace, out: Path) -> dict:
    cmd = [sys.executable, str(operator), "plan-upgrade",
           "--target", str(project),
           "--source-repository", args.source_repository,
           "--source-commit", args.source_commit,
           "--representative-query", args.representative_query,
           "--project-check", args.project_check,
           "--output", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    row = {"project": str(project), "plan_path": str(out), "returncode": proc.returncode}
    try:
        # apply-plan verifies the plan's embedded canonical plan_hash (sha256 over the
        # canonical JSON with the plan_hash key removed), NOT the file's byte hash.
        row["plan_hash"] = json.loads(out.read_text(encoding="utf-8"))["plan_hash"]
    except (OSError, ValueError, KeyError):
        row["plan_hash"] = None
    tail = (proc.stderr or proc.stdout).strip()
    row["output_tail"] = tail[-400:] if row["returncode"] else ""
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--operator", required=True, help="path to pkc_operator.py")
    ap.add_argument("--projects", nargs="+", required=True,
                    help="project roots that contain tools/pkc-lock.json")
    ap.add_argument("--source-repository", required=True)
    ap.add_argument("--source-commit", required=True)
    ap.add_argument("--representative-query", required=True,
                    help="bounded project question used by the per-plan smoke check")
    ap.add_argument("--project-check", required=True,
                    help="project test command executed by each plan's verification")
    ap.add_argument("--output-dir", default="/tmp/pkc-batch-upgrade")
    ap.add_argument("--apply", action="store_true",
                    help="after planning, prompt per project and run apply-plan --human-reviewed")
    args = ap.parse_args()

    operator = Path(args.operator).resolve()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for raw in args.projects:
        project = Path(raw).resolve()
        lock = project / "tools" / "pkc-lock.json"
        if not lock.is_file():
            rows.append({"project": str(project), "status": "skipped_no_lock"})
            continue
        current = json.loads(lock.read_text(encoding="utf-8")).get("source_commit", "")
        if current == args.source_commit:
            rows.append({"project": str(project), "status": "already_on_target",
                         "source_commit": current})
            continue
        out = outdir / f"{project.name}-upgrade-plan.json"
        row = plan_one(operator, project, args, out)
        row["previous_commit"] = current
        row["status"] = "planned" if row["returncode"] == 0 and row["plan_hash"] else "plan_failed"
        rows.append(row)

    print(json.dumps(rows, ensure_ascii=False, indent=1))
    summary = Path(outdir / "batch-summary.json")
    summary.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = all(r.get("status") in {"planned", "already_on_target", "skipped_no_lock"} for r in rows)
    print(f"summary: {summary} | all_planned={ok}", file=sys.stderr)

    if args.apply and ok:
        for row in rows:
            if row.get("status") != "planned":
                continue
            answer = input(f"apply {row['project']} (plan hash {row['plan_hash']})? "
                           f"type project name to confirm: ")
            if answer.strip() != Path(row["project"]).name:
                print(f"  skipped {row['project']}")
                continue
            proc = subprocess.run([sys.executable, str(operator), "apply-plan",
                                   "--plan", row["plan_path"],
                                   "--plan-hash", row["plan_hash"],
                                   "--human-reviewed"], capture_output=True, text=True)
            tail = (proc.stderr or proc.stdout).strip()[-300:]
            print(f"  apply exit={proc.returncode} {tail}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
