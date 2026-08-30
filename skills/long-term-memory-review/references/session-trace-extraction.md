# 历史会话轨迹提取（DSH zstd JSONL）

跨会话记忆评估的原材料来自 DSH 会话日志。**优先用 `dsh-session-history` 技能**；
harness 没有该技能时，用本文件的最小方法，只读、不猜。

## 会话定位

- 根目录：`~/.dsh/sessions/`
- 项目目录名 = 项目绝对路径的 `/` → `-`，例如 `/home/<user>/<project>` → `--home-<user>-<project>--`
- 单会话：`<项目目录>/<session-id>/session.jsonl.zstd`（zstd 压缩）；用 `ls -S` 按大小找主力会话（长任务往往几 MB）。

## 解压分析（勿先读原文）

```bash
zstd -d -c <session.jsonl.zstd> | python3 /tmp/trace_extract.py
```

## 事件类型与关键字段（JSONL，每行一个事件）

| type | 意义 | 关键字段 |
|---|---|---|
| `user/message` | 用户消息 | `data.content[].text`（`system-reminder` 也算在这里面）|
| `assistant/message` | 模型文本 | `data.content[]`，含 TEXT 流程推进标记 |
| `assistant/chunk` | 流式片段 | 一般不用 |
| `tool/call` | 工具调用 | `data.name` |
| `tool/result` | 工具结果 | `data.isError`，错误信息在 content |
| `step/end` | 步结束 | `data.step` |
| `turn/end` | 轮结束 | `data.reason.kind`（completed / error / interrupted）|
| `llm/retry` | 重试 | 错误信息（API 400 等高发故障）|

时间戳：顶层 `time`（epoch 毫秒）。

## 最小提取脚本 `/tmp/trace_extract.py`

```python
import json, sys, datetime, collections
errs = collections.Counter()
checkpoints = 0
print("time | type | 摘要")
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except Exception:
        continue
    t = e.get("time", 0)
    ts = datetime.datetime.fromtimestamp(t/1000).strftime("%m-%d %H:%M:%S")
    typ = e.get("type", "?")
    d = e.get("data", {})
    if typ == "user/message":
        txt = " ".join((c.get("text","") for c in d.get("content",[]) if isinstance(c, dict)))
        txt = txt.replace("\n", " ")[:120]
        # 统计上下文压缩
        if "system-reminder" in txt and ("skill catalog" in txt or "checkpoint" in txt):
            checkpoints += 1
        print(f"{ts} | USER | {txt}")
    elif typ == "assistant/message":
        txt = " ".join((c.get("text","") for c in d.get("content",[]) if isinstance(c, dict) and c.get("type")=="text"))
        txt = txt.replace("\n", " ")[:120]
        print(f"{ts} | TEXT | {txt}")
    elif typ == "tool/result" and d.get("isError"):
        errs[str(d.get("source", {}).get("kind", "tool"))] += 1
    elif typ == "turn/end":
        print(f"{ts} | TURN-END | {d.get('reason',{})}")
    elif typ == "llm/retry":
        errs["llm/retry"] += 1
print("=== 错误计数 ===", dict(errs))
print("=== checkpoint/压缩次数 ===", checkpoints)
```

按需改成两个模式：`text`（只看 USER/TEXT 时间线）与 `all`（含错误/turn 计数）。

## 必提取的五类信号

1. **用户时间线**：所有 `user/message` 要点（需求、纠偏、提供的实验），按时间排序——需求漂移靠它对照。
2. **TEXT 流程**：模型文本里的推进标记（"开始实现 X / 验证通过 / 闭合"）——判断哪段在绕路。
3. **工具错误**：`tool/result isError` 聚成计数，`llm/retry` 单独计数——同错 3 次以上即高打断。
4. **轮结束原因**：`turn/end reason.kind`——error / interrupted = 中断点，标出中断到恢复的空窗时长。
5. **压缩计数**：system-reminder 里的 checkpoint / skill catalog 次数 → 上下文压缩频率（频繁=会话内结论易蒸发）。

## 产出

两样东西进复盘报告：

1. **任务全景表**：`| 会话 | 时段 | 干了什么 | 阻碍 |`
2. **障碍清单**：每条带时间戳/次数证据，供四分类评判。