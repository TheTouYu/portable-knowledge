---
name: long-term-memory-review
description: 跨项目长期记忆审查与优化循环——从历史会话还原大模型在目标项目多会话任务里的真实轨迹，按"是否具备长期记忆"逐障碍评判，盘点项目记忆载体（技能/知识树 PKC/权威文档/账本/git 提交），跑 memory-health-report 与 golden-set 检索评估量化记忆健康度，产出优化清单并落地，最后给出指导活跃会话（若还在跑）的高效提示词。当用户说"审查/复盘某项目的长期记忆""跑记忆机制优化循环""看看大模型效率有没有被长期记忆优化""memory review/audit/记忆复盘"时使用；也适用于"不定时去知识树项目执行完整流程，确保大模型真正在长期记忆上优化了效率"。
compatibility: 依赖 Python 3、可用的 PKC（tools/pkc.py 或全局 pkc）、DSH 会话日志（~/.dsh/sessions/）；harness 提供 dsh-session-history / skill-creator 时优先使用。
metadata:
  operator-contract: "0.1"
---

# Long-Term Memory Review（长期记忆审查与优化循环）

元技能：定期（用户不定时）去 portable-knowledge（或任一项目）执行，审查**目标项目**里大模型的多会话任务是否靠长期记忆真正提效，并落地优化。本技能只做**定界、调度、评判、报告、落地统筹**，不自己实现 PKC 语义、不自己写会话日志解析器。

每次执行产出 5 件：

1. 记忆健康量化快照（memory-health-report + golden-set / retrieval-eval）
2. 任务轨迹全景（历史会话时间线 + 障碍清单）
3. 障碍排序 + 记忆可解清单 + 当前障碍（审查三问结论）
4. 本轮优化落地（文档 / 技能 / 账本 / 知识树 / git 提交）
5. 指导活跃会话的继续提示词

## 分工边界（先声明，避免重复造轮子）

| 能力 | 委托对象 |
|---|---|
| PKC 知识树读写 / 检索 / bundle 入库 | `pkc-project-operator` |
| 历史会话检索 | `dsh-session-history` 技能；无则用 `references/session-trace-extraction.md` |
| 记忆量化快照 | `tools/memory-health-report.py` + 目标项目 golden-set / retrieval-evaluation |
| 技能修改 | `skill-creator`（若 harness 提供） |
| 派独立模型跑检索评估 | `isolated-model-evaluator` |

## 执行流程（七阶段）

### Phase 0 定界

确认四件事，输出一行声明：

- 目标项目路径（会话日志里的项目目录名 = 路径 `/`→`-`，如 `--home-h-genshin-ts-ui--`）。
- 目标任务：哪波多会话任务（用户会描述，或从项目 git log 最近提交倒推）。
- 评判标准：是否具备长期记忆。
- 时间范围：`~/.dsh/sessions/` 里该项目的会话跨度。

### Phase 1 量化基线（不要跳过——这是"有没有真提效"的硬指标）

```bash
python3 tools/memory-health-report.py --target <目标项目绝对路径>
```

读它输出的：claims 总数/变化、retrieval-eval passed/total、bundles 数、与上次 baseline 的 diff。
若目标项目有 `docs/project-intelligence/golden-set*.json` 或 baseline-report，读取其四层指标
（L0 维护度 / L1 检索质量与路由 / L2 使用率 / L3 正确率），记录为本轮"前后对比"锚点。
关键点：`progressive-query` 是否 coverage gap、`query --level 2` 是否命中，是常见的记忆可达性病灶。

### Phase 2 历史轨迹还原

用 `dsh-session-history` 或 `references/session-trace-extraction.md`，解压该项目的
`~/.dsh/sessions/<项目目录>/<session-id>/session.jsonl.zstd`，提取五类信号：

1. 用户时间线（需求 / 纠偏 / 提供的实验）
2. 模型 TEXT 流程（开始实现 / 验证通过 / 闭合）
3. 工具错误计数（`llm/retry` 单独记）
4. 轮结束原因（error / interrupted 的中断点与空窗时长）
5. checkpoint / 压缩次数（越密，会话内结论越易蒸发）

产出：任务全景表 + 障碍清单（每条带时间戳/次数证据）。

