> 2026-10-14 更新：当前版本 v0.1.9。功能、验证和接力要点见 [最新发布说明](docs/RELEASE_0.1.9.md)，参赛准备见 [材料建议](docs/COMPETITION_DELIVERY.md)。下文保留接力开发时的历史记录，不应将历史“全部完成/无 Bug/已实测”表述作为当前保证。

# Handoff

Version: v0.1.4
Owner: 第三棒（智能层 · Day 4–5）
Date: 2026-10-11

## 当前可以正常运行的功能

- 三场景真实闭环：LifeGrid 个人周计划 / Academic 智能排课 / LabFlow 实验室调度，
  另附 meeting、production 两个扩展场景。
- 统一约束表示 UCR（`backend/app/schemas.py` 的 `Problem`），五个 Adapter 共用一个 CP-SAT 内核。
- 真实 OR-Tools CP-SAT 求解，三档偏好（efficient / balanced / robust），
  七项目标（goal / compact / balance / robust / lead / stability / regular）。
- 独立后置校验器（`solver/validator.py`）：硬约束违反必须为 0，否则抛错。
- 自然语言约束解析：`demo` 离线规则解析（默认）+ `openai` / `deepseek` 真实 Provider。
- Constraint Review：约束卡片可编辑 / 删除 / 新增，`reviewed` 确认后才允许求解。
- 文件导入：CSV / XLSX（结构化）；**TXT / PDF（第三棒新增，非结构化文本提取）**。
- 冲突诊断（`solver/diagnosis.py`）：每条放宽建议都经 CP-SAT 重求解验证。
- 修复：`/api/repair` 应用选定放宽方案并重求解，强制最小化改动。
- 结果解释（`solver/explain.py`）：纯数据；**第三棒新增 LLM 叙事层（`llm/explanation_service.py`）**。
- **重规划对比（第三棒新增）**：`/api/compare` 逐活动对比两次方案，给出 changed 与 stability。
- **五维权重滑块 + 自定义模式（第三棒新增，规格 §15）**：
  `/api/weights` 暴露 7 个目标维度与三档预设；前端新增「自定义权重」面板，可拖动滑块、
  一键恢复预设、按自定义权重重新求解。
- **版本快照工具（第三棒新增，规格 §33/§35）**：`tools/snapshot.py` 支持创建/列出/校验快照与
  `--bump` 递增版本，快照含 SHA-256 清单，符合"无 Git 版本纪律"。
- 求解历史（SQLite）、benchmark 对比脚本、Render 部署配置、pre-commit 前端构建守卫。

## 本阶段新增（第三棒）

| 文件 | 说明 |
| --- | --- |
| `backend/app/importer.py` | 新增 `extract_text()`：TXT（UTF-8/GB18030）与 PDF（pypdf，缺失时优雅降级）文本提取。**未改动既有 CSV/XLSX 分支** |
| `backend/app/main.py` | 新增 `POST /api/import/text`；`/api/explain` 接入解释服务；新增 `POST /api/compare` |
| `backend/app/llm/explanation_service.py` | 新增。把 `explain.py` 的真实事实交给 LLM 润色；`demo`/失败时回退确定性解释 |
| `backend/app/solver/compare.py` | 新增。方案对比（Minimal-Perturbation 证据），纯数据 |
| `backend/app/schemas.py` | 新增 `CompareRequest`（纯新增，未改既有模型） |
| `backend/tests/test_third_baton.py` | 新增 13 个测试，覆盖文本导入 / 解释边界 / 方案对比 |
| `backend/solver/engine.py` | `solve()` 新增可选 `overrides` 参数（自定义权重）；**未改动 WEIGHTS 结构与建模逻辑** |
| `backend/app/schemas.py` | `SolveRequest` 新增 `weights`（可选） |
| `backend/app/main.py` | 新增 `GET /api/weights`；`run()` 透传自定义权重 |
| `backend/tests/test_weights_snapshot.py` | 新增 9 个测试，覆盖自定义权重契约与快照工具 |
| `tools/snapshot.py` | 新增。版本快照工具（创建/列表/校验/bump） |
| 前端 `WeightPanel.tsx` | 新增。五维（含七项）权重滑块面板 |
| 前端 `InputPanel.tsx` | 新增 TXT / PDF 导入按钮；集成 WeightPanel |
| 前端 `App.tsx` | 新增 `importText()`、解释叙事渲染、自定义权重状态与透传 |
| 前端 `types.ts` | `Explanation` 增加 `narrative` 字段；新增权重元数据类型 |
| 前端 `styles/dialogs.css` / `input.css` | 新增 `.narrative` 与 `.weight-panel` 样式 |

## 尚未完成

- 前端未使用规格指定的 TailwindCSS / shadcn/ui / FullCalendar（使用自写 CSS + 自研日历）。
- 用户测试与真实测评报告未做。
- 前端技术栈偏离规格；答辩时需说明或统一。

## 已知 Bug

- 无已知功能性 Bug。环境层面：本机 pnpm isolated linker 无法创建符号链接，
  构建时需 `--config.node-linker=hoisted`（见下）。

## 前端启动命令

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev            # http://127.0.0.1:5173
```

若 `pnpm install` 报 esbuild postinstall 失败（Windows EBUSY / 无符号链接权限）：

```sh
pnpm install --frozen-lockfile --ignore-scripts --config.node-linker=hoisted
./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build
```

## 后端启动命令

```sh
python -m venv .venv
# 激活后：
pip install -r backend/requirements-lock.txt
pip install "pypdf>=4,<6"        # PDF 导入需要（可选）
python run_demo.py               # 一体化本地运行
python run_demo.py --check       # 仅检查依赖与生产构建
```

## 测试方法

```sh
python -m pytest backend/tests -q
# 真实 LLM 端到端（需要 key）：
ATLAS_LLM_LIVE_TEST=1 python -m pytest backend/tests/test_llm_live.py -q
```

## 推荐下一步

1. ~~决定是否将前端技术栈对齐规格（TailwindCSS / shadcn / FullCalendar），或统一话术。~~
   **已决策**：保留自写 CSS 与自写组件，理由与答辩话术见 `TECH_STACK.md`。
2. 组织 10–20 人用户测试，形成真实测评报告（规格 §38）。
3. 若要发布：`python tools/snapshot.py --bump patch --with-dist` 生成带构建产物的版本快照。

## 治理文档索引

| 文件 | 用途 |
| --- | --- |
| `PROJECT_STATE.md` | 当前状态、各层完成度、规格 P0/P1/P2 核对结论 |
| `CHANGELOG.md` | 按版本记录每次改动 |
| `HANDOFF.md` | 本文件：交接说明、复现命令、稳定模块清单 |
| `TECH_STACK.md` | 前端技术栈选型说明与答辩话术（回应规格 §2 偏离） |

## 禁止随意修改的稳定模块

- `backend/app/schemas.py` 的核心字段语义（Activity / Resource / Constraint / Problem）
- `backend/app/solver/engine.py` 的权重结构与建模逻辑
- `backend/app/adapters.py` 的既有五个场景 fixture
- `backend/app/solver/validator.py` 的独立校验规则
- `backend/app/llm/providers.py` 的 Provider 边界（模型输出仅作数据 + 双重校验）
