# engram × PKC 长期知识记忆结合方案

> 目标：让 DSH 统一大脑（dsh-engram-relay 插件，下称 engram）与本项目便携知识核（Portable Knowledge Core，下称 PKC）互补成一套「经验记忆 + 权威知识」双器官系统。
> 原则：**合并是幻觉，互见才是融合** —— 不搬数据、不改语义，做三条桥 + 一份分层纪律。

## 1. 背景定位

- **engram（风识）**：跨会话**经验记忆**。带情景、第一人称、自动蒸馏（每回合后 LLM 提炼至多 3 条）、软结构（标题+摘要+正文+因果边）、有会话生命周期（session 层会话即清、45 天闲置退役）。每轮请求自动唤醒注入（预算 200 tokens，等待上限 800ms）。
- **PKC**：项目**权威知识**。去情景、可共享、硬治理（Topic / Claim / Evidence / Authority Ref / Bundle 事务）、Git 版本化、写入需人工 exact-hash 审批、显式 CLI 查询（validate → tree → query → show-claim）。
- 一句话：engram 管「我经历过什么、上次怎么做的」，PKC 管「本项目什么是真的、依据在哪」。前者是情景记忆，后者是语义知识库——正好互补，不该互相替代。

## 2. 能力对照表

| 维度 | engram（统一大脑） | PKC（便携知识核） |
|---|---|---|
| 记忆对象 | 经验节点 fact/decision/event/note | Claim + Authority Ref（可验证断言+依据） |
| 结构强度 | 软结构：标题/摘要/正文/因果边 | 硬治理：Topic/Claim/Evidence/Bundle 事务、append-only 事件 |
| 写入方式 | 自动：回合结束后 LLM 蒸馏，2-gram 重叠去重 | 人工：knowledge-plan 契约 + 精确哈希审批 |
| 生命周期 | session 层会话即清；45 天闲置退役 | Git 权威永久 + supersede 生命周期 |
| 读入方式 | 每轮自动唤醒注入（哈希预筛+三通道精排+因果传播） | 显式查询：validate→tree→query→show-claim |
| 检索引擎 | 本地 ONNX bge 嵌入 + 纯算法降级三通道 | 确定性 lexical 检索 + 可选 VECTORENGINE 嵌入层 |
| 可见性 | 三层：global / project(绑目录) / session | 四档：internal / public_redacted / restricted / public |
| 质量闸 | ACT-R 激活衰减 + 灵枢 D_norm 校验 | 仓库契约测试 + 检索评估用例 |
| 失效语义 | 软（退役可复活） | 硬（drift 即 fail-closed） |

## 3. 本机健康基线（结合的前提）

结合之前先认清三个现实（全部本机实测）：

1. **P0 · 灵枢运行集缺失**：engram 依赖的灵枢校准器脚本不在安装包内，自启时每轮空等轮询约 15s，超过 800ms 注入等待上限 → **自动记忆注入实际全部丢失**。修法三选一：补齐灵枢运行集（上游仓库）/ 关闭自启止血 / 修 spawn 子进程退出监控。**此项不修，任何结合都收不到效。**
2. **P1 · engram 库近空**：当前仅 3 条记忆且 global 层为零。「记」侧没跑起来，桥 A 的种子恰好是启动燃料。
3. **P2 · PKC 语义检索降级 lexical**：嵌入是可选层，需环境变量 `VECTORENGINE_API_KEY / VECTORENGINE_BASE_URL / VECTORENGINE_EMBEDDING_MODEL`，缺键时显式回退 lexical（设计内行为，非故障）。本会话已实跑 `validate` + `rebuild`，投影健康。

## 4. 结合点设计：三条桥 + 一份分层纪律

### 桥 A · 权→忆（知识种子，PKC → engram，只读）

把 PKC 知识树的 **topic 级摘要**播种为 engram **project 层**节点（title=主题名，summary=一句 claim 摘要，正文附 PKC 相对路径指针），让 DSH 每轮自动唤醒能命中项目权威知识。