### Phase 3 记忆载体盘点

逐类检查五类载体，用 `references/memory-carrier-checklist.md`：

技能 → 知识树 PKC → 权威文档 → 账本 → git 提交状态。

每类一行结论：`✓/✗ + 缺口一句话 + 证据`。

### Phase 4 逐障碍评判（四分类，核心判据）

对 Phase 2 每个障碍归入一类：

- **A 记忆命中**：跨会话成功检索到旧结论并复用 → 保留该机制。
- **B 记忆缺失**：规则/结论未落盘，导致重新推导或等用户再做实验 → 本轮可落盘解决。
- **C 记忆漂移**：需求/目标在上下文压缩中丢失、无外部账本 → 账本纪律解决。
- **D 记忆无关**：基础设施/工具故障（API 400、`diff` 缺失、技能注册缺）→ 记录应对经验，不算记忆缺陷。

按打断程度排序：中断时长 > 返工轮次 > 重复次数 > 分钟级小坑。

### Phase 5 报告与三问

用 `references/review-report-template.md` 落报告，必须回答三问：

1. 障碍排序（按打断程度）
2. 哪些障碍能被长期记忆完美解决
3. 当前障碍（此刻卡在哪 + 遗留风险）

### Phase 6 落地优化（本轮真正的改动）

按"最高收益优先"落地，不是写报告就完：

- 缺的规则 → 权威文档（最小适用范围，带证据链）→ 回灌技能 → 账本登记 → 知识树 bundle 入库（委托 `pkc-project-operator`，遵守 hash 审批，**不直接手写 registry/SQLite**）。
- 纪律写入：闭合即落盘、需求级事项必须外部账本、基础设施错误应对经验入协作手册。
- 量化验证：优化后重跑 memory-health-report / retrieval-eval，对比 Phase 1 基线；检索评估升级到 PASS 才算闭环。

### Phase 7 收尾

- 提交：限定路径 `git add <改的文件>` + `git commit`，**不把无关未提交内容卷进去**；先 `git diff --check`。
- 若目标会话仍在跑：产出**继续提示词**（见下）。
- 报告"规则反馈检查"：是否发现不一致、证据、更新的最小规则文件、未推广的局部经验。

## 继续提示词模板（给被审查的活跃会话）

```text
继续当前任务前，先读刚落盘的权威资料：
1. <技能路径> → 新章节
2. <文档路径> → 新规则
3. <账本路径> → 本任务 OPEN 项

按以下纪律继续：
一、当前阻碍：<描述> → 用"卡住三问"（先查知识库→请用户 10 秒差分→天然实验），不要猜。
二、每轮闭合即落盘（会话内结论会随 checkpoint 压缩蒸发）。
三、小步提交、限定路径（工作区有无关未提交内容）。
四、基础设施错误（API 400 等）停止重试，等待恢复，不算任务代码问题。
五、收尾清单：<逐项>。
```

## 关键纪律（2026-08-22 UI 任务实证提炼）

1. **会话内结论随时蒸发**：27 次 checkpoint 压缩后，闭合结论只剩会话日志兜底——"收尾时落盘"=不落盘。
2. **评判用真实证据**：快照/hash/日志/时间线是唯一铁证，不凭"应该怎样"下结论。
3. **需求必须外部账本**：目标形态变化（如"导出 GIA"→"直接注入地图"）不写 open-items，压缩后用户只能重提。
4. **基础设施错误不归因任务代码**：API 400 重试 29 次是最大空窗来源，正确动作是停止重试 + 记录应对经验。
5. **改动小步提交**：一次提交一件事，先 `git status`/`git diff --cached --stat` 确认暂存区没有不属于本任务的删除/修改。

## 效率判据（判断"长期记忆有没有真优化效率"）

- **检索可达**：golden-set recall 上升 / `progressive-query` 无 coverage gap / `query --level 2` 命中。
- **跨会话复用**：历史会话检索能直接拿到旧结论并复用，不重新推导、不重新求用户做实验。
- **闭环落盘**：任务结束时知识已进"技能 + 文档 + 知识树"，而非"之后补"。
- **量化对比**：memory-health-report 基线 diff、retrieval-eval passed/total 单调向好。