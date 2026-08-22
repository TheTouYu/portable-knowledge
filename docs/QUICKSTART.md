# Quickstart: First Project

This walkthrough uses neutral data only. It proves tool configuration, not real-world knowledge.

## 1. Create a disposable project

From the PKC repository root:

### Linux/macOS

```bash
cp -R examples/minimal-project /tmp/pkc-quickstart
cd /tmp/pkc-quickstart
git init
git add .
git commit -m "Initialize neutral PKC project"
```

### Windows PowerShell

```powershell
Copy-Item -Recurse .\examples\minimal-project $env:TEMP\pkc-quickstart
Set-Location $env:TEMP\pkc-quickstart
git init
git add .
git commit -m "Initialize neutral PKC project"
```

If Git requires an identity for this disposable repository, configure a local-only test identity. Do not change a user's global Git configuration without approval.

## 2. Understand the instance

`project-intelligence.json` connects PKC to the project. It declares:

- instance and required PKC version;
- authority registry, actor, store, and knowledge paths;
- principal, executor, workspace, and writer identities;
- Project Memory role files;
- active Context and startup budget.

Read `memory/OPERATING.md`, `memory/CURRENT.md`, and `memory/DECISIONS.md`. In a real project these are the bounded startup memory, not proof of current implementation or external behavior.

## 3. Validate and build the projection

Run with the `pkc` executable installed in `INSTALL.md`:

```bash
pkc capabilities
pkc validate
pkc rebuild
pkc validate
```

Expected counts are one Node, one Topic, and one Claim. `.local/pkc/knowledge.sqlite` is generated and ignored by Git.

## 4. Explore and retrieve

```bash
pkc tree --format text
pkc query "deterministic lookup" --level 1 --format text
pkc query "deterministic lookup" --level 2 --format json
pkc show-claim clm_00000000000000000000000000 --format json
```

Levels:

- L1: route and compact discovery.
- L2: bounded Claim summaries plus configured metadata.
- L3 / `show-claim`: exact boundary, Authority, evidence, conflict, and verification detail.

Start bounded. Escalate only when exact evidence or Authority boundaries are needed.

### Claim identifiers and Authority status filtering

Every retrieval result identifies its Claim by a stable Claim ID (`clm_…`).
`knowledge-search` JSON exposes it explicitly as `claim_id`; the legacy `id`
field remains for compatibility and holds the same value. The identifier is
the same Claim ID used by `show-claim` and by Authority Reference `claim_ids`
links — it is a stable identity, never evidence or a ranking guarantee.

`pkc query` and `pkc knowledge-search` accept the same `--status` values,
computed with the same Claim-level Authority status rule:

- `any` (default): no Authority status filter; the result set and ordering
  stay unchanged.
- `current`: only Claims whose every linked Authority Reference observes the
  committed baseline unchanged.
- `pending_review`: only Claims with at least one linked Authority Reference
  that is not `current`.
- `not_registered`: only Claims with no linked Authority Reference.

```bash
pkc query "deterministic lookup" --level 2 --status current --format json
pkc knowledge-search "bounded question" --status current --format json
```

The status filter runs after permission, lifecycle, and conflict checks and
before pagination/limit, so a narrow filter never hides a Claim that a wider
result would have shown. It can only narrow the Claims the caller is already
authorized to see; it never reveals restricted Claims or their status.

## 5. Use PKC in another project

Do not copy the neutral Claim as project knowledge. Instead:

1. Copy only the structural files you need.
2. Map existing project documents to Memory roles in place; do not create duplicate status/decision bodies.
3. Choose project-owned authority and knowledge paths.
4. Define explicit identities and one Primary Context.
5. Create Node/Topic structure only after project owner approval.
6. Commit the baseline.
7. Use high-level semantic plans for production Claim/Authority changes.

The fact-free files under `domain-packs/` can help propose candidate structure for existing personal-brand or software projects. They do not preload Claims and cannot decide the project's actual facts.

## 6. Read-only operating sequence for an AI model