- 生成：`pkc tree --format json` + `pkc query --level 2` 输出 → 脚本转成 engram 写入调用（批量 .mjs）。
- 频控：注入预算只有 200 tokens → 只播 topic 级（约 3 条），claim 细节靠 engram 渐进展开去 PKC 现查。
- 层级：用 **project 层**（session 层会话即清；global 层会跨项目泄漏）。

### 桥 B · 记→证（经验晋升，engram → PKC，半自动+人守门）

engram 中被反复唤醒命中、反复蒸馏的主题（项目级经验）说明它已从「个人经验」沉淀为「项目事实」——此时由人审核后提炼为 PKC Claim，走 knowledge-plan 完整契约（init → add → check → finalize → **人工 exact-hash 审批** → apply）。

- 判据建议：同一主题在 engram 中被唤醒命中多次且跨会话稳定出现，才提名晋升。
- engram 侧晋升后原节点保留，正文追加「已晋升为 Claim」指针，因果边指向新 Claim 节点。

### 桥 C · 查询联邦（忆空则问树，双向互查）

- engram recall 无命中/低置信时 → 回调 `pkc knowledge-search --term` 兜底，把 PKC 命中路径作为 memoryHint 回注（engram 已有跨端联动先例：respond 无命中时的 memoryHint 机制，同型扩展）。
- 反向：PKC 深查询（show-claim / L3）前，可先看 engram project 层有没有相关经验节点作上下文。

### 约定 D · 分层纪律（防双源漂移，最重要）

- **engram 只放经验与指针，不放权威结论**：桥 A 种子只存标题+摘要+PKC 路径，永不缓存 claim 全文——权威唯一源是 PKC，防两处漂移。
- **PKC 只放验证过的知识，不放会话过程**：会话细节属于 engram，不进知识树。
- 权威变更只走 knowledge-plan；engram 任何节点都无权直接改 PKC。
- 权限边界：restricted/public 档内容不进桥 A 种子（global/project 层可见面更宽），只播 internal 档。

## 5. 落地步骤（每步带验证，全部不动知识树语义）

| 步 | 动作 | 验证方式 |
|---|---|---|
| S0 | 修 P0：最小止血 = profile patch 设 `lingshuAutoStart=false`；根治 = 补灵枢运行集 | 新会话 distill 调试日志无 15s 级轮询记录；engram-memory 注入恢复常态（远小于 800ms） |
| S1 | 桥 A 播种：写种子脚本，为 3 个 topic 各生成 1 条 project 层节点 | 新会话提问 topic 名，engram-memory 段命中对应节点 |
| S2 | （可选）配 VECTORENGINE 指向兼容嵌入服务 | `pkc knowledge-search --semantic` 返回 mode 非 lexical、无 fallback warning |
| S3 | 桥 C 探针：engram 无命中场景挂 PKC 兜底查询 | 模拟查询回执含 PKC 命中路径 |
| S4 | 桥 B 试运行：下波任务结束后挑高命中记忆走一次 knowledge-plan 晋升 | bundle-inspect 语义 diff 可读 + 人工 exact-hash 审批记录完整 |

S0–S3 零 knowledge-plan 操作；S4 若执行，本身就走含独立人工审批的完整契约。

## 6. 风险与边界

- **双源漂移**：靠约定 D 指针化规避；若种子必须带数字参数，注明「摘自 PKC 某路径某时点」。
- **注入预算撑爆**：200 tokens 上限，种子宁少勿多；唤醒压力阀在候选过多时只取前几名。
- **权限泄漏**：桥 A 只播 internal 档 + project 层；禁止把 restricted 摘要播进 global。
- **蒸馏变形**：engram 自动蒸馏可能把种子摘要二次加工 → 种子节点在 engram 中标注来源与因果链，蒸馏撞题时按同题刷新处理。
- **回退安全**：三桥全部可独立下线（不播种/不晋升/不兜底即回到纯 engram 或纯 PKC），无耦合锁死。

