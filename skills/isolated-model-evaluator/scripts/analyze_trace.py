#!/usr/bin/env python3
"""analyze_trace.py — 评估 trace 自动化分析（长期资产：每轮评估后一键复盘）

用法:
  python3 analyze_trace.py <trace.jsonl> [--output REPORT.md] [--round N]

从 Pi trace.jsonl 提取子代理行为画像：
  1. 工具调用序列（名称 + 命令摘要 + 阶段分类）
  2. 阶段分布（读技能/写脚本/管道/核验/考古——按文件路径与命令特征）
  3. 指标汇总（调用数、错误、思考/正文字符）
输出 markdown 报告，供技能迭代与复盘直接引用。

注：trace 事件无时间戳（仅 session 有 ISO 时间），耗时不可得；"考古-历史产物"
按命令特征精确匹配（cp items / 读取旧轮产物），不含写当前轮输出目录。
"""
import json, os, re, argparse
from collections import Counter

CURRENT = None  # 当前轮目录名（--round），用于区分"写自己目录"与"读历史产物"

def stage_of(args):
    cmd = args.get('command') or ''
    path = args.get('path') or ''
    if path and re.search(r'(SKILL|METHODOLOGY|\.md$)', path):
        return '读技能/文档'
    if path and re.search(r'(src/|web/|\.ts$|index\.html)', path):
        return '考古-源码'
    if cmd and re.search(r'(benchmark/(?!connectivity-check)|validator|spec\.md|runs/)', cmd):
        return '考古-benchmark'
    if cmd and re.search(r'(cp .*items\.json|cat /tmp/ferris-eval\d+/(?!' + (CURRENT or 'x') + r'))', cmd):
        return '考古-历史产物'
    if cmd and re.search(r'(sweep|verify-geom|参数扫描)', cmd):
        return '离线几何建模'
    if cmd and 'run-gms-model' in cmd:
        return '管道'
    if cmd and ('connectivity-check' in cmd or 'gms.verify' in cmd or 'VERIFY_FAIL' in cmd):
        return '核验'
    if cmd and ('cat > ' in cmd or "cat >" in cmd):
        return '写脚本'
    if cmd and re.search(r'(dbg|probe)', cmd):
        return '调试脚本'
    return '其他'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace', help='trace.jsonl 路径')
    ap.add_argument('--output', default='', help='报告输出路径（缺省打印到 stdout）')
    ap.add_argument('--round', default='', help='当前轮输出目录名（如 ferris-eval9），用于区分写自己目录 vs 读历史产物')
    args = ap.parse_args()
    global CURRENT
    CURRENT = args.round

    calls = []
    errs = []
    thinking = 0
    text = 0
    tool_names = Counter()

    for line in open(args.trace):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get('type')
        if t == 'tool_execution_start':
            calls.append({'tool': ev.get('toolName'), 'args': ev.get('args', {})})
        elif t == 'tool_execution_update':
            u = ev.get('update') or ev.get('message') or {}
            if isinstance(u, dict) and u.get('isError'):
                errs.append(str(u.get('error') or u)[:200])
        elif t == 'message_update':
            e = ev.get('assistantMessageEvent', {})
            et = e.get('type')
            if et == 'thinking_delta':
                thinking += len(e.get('delta', e.get('text', '')) or '')
            elif et == 'text_delta':
                text += len(e.get('delta', e.get('text', '')) or '')
        elif t == 'message' and ev.get('message', {}).get('role') == 'assistant':
            for c in ev['message'].get('content', []):
                if c.get('type') == 'thinking':
                    thinking += len(c.get('text', ''))
                elif c.get('type') == 'text':
                    text += len(c.get('text', ''))

    for c in calls:
        c['stage'] = stage_of(c['args'])
        tool_names[c['tool']] += 1

    stage_counter = Counter(c['stage'] for c in calls)
    out = []
    out.append(f"# Trace 分析：{os.path.basename(os.path.dirname(args.trace)) or args.trace}")
    out.append("")
    out.append(f"- 工具调用：{len(calls)} 次；错误：{len(errs)}")
    out.append(f"- 思考字符：{thinking:,}；正文字符：{text:,}（思考占比 {thinking/max(1,thinking+text)*100:.0f}%）")
    out.append("")
    out.append("## 阶段分布（时间黑洞定位）")
    out.append("")
    for stage, n in stage_counter.most_common():
        out.append(f"- **{stage}**：{n} 次调用")
    out.append("")
    out.append("## 工具分布")
    out.append("")
    out.append(", ".join(f"{k}={v}" for k, v in tool_names.most_common()))
    out.append("")
    out.append("## 调用序列")
    out.append("")
    out.append("| # | 工具 | 阶段 | 摘要 |")
    out.append("|---|---|---|---|")
    for i, c in enumerate(calls):
        arg = c['args']
        s = arg.get('command') or arg.get('path') or ''
        s = re.sub(r'\s+', ' ', s)[:90]
        out.append(f"| {i} | {c['tool']} | {c['stage']} | `{s}` |")
    out.append("")
    if errs:
        out.append("## 错误")
        out.append("")
        for e in errs[:10]:
            out.append(f"- `{e}`")

    report = "\n".join(out)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"报告已写入 {args.output}")
    else:
        print(report)

if __name__ == '__main__':
    main()
