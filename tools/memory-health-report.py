#!/usr/bin/env python3
"""Memory Health Report — 生成跨项目长期记忆健康快照。

用法:
  python3 tools/memory-health-report.py --target /path/to/project [--output report.json]

输出 JSON 包含：
  - 项目元数据（runtime 版本、commit）
  - Claims 统计（总数、按 lifecycle/confirmation/conflict 分布）
  - Topic 统计（总数、按 node 分布）
  - Bundle 最近历史
  - 检索评估（如果项目有 retrieval-evaluation.json）
  - 原始数据（用于对比基线）

首次运行自动保存基线到 project/.local/knowledge/memory-baseline.json。
后续运行与基线对比，标注差异。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def eprint(*a, **kw):
    print(*a, file=sys.stderr, **kw)


def run_pkc(project: Path, args: list[str]) -> dict:
    """Run project's PKC wrapper and return parsed JSON."""
    wrapper = project / "tools/pkc.py"
    if not wrapper.is_file():
        raise SystemExit(f"Project {project} has no tools/pkc.py wrapper")
    result = subprocess.run(
        [sys.executable, str(wrapper), *args],
        cwd=project, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        # Try to parse stdout as JSON error payload
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            pass
        # Try stderr
        if result.stderr.strip():
            sys.stderr.write(result.stderr)
        raise SystemExit(f"PKC command failed (exit {result.returncode}): {' '.join(args)}")
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        raise SystemExit(f"PKC output not JSON: {e}\n{result.stdout[:500]}")


def collect_claims_info(project: Path) -> dict:
    """Collect all claims via tree structure (node → topics → claim_count)."""
    tree = run_pkc(project, ["tree", "--format", "json"])
    nodes = tree.get("nodes", [])
    topics = []
    claims_by_topic = {}
    total_claims = 0
    for node in nodes:
        for topic in node.get("topics", []):
            tid = topic.get("id", "?")
            tc = topic.get("claim_count", 0)
            claims_by_topic[tid] = tc
            total_claims += tc
            topics.append(topic)

    # Sample claims via a broad query to get lifecycle/confirmation stats
    broad = run_pkc(project, ["query", "--level", "2", "--limit", "200", "--status", "any", "--format", "json", "的"])
    results = broad.get("results", [])

    lifecycle_counts = Counter()
    confirmation_counts = Counter()
    conflict_counts = Counter()
    for r in results:
        lifecycle_counts[r.get("lifecycle", "unknown")] += 1
        confirmation_counts[r.get("confirmation", "unknown")] += 1
        conflict_counts[r.get("conflict", "unknown")] += 1

    return {
        "node_count": len(nodes),
        "topic_count": len(topics),
        "total_claims": total_claims,
        "claims_sampled": len(results),
        "lifecycle_distribution": dict(lifecycle_counts),
        "confirmation_distribution": dict(confirmation_counts),
        "conflict_distribution": dict(conflict_counts),
        "claims_by_topic": claims_by_topic,
        "topics": topics,
        "nodes": nodes,
    }


def collect_bundle_history(project: Path) -> dict:
    """Get recent bundle status."""
    try:
        status = run_pkc(project, ["bundle-status", "--format", "json"])
        return {
            "bundles": status.get("bundles", []),
            "bundle_count": len(status.get("bundles", [])),
        }
    except SystemExit:
        return {"bundles": [], "bundle_count": 0, "error": "bundle-status failed"}


def collect_capabilities(project: Path) -> dict:
    """Get runtime version info."""
    try:
        caps = run_pkc(project, ["capabilities", "--format", "json"])
        return {
            "runtime_version": caps.get("runtime_version", "?"),
            "core_version": caps.get("core_version", "?"),
            "capabilities": caps,
        }
    except SystemExit:
        return {"runtime_version": "?", "core_version": "?"}


def collect_retrieval_eval(project: Path) -> dict:
    """Run retrieval evaluation if available."""
    eval_script = project / "tools/evaluate_pkc_retrieval.py"
    eval_data = project / "data/knowledge/retrieval-evaluation.json"
    if not eval_script.is_file() or not eval_data.is_file():
        return {"available": False}

    result = subprocess.run(
        [sys.executable, str(eval_script)],
        cwd=project, capture_output=True, text=True, check=False
    )
    try:
        return {"available": True, "output": json.loads(result.stdout)}
    except (json.JSONDecodeError, ValueError):
        return {"available": True, "raw_output": result.stdout, "stderr": result.stderr}


def collect_vector_status(project: Path) -> dict:
    """Check vector index status."""
    vector_dir = project / ".local/knowledge/vector"
    index_file = vector_dir / "index.json"
    cache_file = vector_dir / "embedding-cache.json"
    return {
        "index_exists": index_file.is_file(),
        "cache_exists": cache_file.is_file(),
        "index_size_bytes": index_file.stat().st_size if index_file.is_file() else 0,
        "cache_size_bytes": cache_file.stat().st_size if cache_file.is_file() else 0,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PKC Memory Health Report")
    parser.add_argument("--target", required=True, help="Target project path")
    parser.add_argument("--output", help="Output JSON file path (default: stdout)")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not (target / "tools/pkc-lock.json").is_file():
        raise SystemExit(f"Not a PKC project (no tools/pkc-lock.json): {target}")

    eprint(f"🔍 Scanning {target} ...")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": str(target),
        "project_name": target.name,
    }

    eprint("  capabilities ...")
    report["capabilities"] = collect_capabilities(target)

    eprint("  claims & topics ...")
    report["knowledge"] = collect_claims_info(target)

    eprint("  bundles ...")
    report["bundles"] = collect_bundle_history(target)

    eprint("  retrieval evaluation ...")
    report["retrieval_eval"] = collect_retrieval_eval(target)

    eprint("  vector index ...")
    report["vector"] = collect_vector_status(target)

    # Load/save baseline
    baseline_dir = target / ".local/knowledge"
    baseline_file = baseline_dir / "memory-baseline.json"
    if baseline_file.is_file():
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        report["baseline"] = baseline
        # Compute diff
        old_claims = baseline.get("knowledge", {}).get("total_claims", 0)
        new_claims = report["knowledge"].get("total_claims", 0)
        report["diff"] = {
            "claims_change": new_claims - old_claims,
            "claims_change_pct": round((new_claims - old_claims) / max(old_claims, 1) * 100, 1),
        }
    else:
        report["baseline"] = None
        report["diff"] = None

    # Save new baseline
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    eprint(f"💾 Baseline saved to {baseline_file}")

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        eprint(f"📄 Report written to {args.output}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # Summary
    k = report["knowledge"]
    caps = report["capabilities"]
    eprint(f"\n{'='*50}")
    eprint(f"📊 Memory Health Summary — {target.name}")
    eprint(f"  Runtime: {caps.get('runtime_version', '?')}")
    eprint(f"  Topics:  {k.get('topic_count', 0)}")
    eprint(f"  Claims:  {k.get('total_claims', 0)} (sampled {k.get('claims_sampled', 0)})")
    if report["diff"]:
        d = report["diff"]
        eprint(f"  Change:  {d['claims_change']:+d} claims ({d['claims_change_pct']}%)")
    eprint(f"  Bundles: {report['bundles'].get('bundle_count', 0)}")
    if report["retrieval_eval"].get("available"):
        re = report["retrieval_eval"]["output"]
        eprint(f"  Retrieval eval: {re.get('summary', '?')}")
    vec = report["vector"]
    eprint(f"  Vector index: {'✓' if vec.get('index_exists') else '✗'} ({vec.get('index_size_bytes', 0)} bytes)")
    eprint(f"{'='*50}")


if __name__ == "__main__":
    main()