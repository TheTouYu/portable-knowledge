# Capture DRAFT 格式契约（knowledge-plan capture --file）

> 受众：需要在目标项目里用 `knowledge-plan capture --file DRAFT.json` 批量录入 Claim + Authority Ref 的操作者。
> 只读本文件 + `capture --help` 就应能写出可被 `--preview-only` 接受的草稿，无需翻源码。
> 运行时：portable_knowledge ≥ 0.2.0rc5。语义等价的本体文档：portable-knowledge 仓库 `docs/SEMANTIC-CHANGES.md`「File-driven batch capture」节。

## 0. 一句话契约

`capture --file <草稿>` 把一次「有界语义变更」描述成一个 JSON（或 Markdown）草稿，内部自动执行与交互式完全相同的类型化流水线：

```text
init → 每条 claim 一次 add-claim → 每条 authority ref 一次 add-authority-ref
     → 一次 delta check → 一次 finalize（--preview-only 时跳过 finalize，plan 保持 open）
```

它只会产出待人工精确 hash 审阅的不可变 Bundle（或 preview），**绝不 approve / apply / commit**，也不走 `bundle-create --manifest` 或兼容模式。

## 1. 顶层字段（schema_version 必须为 1）

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `schema_version` | 是 | 整数 `1` | 其他值直接报 `PLAN_DRAFT_INVALID` |
| `intent` | 是 | 非空字符串 | 本次有界语义变更的一句话描述；同名 intent 重跑会重放同一 Bundle |
| `risk` | 是 | `low` \| `medium` \| `high` | 语义风险档 |
| `baseline_mode` | 否 | `committed`（默认）\| `worktree` | 引用未提交设计文档时用 `worktree`；CLI `--baseline` 可覆盖草稿值 |
| `claims` | 是 | 非空数组 | 见 §2；多 claim 顺序执行，顺序无关 |

未知顶层字段会被拒绝（`unknown draft field`），拼写错误不会静默通过。

## 2. claims[]：每条一个 Claim

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `id` | 否 | 非空字符串，草稿内唯一 | 本地别名，供 `authority_refs[].claim_id` 引用；缺省时 ref 绑定其所在 claim |
| `node` | 是 | 节点 id | claim 归属节点 |
| `node_name` / `node_path` / `node_boundary` / `node_keywords` | 仅新建节点时 | 字符串 / 字符串 / 字符串 / 字符串数组 | **仅当原子创建新节点时有效**；节点已存在再传会报「node metadata is only valid when atomically creating a new node」 |
| `topic_id` | 是 | 字符串 | claim 归属 topic |
| `topic_path` | 新建 topic 时必填 | Markdown 路径（须位于 node 路径下） | 已有 topic 时可省（会自动取注册值） |
| `topic_title` / `topic_summary` / `topic_keywords` | 仅新建 topic 时 | 字符串 / 字符串 / 字符串数组 | **topic 元数据仅创建时有效**：同 topic 的第 2 条起不再接受元数据（交互式报 `PLAN_TOPIC_INVALID`；capture 批处理对「与首条完全一致」的重复元数据幂等忽略，不一致才报错） |
| `title` / `statement` / `boundary` | 是 | 非空字符串 | Claim 三段：标题 / 断言 / 边界 |
| `permission` | 否 | `restricted` \| `internal`（默认）\| `public_redacted` \| `public` | 必须等于其 topic 现有 permission |
| `duplicate_resolution` | 否 | `cancel`（默认）\| `create_distinct_with_boundary` | **新建 topic 时必须为 `create_distinct_with_boundary`** |
| `fact_classes` | 是 | 非空数组，取值见 §4 | 声明本 claim 需要哪些事实类覆盖 |
| `authority_refs` | 否 | 数组，见 §3 | 本 claim 的 Authority 覆盖 |

## 3. claims[].authority_refs[]：每条一个 Authority Ref

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `claim_id` | 否 | 草稿内某 claim 的 `id` | 目标 claim；缺省绑定所在 claim；引用未知 id 是草稿错误 |
| `path` | 是 | 项目内已提交文档路径 | Authority 源文件；必须已在 git 基线（除非 baseline_mode=worktree） |
| `locator` | 是 | 非空字符串 | 文档内的节/段落定位 |
| `role` | 是 | 见 §4 ROLES | Authority 角色 |
| `change_policy` | 是 | 见 §4 POLICIES | 源变化时的处理策略 |
| `fact_classes` | 是 | 非空数组 | **必须是目标 claim 已声明的 fact_classes 子集**，否则草稿错误 |
| `diagnostic_hash` | 否 | 字符串 | 可选诊断指纹 |

## 4. 受控词表（与交互式 CLI 完全一致）