```text
read project operating/current/decision entries
→ pkc capabilities
→ pkc validate
→ pkc rebuild only if needed
→ pkc tree or progressive-query
→ pkc query at L1/L2
→ show-claim only for exact verification
```

Never read `.local` or SQLite directly. Never report a local miss as proof of global absence.

For writes, continue with [`SEMANTIC-CHANGES.md`](SEMANTIC-CHANGES.md).

## 7. Configure project knowledge experience

Projects may opt into deterministic retrieval/refusal regressions and bounded freshness checks:

```json
{
  "evaluation": {"cases_path": "data/knowledge/evaluation/retrieval-cases.json"},
  "experience": {
    "current_surfaces": ["AGENTS.md", "memory/CURRENT.md"],
    "count_surfaces": ["memory/CURRENT.md"],
    "stale_markers": ["obsolete command text"],
    "upstream_locks": ["data/knowledge/upstream-evidence-lock.json"],
    "proof_boundary": "State exactly which later evidence layers this check does not prove."
  }
}
```

Run the single offline, read-only check:

```bash
pkc knowledge-check --format text
```

When `evaluation.cases_path` is absent, retrieval evaluation is reported as `NOT_CONFIGURED`/skipped while Authority, Memory, tree, and freshness checks still receive their own verdict. An invalid configured evaluation remains a failure.

It never rebuilds, modifies authority, creates a Bundle, or accesses the network. Stable outcomes are `0` pass, `1` project knowledge/regression failure, and `2` unavailable environment/configuration. Authority or upstream changes produce review warnings and never auto-rewrite Claims.

Optional embeddings use only `VECTORENGINE_API_KEY`, `VECTORENGINE_BASE_URL`, and `VECTORENGINE_EMBEDDING_MODEL` from the process environment or ignored project `.env`:

```bash
pkc knowledge-index
pkc knowledge-search "bounded question" --semantic
pkc knowledge-check --semantic
```

The index and model+input-SHA-256 cache live below the configured `.local` projection. Missing keys, index/model/permission changes, timeout, 429, 5xx, or invalid responses produce an explicit lexical fallback during search/check. Index creation itself fails with exit code 2 when the provider is unavailable. JSON output never includes embeddings, cache entries, secrets, or full indexed Claim statements. Similarity is not evidence.

Evaluation fixtures use schema version 1 with `defaults` and `cases`. Each case supplies a query and may assert expected Topic IDs, expected Claim IDs, and forbidden Claim IDs; an omitted assertion dimension is not required. Optional alternate search terms augment rather than replace the query. Both snake_case Core names and the earlier camelCase fixture spelling are accepted; conflicting dual spellings fail with a field- and case-specific schema error.

`knowledge-check`, semantic-plan delta, and staged full preflight use the same normalized deterministic evaluator, including permission, Topic@N/Claim@N, visibility filters, alternate terms, and refusal assertions. Cases may declare explicit delta scope independently from expected results:

```json
{
  "id": "bounded-runtime",
  "query": "runtime selection",
  "expected_claim_ids": ["clm_example"],
  "affected_by": {
    "node_ids": [],
    "topic_ids": ["topic-runtime"],
    "claim_ids": []
  }
}
```

Legacy top-level case scope fields (`node_ids`, `topic_ids`, `claim_ids`) remain accepted. A case without scope metadata runs during delta conservatively because a staged Claim can change global lexical ranking. Explicitly scoped non-intersecting cases are reported as deferred to full preflight rather than silently treated as covered.

## 8. Search other registered projects (read-only)

Create a small local registry that names only the PKC projects which may be
queried. Paths are resolved relative to the registry file; absolute paths are
also accepted for a machine-local registry. The registry is a routing list,
not Authority, and it contains no copied Claims:

```json
{
  "schema_version": 1,
  "projects": [
    {
      "id": "game-project",
      "root": "../game-project",
      "read_permission": "internal",
      "evidence_boundary": "Game-owned PKC knowledge only."
    },
    {
      "id": "compiler-project",
      "root": "../compiler-project",
      "read_permission": "internal",
      "evidence_boundary": "Compiler-owned PKC knowledge only."
    }
  ]
}
```

