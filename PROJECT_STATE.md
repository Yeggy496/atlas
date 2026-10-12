> 2026-10-12 复核说明：下文保留接力开发时的历史记录。当前功能、测试结果、部署方式和已知限制请优先阅读 [最新分析报告](docs/REVIEW_2026-10-12.md)。不要将历史“全部完成/无 Bug/已实测”表述作为当前保证。

# Project State

> 本文件由 MASTER_SPEC §34 要求，随每一棒交接更新。
> 最后更新：2026-10-11 · v0.1.4 全功能巡检与缺陷修复

## 当前版本

- **版本号**：`v0.1.4`（见 `VERSION`）
- **交接人**：第三棒（智能层 · Day 4–5）
- **交接基线**：第一棒（架构与最小闭环 · Day 1）/ 第二棒（平台化 · UCR / Adapters / 导入 · Day 2–3）成果**全部保留、未改动**

## 一句话状态

三场景（LifeGrid 个人周计划 / Academic 智能排课 / LabFlow 实验室调度）**已全部可端到端 Demo**；
LLM 只做「理解」，CP-SAT 做「决策」，硬约束违反恒为 0；
第三棒的 TXT/PDF 导入、LLM 解释层、方案对比、五维权重滑块、快照工具与三份治理文档均已落地。

## 各层状态

| 层 | 状态 | 说明 |
| --- | --- | --- |
| 前端 | ✅ 可用 | React 18 + Vite + TypeScript；生产构建通过（`tsc -b` + `vite build` 无错）。日历 / 约束卡片 / 解释弹窗 / 权重滑块 / 对比入口 / 导出按钮组齐全 |
| 后端 | ✅ 可用 | FastAPI；**17 个端点**，覆盖 求解 / 解析 / 诊断 / 修复 / 解释 / 对比 / 导入 / **导出** / 权重元数据 / 历史 |
| 数据库 | ✅ 可用 | SQLAlchemy + SQLite（`atlas.db`），记录求解历史；Render 上使用 `/tmp/atlas.db` |
| 求解器 | ✅ 可用 | Google OR-Tools CP-SAT 真实求解；七项目标 + 三档偏好 + 自定义权重；独立后置校验器 |
| LLM 层 | ✅ 可用（可降级） | `demo` 离线规则为默认；`openai` / `deepseek` 真实 Provider 可选。解释层在无真实 Provider 时回退确定性结果 |
| 导出层 | ✅ 可用 | `POST /api/export/{xlsx,pdf}`；XLSX 含完整中文课表，PDF 为英文摘要版（取舍见 CHANGELOG） |
| 版本管理 | ✅ 可用 | "无 Git 版本纪律"：`tools/snapshot.py` 快照 + SHA-256 清单 + `--bump` 版本递增 |

## 三场景完成度

| 场景 | Adapter | 完成度 | 备注 |
| --- | --- | --- | --- |
| LifeGrid（个人周计划） | `life` | ~95% | 六类活动、作息约束、偏好窗口、最小改动重规划均可用 |
| Academic（单班排课） | `academic` | ~90% | 教师 / 教室 / 时段硬约束、连堂、每日上限可用 |
| LabFlow（实验室调度） | `lab` | ~90% | 多资源并行占用、设备可用窗口、先后依赖可用 |
| meeting / production（扩展） | `meeting` / `production` | ~70% | 作为平台通用性的佐证场景，非答辩主线 |

> 完成度按「规格要求的功能项已实现且经测试」估算，非行数占比。

## 第三棒新增（本次交接）

- `POST /api/import/text` + `importer.extract_text()`：TXT（UTF-8/GB18030）与 PDF（pypdf）文本提取，**只提取不解释**，交给既有解析管线复核。
- `llm/explanation_service.py` + `/api/explain` 改造：确定性事实为唯一事实源，LLM 仅追加叙事，`demo`/失败自动回退。
- `solver/compare.py` + `POST /api/compare`：逐活动方案对比，输出 `changed` 与 `stability`（Minimal-Perturbation 的可量化证据）。
- `HANDOFF.md` / `CHANGELOG.md` / `PROJECT_STATE.md` 三份治理文档。
- `backend/tests/test_third_baton.py`：13 个新用例。

## 测试状态

```
python -m pytest backend/tests -q
→ 66 passed, 1 skipped（skip 为需真实 key 的 live 用例）
```

前端：

```
cd frontend && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build   # 均通过
```

## 部署状态

- `render.yaml` 为**模板**，未实际创建云服务；`README.md` 中的 live demo 地址由第一/二棒保留。
- 依赖声明：`backend/requirements.txt` 与 `backend/requirements-lock.txt` 均已声明 `pypdf`。
- 生产前端产物已提交于 `frontend/dist`，由 FastAPI 直接托管。

## 关键问题 / 风险

| 级别 | 问题 | 影响 | 处理 |
| --- | --- | --- | --- |
| 中 | 前端技术栈与规格不一致（自写 CSS 替代 TailwindCSS / shadcn/ui / FullCalendar） | 答辩需说明 | 未改，留待决策 |
| 低 | PDF 依赖 pypdf 需在部署环境安装 | 缺依赖时 PDF 导入返回友好错误 | 已声明依赖 + 代码优雅降级 |

