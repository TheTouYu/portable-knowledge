# Worktree 基线 Authority

记录 --baseline worktree 接受未提交设计文档作为 Authority 的契约

<!-- CLAIM:START clm_F8BD630E9C01A78FCBD04D4E34 -->

### worktree baseline 接受未提交工作区文件作为 Authority

在显式使用 --baseline worktree 的知识计划中，add-authority-ref 可以从当前工作区读取未提交或新建文件作为 Authority 源，approved_hash 取该工作区文件精确字节；committed 默认模式仍只接受计划基线中的已提交文件。

#### 适用边界

这只适用于显式选择 --baseline worktree 的计划；不改变默认 committed 模式的未提交/脏文件拒绝，也不意味着 working-tree-only 观察可长期替代已提交 Authority；Bundle 应用后仍应尽快提交源文件，否则后续 knowledge-check 可能报告 stale/invalidated。

<!-- CLAIM:END clm_F8BD630E9C01A78FCBD04D4E34 -->