## 7. 落地实测（2026-09-08）

S0–S3 已在真实环境跑通并留下可复算读数：

- **S0 止血**：关闭灵枢自启后，15s 级唤醒停顿归零（全量唤醒日志中最后一次为 09:06:54Z，此后 0 条）；真实会话唤醒耗时 median 88ms / max 816ms，且唯一一条 ≥800ms 的唤醒结果为 items=0（无内容可丢）——自动注入不再丢。
- **S1 播种**：3 条 topic 级节点以 project 层写入，真实会话请求命中 hybrid-wake:1/2，耗时 78–280ms。
- **S3 兜底**：engram 侧无命中时，PKC knowledge-search 以 lexical 模式返回命中路径，兜底链路可用。
- **冷启动**：服务重启后首条真实唤醒即命中 project 层且耗时 442ms，无 15s 级停顿——S0 止血与可见性修复在冷启动下同样生效。

### 可见性结论（按会话解析工作目录）

按工作目录分层的记忆可见性判定，必须按发起请求的会话解析工作目录，不得使用进程级共享的工作目录字段：进程级单字段在并发会话下由后写者覆盖先写者，导致不同会话互相过滤对方的 project 层记忆；实测同一进程内两个会话在按会话解析后各得各自工作目录，过滤恢复正确。

该规则不覆盖无会话标识的后台请求——此类请求没有独立工作目录，只能按全局层放行；也不证明任何具体记忆节点的内容正确性。

## 8. 跨项目记忆联动实测（2026-09-09）

本节回答「知识树跨项目联动到底有没有发挥价值」，并把结论固化为第四条桥。全部读数为本机实跑，命令可复算。

### 8.1 实测读数

- **PKC 侧常设联邦**：新建常驻登记 `~/.dsh/pkc-federation.json`（4 个已装 PKC 的项目，逐项含 root / read_permission / evidence_boundary）+ 入口脚本 `~/.dsh/bin/pkc-fed`（默认查全部登记项目，可追加项目 id）。实跑 federation-search 命中分布：knowledge 5/8/4/2，authority 4/5/4/2，memory 2/1/4/8，契约 0/2/0/0；返回 `read_only: true`、`cross_project_writes: false`；wrapper 退出码 0。**四个项目里只有 1 个装了自己的 `pkc` CLI，其余 3 个仍被联邦读到**（直读 registry / projection）——能力早已具备，缺的只是登记文件。
- **engram 侧层分布**：升层前 151 节点（session 101 / project 47 / global 3）；本轮把 6 条与具体仓库无关的通用结论写为 global 层副本，另加 1 条跨项目查询入口元记忆 → global 3 → 10，总节点 162。
- **覆盖缺口（关键）**：engram 的 project 桶只覆盖 4 个工作目录，PKC 已装项目是另外 4 个，两者交集仅 1 个。**跨项目记忆目前是「两套账本各记各的」。**

### 8.2 桥 D · 跨项目互见（新增）

- **读侧**：任何项目的会话都能用 `pkc-fed`（或显式 `--registry ~/.dsh/pkc-federation.json`）只读查询其他项目的 knowledge / authority / memory 三类命中；命中按项目分组，权限固定，不可命令行提权。
- **写侧**：跨项目**不能**直接提升。engram 的 `engram_promote` 受可见性准入约束（project 层要求 `projectId === viewer.cwd`），对别的项目的节点一律「无权提升」——跨项目沉淀只有两条路：① 从归属项目的会话内提升；② 在目标项目内写同标题 global 副本（本轮采用 ②）。
- **纪律**：联邦查询结果**不得跨项目合并为新事实**（看得到 ≠ 自动学到）；要升为项目事实，必须回到归属项目走 knowledge-plan + 人工 exact-hash 审批。

