#!/usr/bin/env bash
# run_skill_eval.sh — 技能评估一键封装（轮次参数化 + 完成后自动 trace 分析）
#
# 用法:
#   run_skill_eval.sh <round-name> [--skill PATH] [--task-file PATH] [--provider P] [--model M] [--timeout N] [--analyze]
#
# 行为:
#   1. 实例化任务模板（templates/ferris-task.md，{ROUND} 占位符 → /tmp/<round-name>/task.md）
#   2. evaluate.py 执行（输出 /tmp/<round-name>）
#   3. --analyze 时自动跑 analyze_trace.py 并落盘 /tmp/<round-name>/TRACE-ANALYSIS.md
#
# 例:
#   run_skill_eval.sh ferris-eval10 --analyze
#   run_skill_eval.sh ferris-eval11 --provider opencode-go --model deepseek-v4-flash --timeout 1500
set -euo pipefail

ROUND="${1:?用法: run_skill_eval.sh <round-name> [--skill PATH] ...}"
shift

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$HERE/../.."        # 默认技能 = model-build-test（同仓库 skills 下）
TASK_TEMPLATE="$HERE/../templates/ferris-task.md"
PROVIDER=""
MODEL=""
TIMEOUT=1500
ANALYZE=0
ROOT="$(cd "$HERE/../../../.." && pwd)/genshin-model-studio"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2 ;;
    --task-file) TASK_TEMPLATE="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --analyze) ANALYZE=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

OUT="/tmp/$ROUND"
mkdir -p "$OUT"
sed "s|{ROUND}|$OUT|g" "$TASK_TEMPLATE" > "$OUT/task.md"
echo "== 任务文件: $OUT/task.md"

ARGS=(--root "$ROOT" --skill "$SKILL" --task-file "$OUT/task.md" --output-dir "$OUT" --tools read,bash --timeout "$TIMEOUT")
[ -n "$PROVIDER" ] && ARGS+=(--provider "$PROVIDER")
[ -n "$MODEL" ] && ARGS+=(--model "$MODEL")

echo "== evaluate.py ${ARGS[*]}"
python3 "$HERE/evaluate.py" "${ARGS[@]}" 2>&1 | tee "$OUT/run.log" || echo "== 评估结束（非零退出）"

if [ "$ANALYZE" = "1" ] && [ -f "$OUT/trace.jsonl" ]; then
  echo "== trace 分析"
  python3 "$HERE/analyze_trace.py" "$OUT/trace.jsonl" --round "$ROUND" --output "$OUT/TRACE-ANALYSIS.md" || true
  head -30 "$OUT/TRACE-ANALYSIS.md"
fi
echo "== 产物: $OUT"