- `role`（Authority 角色）：`design_intent` \| `current_implementation` \| `documented_contract` \| `external_environment_behavior`
- `change_policy`：`existence_only` \| `review_on_change` \| `invalidate_on_change` \| `manual_review`
  - **政策语义陷阱（2026-08-29 实踩）**：`manual_review` 的 ref **永远处于 non-current（manual_review）状态**——任何触及该 ref 关联 claim 的 plan 在 finalize 时会被 `PLAN_FULL_AUTHORITY_NOT_CURRENT (plan_affected)` 阻塞，等于**无法为绑定该 ref 的 claim 完成录入**。引用「本轮刚提交的文档」用 `review_on_change`（或 `invalidate_on_change`），`manual_review` 只用于允许其长期停留待审的易变源。
- `fact_classes`：`runtime_behavior` \| `public_type_surface` \| `cli_behavior` \| `documented_contract` \| `external_game_evidence` \| `transform_defaults` \| `writeback_behavior` \| `evidence_scope`
- `permission`：`restricted` \| `internal` \| `public_redacted` \| `public`
- `risk`：`low` \| `medium` \| `high`
- `duplicate_resolution`：`cancel` \| `create_distinct_with_boundary`
- `baseline_mode`：`committed` \| `worktree`

## 5. 最小示例（JSON）

```json
{
  "schema_version": 1,
  "intent": "Add two schema-contract claims",
  "risk": "medium",
  "claims": [
    {
      "id": "c1",
      "node": "software-core",
      "topic_id": "topic-schema",
      "title": "Schema input is explicit",
      "statement": "The schema parser accepts explicit versioned fields.",
      "boundary": "Only the committed neutral fixture is in scope.",
      "fact_classes": ["documented_contract"],
      "authority_refs": [
        {
          "claim_id": "c1",
          "path": "authority/schema-contract.md",
          "locator": "schema contract",
          "role": "documented_contract",
          "change_policy": "invalidate_on_change",
          "fact_classes": ["documented_contract"]
        }
      ]
    },
    {
      "node": "software-core",
      "topic_id": "topic-schema",
      "title": "Schema parsing fails closed",
      "statement": "Invalid schema versions are rejected before any mutation.",
      "boundary": "Applies to the committed fixture only.",
      "fact_classes": ["documented_contract", "cli_behavior"]
    }
  ]
}
```

要点：

- **多 claim 多 ref**：`claims` 数组长度不限；每个 claim 内嵌 `authority_refs` 数组长度不限；跨 claim 引用用 `claim_id` 别名。
- **已有 topic 追加 claim**：只给 `node` + `topic_id`（+ `topic_path` 可省），**不要再带 `topic_title/topic_summary/topic_keywords`**。
- **新建 topic 首条 claim**：带上 `topic_path` + 全部 topic 元数据，且 `duplicate_resolution` 必须是 `create_distinct_with_boundary`。

## 6. Markdown 变体（--draft-format markdown；.md 自动识别）

```markdown
- intent: Add one schema-contract claim
- risk: medium

## Schema input is explicit

- node: software-core
- topic_id: topic-schema
- title: Schema input is explicit
- statement: The schema parser accepts explicit versioned fields.
- boundary: Only the committed neutral fixture is in scope.
- fact_class: documented_contract

### authority_ref

- path: authority/schema-contract.md
- locator: schema contract
- role: documented_contract
- change_policy: invalidate_on_change
- fact_class: documented_contract
```

规则：第一个 `##` 之前的 `- key: value` 行是草稿级 `intent`/`risk`；每个 `##` 标题开一条 claim（标题即 claim title）；`### authority_ref` 开该 claim 的一条 ref。列表字段（`node_keywords`/`topic_keywords`/`fact_classes`/`aliases`/`keywords`）可重复写或逗号分隔；单数别名（`fact_class`→`fact_classes`、`keyword`→`keywords` 等）自动归一。Markdown 先归一成 JSON 草稿再走同一套校验，报错字段名与 JSON 完全一致。

## 7. 预览与错误定位

```bash
python tools/pkc.py knowledge-plan capture --file DRAFT.json --preview-only
```

- `--preview-only` 跑完整流水线但跳过 finalize：输出候选 Bundle 的 `semantic_diff` + `content_hash`，plan 保持 open（可继续 `finalize` 或 `abandon`）。
- 草稿错误报 `PLAN_DRAFT_INVALID` 并带精确字段名（如 `claims[2].authority_refs[0].role`）；流程中段失败会报 `PLAN_DELTA_FAILED` 并把 finding 关联回草稿字段（`draft_field`），同时 abandon 半成品 plan（`retained_plan` 说明原因），绝不留部分 Bundle。
- 同一草稿成功后再跑一次 = 重放同一不可变 Bundle（相同 intent）。