> 五维权重滑块 + 自定义模式（§15）与 `tools/snapshot.py`（§35）**已完成**，见「第三棒补完」。

## 未改动（禁止随意修改的稳定模块）

- `schemas.py` 核心字段语义（Activity / Resource / Constraint / Problem）
- `solver/engine.py` 权重结构与建模逻辑
- `adapters.py` 既有五个场景 fixture
- `solver/validator.py` 独立校验规则
- `llm/providers.py` Provider 边界
- 既有 CSV / XLSX 导入分支

## 下一步（按优先级）

1. ~~前端技术栈与规格对齐的决策（或统一答辩话术）。~~
   **已决策（v0.1.3）**：走「保留自写 CSS + 补齐技术选型说明」，详见 `TECH_STACK.md`。
   Tailwind 已接入构建链路但未作主力；shadcn/ui 与 FullCalendar 有意未采用，
   理由与可念的答辩话术已写入该文档。
2. 组织 10–20 人用户测试，产出真实测评报告（规格 §38）。**线上链接已就绪，待真人反馈。**
3. ~~发布前用 `python tools/snapshot.py --bump patch --with-dist` 生成版本快照。~~
   **已完成** → 见快照列表。

## v0.1.3 技术栈决策归档（本轮追加）

- 新增 `TECH_STACK.md`：规格 §2 前端推荐项与实际实现的**逐项对照表**、
  每处差异的选型理由、成本评估、以及两段可直接使用的**答辩话术**。
- 决策：**保留现有自写 CSS 与自写组件**，不重构。
  依据为 §27 第 2 条「不要随意推翻已经工作的模块」+ 接力开发「不改前棒成果」约束。
- 该文档为**纯新增**，未改动任何代码。

## v0.1.2 规格功能补齐（本轮追加）

对照 MASTER_SPEC 原文逐条核对后，补齐最后两处缺口（均为新增，无既有行为变更）：

- **`POST /api/diagnose`**（§14/§23）：独立冲突诊断。会**先求解再诊断**，对可解问题
  正确返回 `infeasible: false`；修复建议带 CP-SAT 见证。
- **`POST /api/parse-constraints`**（§23）：既有 `/api/constraints/parse` 的文档化别名。
- **`POST /api/export/{xlsx,pdf}`**（§25 P2）：XLSX 含完整中文课表（3 工作表）；
  PDF 为纯 stdlib 英文摘要（不入 CJK 字体，理由见 CHANGELOG）。
- 前端结果面板新增 Excel / PDF / JSON 导出按钮组。
- 测试：`test_api_surface_exports.py`（9 例）→ 全套 **84 passed, 1 skipped**。
- 浏览器实测（Edge headless + CDP）：导出按钮渲染/启用/点击全流程正确，
  两个导出端点均 200，0 控制台错误。

### 规格核对结论（P0 / P1 / P2）

| 优先级 | 项目 | 状态 |
| --- | --- | --- |
| P0 | React 界面 / FastAPI / CP-SAT / 三场景 / NL 输入 / Review / 日历 / 冲突检测 / CSV+XLSX / 可部署 | ✅ 全部完成 |
| P1 | 五维目标 / 三档模式 / Repair / 重优化 / 稳定性 / 结果解释 / PDF 导入 / 资源利用率可视化 | ✅ 全部完成 |
| P2 | 导出 Excel / 导出 PDF / 更多场景 / 登录 / 多用户 | ✅ 导出完成；更多场景已有 meeting+production；登录与多用户**按 §26 明确不做** |

## v0.1.1 上线发布（本轮追加）

- **公网发布**：站点已作为单端口 HTTP 服务发布，可直接访问测试。
- **部署链路三处修正**（业务逻辑未变）：
  1. 依赖安装改用 `backend/requirements.txt`（`requirements-lock.txt` 锁定的 numpy 等版本
     要求 Python ≥3.13，与发布沙箱不兼容）。
  2. 启动命令用 `sh -c '... ${PORT:-3000}'` 包裹，修复 `$PORT` 未插值。
  3. 新增 `backend/app/webapp/` 前端构建兜底副本 + `main.py` 双路径静态托管回退，
     修复发布平台排除 `dist/` 导致的首页 404。
- 线上验证：静态资源与 API 全 200；life 模板 35 活动求解 **OPTIMAL 35/35**；本地回归 75 passed。

## 第三棒补完（本轮追加）

- **五维权重滑块 + 自定义模式**（规格 §15）：`GET /api/weights` + `SolveRequest.weights` +
  前端 `WeightPanel.tsx`（7 条滑块 / 恢复预设 / 自定义重求解）。
- **`tools/snapshot.py`**（规格 §33/§35）：创建 / 列表 / SHA-256 校验 / `--bump` 版本递增。
- 两个 bug 已修：预设切换时自定义权重未清空的闭包陈旧问题；快照工具误纳入 `_scratch*` 临时目录。
- 测试：新增 `backend/tests/test_weights_snapshot.py`（9 例）；全套 **75 passed, 1 skipped**。
