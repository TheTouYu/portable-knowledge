---
name: long-term-memory-review
description: 长期记忆机制建设者——复盘大模型在目标项目的历史执行轨迹，围绕"记"（沉淀住）与"忆"（想起来）两个核心环节，执行不限形式的优化（文档/流程/知识树/知识树功能升级/代码/提交），并打通跨项目记忆，让大模型真正拥有长期记忆。当用户说"复盘/审查大模型的长期记忆""跑记忆机制优化循环""给大模型配置长期记忆""看记和忆哪里断了""跨项目记忆 / 长期记忆没生效"时使用。
compatibility: 依赖 Python 3、可用的 PKC（tools/pkc.py 或全局 pkc）、DSH 会话日志（~/.dsh/sessions/）；harness 提供 dsh-session-history / skill-creator 时优先使用。
metadata:
  operator-contract: "0.1"
---

# Long-Term Memory Review（长期记忆机制建设：记与忆）

> **核心使命（North Star）**：你是所有关联项目大模型的长期记忆负责人——让「记」容易沉淀、让「忆」容易想起。本技能是周期性执行入口：每次运行扫最近轨迹 → 研究问题 → 不限形式优化（含知识树本体与提交方案）。一切形式规则（提交门槛、改动边界）都服务于这一个目的，可被授权修改。

复盘大模型历史执行轨迹 → 围绕"记""忆"两个环节 → **执行不限形式的优化**
（文档 / 流程 / 知识树 / 知识树功能升级 / 代码 / 提交）→ 打通跨项目 → 让模型拥有长期记忆。

本技能不是"评测打分"工具：产出必须落到载体、通道、代码或提交里，禁止只交一份报告。

## 核心模型：记 ↔ 忆 双循环

- **记（沉淀住）**：会话/任务里产生的结论、规则、经验 → 选介质 → 写入 → 立刻用"忆"验证能查回。
- **忆（想起来）**：下次在需要的时点 → 触发通道 → 命中 → 复用。

**诊断顺序先忆后记**：先弄清"该想的时候为什么没想起来"，才知道"缺的该记到哪、怎么记才被想起"。
本轮的终极目标不是"这一波任务完成了"，而是"下一波任务能不靠人提醒就想起并使用上次的结论"。

## 跨项目三层记忆（记忆不锁死在单项目）

1. **项目内**：AGENTS.md/CLAUDE.md 检索优先级 + 项目 PKC + 技能 + docs + 账本 + git。
2. **项目间**：`federation.json` + `federation-search`（只读跨项目检索）+ 全局技能共享（`.agents/skills` symlink / `install-global`）。
3. **枢纽**：portable-knowledge（本仓库）——全局技能仓库、federation 注册清单、复盘调度、PKC 引擎升级点。

复盘时始终追问：这条规则是**本项目特有**还是**通用**？通用就上枢纽（全局技能 / federation / portable-knowledge），不能只留在单项目里。

## 分工边界（委托，不重造）

| 能力 | 委托对象 |
|---|---|
| PKC 知识树读写 / 检索 / bundle 入库 | `pkc-project-operator` |
| 历史会话检索 | `dsh-session-history`；无则 `references/session-trace-extraction.md` |
| 记忆量化快照 | `tools/memory-health-report.py` + 目标项目 golden-set / retrieval-eval |
| 技能修改 | `skill-creator`（若 harness 提供） |
| 派独立模型跑检索评估 | `isolated-model-evaluator` |

## 执行流程

### Phase 0 定界

- 目标项目路径、目标任务（多会话）、评判标准（记与忆）。
- **跨项目范围三选一**：只审单项目 / 审并接项目间（federation）/ 审并升级枢纽（portable-knowledge）。

---

## 忆循环——先诊断"想不想得起来"

### Phase 1 忆量化基线

```bash
python3 tools/memory-health-report.py --target <目标项目绝对路径>
```

读 claims 变化、retrieval-eval passed/total、bundles；若目标项目有 golden-set / baseline-report，
记四层指标（L0 维护度 / L1 检索质量与路由 / L2 使用率 / L3 正确率）为本轮前后对比锚点。

### Phase 2 轨迹还原 + 记忆深度分析

- `references/session-trace-extraction.md`：L1 统计层（错误计数、压缩次数、中断点、用户时间线）。
- `references/session-depth-analysis.md`：L2 行为层（卡住第一动作、检索有效性三分、复用链、落盘时点）+ L3 因果层（行为→缺口→会话内检索→代价）。
- **重点标出"忆失败"**：没查 / 查错方式 / 查了但载体缺 / 跨项目没接。

### Phase 3 忆通道判缺陷 + 修复（不限形式）

对照 `references/optimization-spectrum.md` 忆侧清单判缺陷，修通道：

