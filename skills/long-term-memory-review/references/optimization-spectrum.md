# 优化手段全谱（记 ↔ 忆，不限形式）

定位：复盘发现缺口后，"用什么形式落地"**不受限**。按三张清单选手段，每个缺口至少落到
一个"记"介质 + 一个"忆"通道，并当场验证。禁止只写一份报告就算完。

## 忆侧（让模型在需要的时点"想起来"）

| 手段 | 轨迹里的触发信号 | 例子 |
|---|---|---|
| AGENTS.md / CLAUDE.md 检索优先级 | 卡住先考古代码而非查记忆；`query` 不带 `--level 2` | 加"缺信息先查知识树，--level 2，gap 降级 knowledge-search --semantic" |
| 技能路由表 + 触发词 | 有技能但会话没用；harness 没唤起 | 改 description 触发词、任务→技能表补行 |
| PKC 检索配置 | progressive-query 全 coverage gap；词法分系统性低 | 调置信阈值、扩 intent_routes、加语义索引 |
| federation 注册 / 检索 | 跨项目经验重复推导 | 写 `federation.json` + 接 `federation-search` |
| 跨会话恢复 | 新会话不知道做过什么 | memory roles（CURRENT.md）+ `dsh-session-history` 接入 |
| 全局技能共享 | 同技能两个项目是副本、改了不同步 | `.agents/skills` symlink / `install-global` |
| 检索辅助代码 | 模型反复探测键名/结构 | 写自检脚本、扩充 golden-set、retrieval-eval runner |

## 记侧（让结论"沉淀住"，且能被忆回）

| 手段 | 轨迹里的触发信号 | 例子 |
|---|---|---|
| 权威文档 | 规则只在会话里 | 写 `docs/game-engine-knowledge` 章节（带样本/命令/结论/适用范围） |
| 账本 | 需求/目标漂移、未完成项丢失 | open-items 登 OPEN/DONE |
| 技能章节 / references | 方法论散在会话 | 回灌 SKILL.md"阻碍点 / 续作入口" |
| PKC claim | 可复用规则没进树 | knowledge-plan → bundle → hash 审批 |
| 评测集扩充 | golden-set 没覆盖这次学到的 | 补 case + expected_claims |
| 代码工具 / 自检 | 同类 bug 反复犯、无防回归 | 加 `tools/` 断言、CLI 校验门 |
| git 提交 | 成果未提交易丢 | 小步提交、限定路径 |

## 知识树功能升级（PKC 引擎本身，枢纽侧）

当忆/记的瓶颈在 **PKC 能力不足**（而非载体缺内容）时，升级 portable-knowledge 本体：

- 检索能力：federation、语义检索、降级链、`--level` 参数默认值。
- 量化能力：memory-health-report 扩展（跨项目对比、记/忆双侧指标）。
- 录入能力：knowledge-plan 原子性、审批门槛、batch capture。

触发信号：轨迹里"查不到是因为**命令/默认值缺陷**"，而不是"树里没这条规则"。
升级属于 L2+：改 `src/` / `tools/`，带测试（`tests/`），按该项目 AGENTS.md /
SEMANTIC-CHANGES 流程，用户确认后提交。

## 每个缺口的落地下限

1. **落对侧**：忆的失败修忆通道；记的失败补记介质。不要用"加新知识"掩盖"没执行检索"——后者是纪律缺口，不是内容缺口。
2. **记完必忆验证**：用"刚记的关键词"去查，命中了才算记成功；查不回 = 介质或触发词没选对，重记。
3. **跨项目判断**：这条规则是**本项目特有**还是**通用**？通用 → 同步进枢纽（全局技能 / portable-knowledge / federation 注册），不能只留在单项目。