Search explicitly selected projects:

```bash
pkc federation-search "minimal reproduction" \
  --registry federation.json \
  --project game-project \
  --project compiler-project \
  --format text
```

Results remain grouped by owning project. `read_permission` is fixed by the
registry and cannot be raised on the command line. The command is read-only:
it never rebuilds a missing projection, changes Authority or Memory, creates a
Bundle, or writes another project. An unavailable project is reported as such;
it is not treated as an empty search result. The registry grants routing scope
to this command, not operating-system access control—protect repositories with
normal filesystem and repository permissions.

## 9. Maintain existing knowledge

Use the operation that matches the semantic intent:

- new knowledge: `knowledge-plan add-claim`;
- reusable one-command batch intake of one or more new Claims with their Authority Refs: `knowledge-plan capture --file DRAFT.json` (see `docs/SEMANTIC-CHANGES.md` for the draft contract);
- correct or clarify an existing proposition: `knowledge-plan revise-claim`;
- change an existing Topic's ownership/path while preserving IDs and history: `knowledge-plan move-topic`;
- re-approve an existing Ref against an exactly committed changed source while preserving its identity and links: `knowledge-plan refresh-authority-ref`;
- remove an inapplicable Ref from the active registry while preserving a reasoned, replacement-linked audit event: `knowledge-plan retire-authority-ref`.

These operations may share one plan and one immutable Bundle. Run one delta check after all operations, finalize for full staged preflight, then stop for exact-hash review. Multi-Bundle orchestration (`bundle_migration_plan`, historically the ambiguous `migration_plan`) is non-atomic across phases and is not a substitute for a structure-refactor Bundle.

### 9.1 Authority documents must be committed before `init` (except explicit worktree baseline)

By default, `knowledge-plan add-authority-ref` requires the referenced Authority
document to match the committed baseline exactly, so commit every Authority
document (`authority/…`) *before* running `knowledge-plan init`. A commit made
after `init` invalidates the plan's baseline: every later mutation fails with
`PLAN_STALE_BASELINE`. Recovery, in increasing order of disruption:

1. `knowledge-plan rebase <plan_id> --reason …` — re-anchors an open plan to
   the new HEAD when no plan-referenced Authority path changed across the gap
   (conflicting paths are listed and rejected). Operations and staged writes
   are kept; the plan identity and plan id do not change.
2. `knowledge-plan abandon <plan_id> --reason …` + re-`init` + replay — always
   available, but replays every operation.

For design-intent capture where the design document is not committed yet,
explicitly opt in to the working-tree baseline instead:

```bash
pkc knowledge-plan init --intent "..." --risk low --baseline worktree
pkc knowledge-plan add-claim ... --fact-class documented_contract
pkc knowledge-plan add-authority-ref ... --path authority/design-intent.md ...
```

`--baseline worktree` accepts applied-but-uncommitted maintenance and newly
written working-tree files as Authority for that plan. It is an explicit,
opt-in relaxation of the default committed-baseline gate; the working-tree file
still must exist and its exact bytes become the approved hash. The same option
is available on one-command batch intake: `knowledge-plan capture --file DRAFT.json --baseline worktree`
(or `"baseline_mode": "worktree"` in the draft).

### 9.2 Bundle artifacts and `expected_changed_files`

A Bundle's `expected_changed_files` lists the knowledge files its apply
creates or replaces. The lifecycle artifacts themselves — `bnd_*.json`,
`bnd_*.approval.json`, `bnd_*.applied.json` — are written by finalize,
bundle-approve, and bundle-apply respectively and are listed by
`bundle-inspect` under `lifecycle_files`; they are intentionally not part of
`expected_changed_files` (their filenames embed the Bundle content hash, so
listing them inside the hashed body would be circular). Use `bundle-inspect
<bundle_id>` to see the complete artifact set before approving.
