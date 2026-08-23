#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索触发率（忆侧可量化指标）——卡住点后第一动作是否检索。

用法:
  python3 retrieval_trigger_rate.py <session.jsonl.zstd> [更多会话...]

口径（对齐 references/session-depth-analysis.md L2）:
  卡住点   = 模型可见文本命中"障碍/不确定性"信号（中英混合，排除成功汇报）。
  第一动作 = 卡住点之后最近一次 tool/call。
  检索动作 = pkc 系查询 / 会话历史(dsh-session-history) / 读技能 SKILL / 读 docs·knowledge·AGENTS·README。
  检索触发率 = 检索动作数 / 卡住点总数。

说明:
  只抓高信号障碍词（返工 / 超限 / 找不到 / 不确定 / coverage gap），
  刻意排除"失败/错误/bug/error"这类既可能是报障也可能是"0 失败"成功汇报的词。
  本工具是粗粒度自审计口径，结果须配合 eyeball 抽查，不是 ground truth。
"""
import json, sys, os, re, subprocess, datetime

STUCK_RE = re.compile(
    r"卡住|不确定|不清楚|不知道|找不到|查不到|没找到|没查到|先查|再查|查一下|查一查|需要确认|待确认|"
    r"归因错|推翻|重新推导|重做|返工|超标|超限|超出|预算(不足|超|紧|快|见底)?|不够|"
    r"coverage gap|not sure|unclear|out of budget|over budget|exceed"
)

def _norm(s):
    return s.replace("\n", " ").replace("\r", " ")

def _tool_input(d):
    for k in ("input", "arguments"):
        if k in d and d[k] is not None:
            v = d[k]
            if isinstance(v, str):
                try: v = json.loads(v)
                except Exception: v = None
            if isinstance(v, dict):
                return v
    return {}

def _call_signature(d):
    inp = _tool_input(d)
    code = inp.get("code", "") or ""
    name = d.get("name", "") or ""
    desc = (inp.get("description", "") or "")[:120] or ""
    raw = inp.get("command") or ""
    return " ".join([name, desc, code[:3000], str(raw)[:500]])

MEM_RE = re.compile(
    r"\bpkc\b|progressive-query|knowledge-search|show-claim|pkc\.py|session-history|dsh-session-"
    r"history|tools\.skill\(|SKILL\.md|AGENTS\.md|CLAUDE\.md|/docs/|/knowledge/|README"
)

def _is_retrieval(sig):
    return bool(MEM_RE.search(sig))

def summarize(path):
    if not os.path.exists(path):
        return None
    p = subprocess.Popen(["zstd","-d","-c",path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    events = []
    for line in p.stdout:
        raw = line.decode("utf-8", errors="replace").strip()
        if not raw: continue
        try: e = json.loads(raw)
        except Exception: continue
        t = e.get("type"); d = e.get("data", {})
        if t in ("assistant/message", "tool/call"):
            events.append((e.get("seq", 0), e.get("time", 0), t, d))
    p.wait()
    events.sort(key=lambda x: x[0])
    stuck = []
    for i, (seq, tm, typ, d) in enumerate(events):
        if typ != "assistant/message": continue
        msg = d.get("message", {})
        texts = [c.get("text","") for c in msg.get("content", []) if isinstance(c, dict) and c.get("type")=="text"]
        txt = _norm(" ".join(texts))
        m = STUCK_RE.search(txt)
        if not m: continue
        nxt = None
        for j in range(i+1, len(events)):
            if events[j][2] == "tool/call":
                nxt = events[j]; break
        sig = _call_signature(nxt[3]) if nxt else ""
        is_ret = _is_retrieval(sig) if nxt else False
        tt = datetime.datetime.fromtimestamp(tm/1000).strftime("%m-%d %H:%M:%S") if tm else "?"
        frag = txt[max(0, m.start()-28):m.end()+28].strip()
        act = (nxt[3].get("name","") if nxt else "(无后续)") +               (("@" + re.sub(r"\s+"," ",(_tool_input(nxt[3]).get("description","") or ""))[:44] if nxt else ""))
        stuck.append({"time": tt, "marker": m.group(0), "frag": frag, "act": act, "retrieval": is_ret})
    hits = sum(1 for s in stuck if s["retrieval"])
    return {"id": os.path.basename(os.path.dirname(path)).replace("session-", "")[:8], "stuck": stuck,
            "total": len(stuck), "hits": hits,
            "rate": (hits/len(stuck)) if stuck else None}

paths = sys.argv[1:]
agg_total = 0; agg_hits = 0
for path in paths:
    s = summarize(path)
    if s is None:
        print(f"!! MISSING {path}", file=sys.stderr); continue
    agg_total += s["total"]; agg_hits += s["hits"]
    r = s["rate"]
    print("=" * 92)
    print(f"### {s['id']}  卡住点 {s['total']}  检索 {s['hits']}  触发率 {('%.0f%%' % (r*100)) if r is not None else 'N/A'}")
    for st in s["stuck"]:
        mark = "检索" if st["retrieval"] else "未查"
        print(f"  [{mark}:{st['marker']}] {st['time']} | {st['frag'][:64]}")
        print(f"          → {st['act'][:96]}")
print("=" * 92)
r = (agg_hits/agg_total) if agg_total else None
print(f"### 合计  卡住点 {agg_total}  检索 {agg_hits}  检索触发率 {('%.0f%%' % (r*100)) if r is not None else 'N/A'}")