### 8.3 待批项：两份安装计划（停在人工审哈希门）

| 实例 | plan_hash（前 16 位） | 预期写入项 | 状态 |
|---|---|---|---|
| 实例 A（建模项目） | `e83d28e023710287` | 15 | 未 apply |
| 实例 B（插件仓库） | `4ea147eb2779e66e` | 15 | 未 apply |

计划为只读生成，目标项目零改动（无 `.local/pkc`、`tools/pkc.py`、`project-intelligence.json`、`knowledge` 痕迹）。**apply 需人工审 plan_hash 后另行发起**，本轮不 apply、不 push。

### 8.4 数据质量发现与修法

151 节点中 11 组同标题、26 条重复（约 17%）。去重门（2-gram 重叠 ≥0.55）没拦住，因为重复多是「同题不同措辞」。建议：① 写入前先 `engram_search` 查同标题；② 高频主题改走 `engram_update` 修订而非新增；③ 把「同题刷新」判据从纯字符重叠升级为「标题规范化 + 语义阈值」双门。

### 8.5 未覆盖维度

- 桥 D 只验证了**只读互见**，未验证跨项目写入闭环（受可见性准入的架构约束，需上游改造或人工跨会话执行）。
- 联邦命中数字是 lexical 模式读数，未启用语义嵌入层。
- 两份安装计划未 apply，「装完是否真能提升该项目大模型的忆」尚无实测。

## 9. 安装执行记录（2026-09-09）

第 8.3 节的两份待批计划已按人工批准执行安装，本节替代 8.3 的状态列。

| 实例 | 计划哈希 | 写入项 | apply 结果 |
|---|---|---|---|
| 实例 B（插件仓库） | `4ea147eb2779e66e6e46c6636096f7813702f8327e134c77c20b695b72325b4c` | 15 文件 + 1 链接 | ok |
| 实例 A（建模项目） | 重建后 `fd344d28f72fbc906894607bd3c1b765454564d4feb6daf7ac90beb2b948af25`（原 `e83d28e0237102879fc7fd65d5dac68e06aef9735587080f835517eb830b5c60` 作废） | 15 文件 + 1 链接 | ok |

- **漂移处置**：实例 A 在计划生成后被并发会话写入 6 行，apply 的 Git 状态门（`skills/pkc-project-operator/scripts/pkc_operator.py:833`）会 fail-closed；按契约重建计划（旧计划文件保留作审计证据）后立即 apply。**这是 fail-closed 设计生效的实证，不是故障。**
- **安装后判据**：两项目的 `tools/pkc.py` 均通过 capabilities / validate / rebuild / validate，runtime 版本 `0.2.0rc5`，lock 指向同一 commit `8a2a083360eeb06c634409a75cab6be9e824de6c`；`.gitignore` 采用追加写入（保留原规则 + `.local/`），既有脏文件零触碰。
- **读数方法论修正（独立审计打回后重测）**：早期闭环探针把 `wrapper_checks_per_project` 写成字面常量（同义反复，非测量），被 fresh 子代理审计 reject；已改用真值探针 `.local/fed/measure_final.mjs`（计数由实跑 rc / 锁文件 / wheel 存在性推导，脚本内不出现结果常量）重测，读数不变：`installed_projects=2`、`wrapper_checks_per_project=2`、`pkc_ahead=2`、`knowledge_diff_lines=0`，并经第二位 fresh 子代理独立复跑复算 pass。
- **权威仓零漂移**：PKC 仓库 `knowledge/` 无 diff、ahead 仍为 2、未 commit、未 push。
- **未覆盖维度**：① 两项目知识树为空（nodes/topics/claims 全 0），first-use 未启动——「装完能不能真提升该项目的忆」尚无实测；② 未跑 adapter 评估用例；③ 安装产物留在目标项目工作树未提交（提交/推送属 L4，需另行批准）。