- 触发器缺 → AGENTS.md / 技能路由表 + 触发词。
- 路由缺 → PKC 配置（阈值 / intent_routes / 语义索引）。
- 检索方式错 → 检索优先级里的降级链（`query --level 2` → `knowledge-search --semantic`）。
- 跨项目未接 → `federation.json` 注册 + 接入 `federation-search`。
- 无复用工具 → 写检索辅助代码（自检脚本 / golden-set 扩充 / retrieval-eval runner）。

---

## 记循环——再补"沉不沉得住"

### Phase 4 该记未记盘点

用 `references/memory-carrier-checklist.md` 对照轨迹，找出：

- 会话内已闭合、但没落盘的结论（"收尾时做"=没做）。
- 知识树/文档/技能的真实缺口。
- 需求/目标形态漂移点（无外部账本）。

### Phase 5 记介质选择 + 执行（不限形式）

对照 `references/optimization-spectrum.md` 记侧与"知识树功能升级"清单：

- 权威文档 / 账本 / 技能章节 / PKC claim（hash 审批）/ 评测集 / 代码工具 / git 提交。
- **PKC 能力不足时升级引擎本体**：改 `src/` / `tools/`，带测试，按 AGENTS.md / SEMANTIC-CHANGES 流程。
- 跨项目通用的结论，同步上枢纽（全局技能 / portable-knowledge / federation）。

### Phase 6 记完必忆验证

用"刚记的关键词"实际去查（`query --level 2` / `progressive-query` / `federation-search`），
**命中了才算记成功**；查不回 = 介质或触发词选错，重记。

---

### Phase 7 收尾

- 提交：限定路径 `git add <改的文件>` + `git commit`，先 `git diff --check`，不卷无关未提交内容。
- 若目标会话仍活跃：产出继续提示词（读刚落盘的资料 → 当前阻碍解法 → 纪律 → 收尾清单）。
- 报告：记/忆双侧结论 + 规则反馈检查（不一致 / 证据 / 更新的最小文件 / 未推广的局部经验）。

## 优化手段全谱

见 `references/optimization-spectrum.md`：忆侧 / 记侧 / 知识树功能升级 三张清单 + 每个缺口的落地下限（落对侧、记完必忆验、跨项目判断）。

## 变更授权与风险分级（复盘时发现问题，能不能直接改目标项目）

能改，但按风险分层：

| 级别 | 动作 | 授权 |
|---|---|---|
| L0 只读 | 历史会话分析、PKC 检索、git log/status、读文档 | 随时 |
| L1 文书 | 写复盘报告、更新 docs 权威文档/账本、改技能 SKILL.md（不涉知识树） | 用户明示"优化/修改"后落 + 小步提交 |
| L2 知识树 | 增删 Claim / Authority Ref / bundle apply / 升级 PKC 引擎 | 必须 hash 审批或项目流程；复盘者不得自审自批 |
| L3 生产 | 改目标项目生产代码 / 游戏文件 / 地图数据 / .gil | 一律禁止；只登记 open-items 或写进继续提示词 |
| 提交 | git add/commit | 复盘/优化循环内的小步 L1 提交可自主执行（精确 add 限定路径 + diff --check，不卷无关改动）；push/合并/回退仍须用户确认 |

复盘默认停在 L1 产出建议单；用户说"改"才落地 L1，L2/L3 始终交回用户或项目专业流程。

## 关键纪律（2026-08-22 UI 任务实证提炼）

1. **会话内结论随时蒸发**：27 次 checkpoint 压缩后只剩会话日志兜底——"收尾时落盘"=不落盘。
2. **评判用真实证据**：快照/hash/日志/时间线是唯一铁证，不凭"应该怎样"。
3. **需求必须外部账本**：目标形态变化不写 open-items，压缩后用户只能重提。
4. **基础设施错误不归因任务代码**：API 400 重试是最大空窗来源，正确动作是停止重试 + 记录应对经验。
5. **记完必忆验**：任何"记"的落地，以"能用忆查回"为完成标准。
6. **跨项目判断**：通用规则不上枢纽，等于每个项目重学一遍。

## 效率判据（记/忆双侧）

- **忆侧**：golden-set recall 上升、`progressive-query` 无 gap、检索触发率（卡住点第一动作是检索的占比）上升并 ≥70%、跨会话/跨项目直接复用。
- **记侧**：任务闭环时结论已落盘（非"之后补"）、memory-health-report 基线 diff 与 retrieval-eval 单调向好。
- **判"真提效"口径**：L1 干净 ≠ 有用；要 L2 检索触发率 ≥70% + 低"查错方式" + 高复用（忆好），且 L3 代价最小化 + 缺口逐轮收敛（记好），两者一起看。