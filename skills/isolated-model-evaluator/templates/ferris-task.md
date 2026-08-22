# 任务：复刻一个物理正确的摩天轮

用 model-build-test 的 gms 组件 API（`window.gms.part` 米制世界坐标命令）在浏览器页面建一个**物理正确**的摩天轮（双环 + 轮辐 + 支架 + 横杆 + 绳索 + 座舱，完整受力链、零悬空、零重叠、座舱竖直、吊舱 60° 均布）。

## 知识入口
- 技能 `skills/model-build-test/SKILL.md`：**§8 方法论 API 化建模**（命名组件/link/verify/point/touches + §8.5 工作节奏与调试模式）+ §7 组件语义
- 设计基准 `benchmark/METHODOLOGY.md`「连接点核验清单」一节（受力链结构与尺寸）

## 交付与验收
- 组件脚本写入 `{ROUND}/ferris.js`（每个 part 带 name + link 声明受力链 + 脚本末尾 `gms.verify()` 自检，不 ok 抛错）
- `scripts/run-gms-model.sh {ROUND}/ferris.js /tmp/ferris-eval3` 跑通（summary ok=true）
- `python3 benchmark/connectivity-check.py {ROUND}/items.json` 无 X
- `{ROUND}/REPORT.md`：结构说明 + verify/核验结果（简短）

## 安全边界（文件白名单，只读这些）
可读：本任务文件、技能 `SKILL.md`、`benchmark/METHODOLOGY.md`、`scripts/run-gms-model.sh`、`benchmark/connectivity-check.py`。
**禁止读一切其他文件**（src/、web/、benchmark/ 其余、runs/、**`/tmp/ferris-eval*` 历史产物**——考古=最大时间黑洞，
API 语义以技能 §7/§8 为准）。核验的 items.json **必须来自本次 run-gms-model.sh 输出**（cp 历史=作弊，验收作废）。
允许执行：`scripts/run-gms-model.sh`、`python3 benchmark/connectivity-check.py`。
禁止修改项目源码；只用 8787 页面。
