# Changelog

本项目遵循 MASTER_SPEC §31 的版本号规则 `vMAJOR.MINOR.PATCH`。
每完成一个核心功能，先实际运行，再补测试，最后记录于此。

## v0.1.4 — 全功能巡检与缺陷修复 · 2026-10-11

对后端全部端点与前端全部交互路径做了一轮**穷尽式巡检**（正向 + 边界 + 恶意输入），
发现并修复 1 个真实的 500 缺陷，另修复 1 处版本号漂移。巡检脚本与报告留档于 `audit_evidence/`。

### Fixed

- **导出接口 500（真实缺陷）**：`POST /api/export/xlsx` 在 `result.assignments`
  为字符串等畸形输入时抛 `AttributeError: 'str' object has no attribute 'get'`（原 `exporters.py` 第 42 行）。
  - 修复：`exporters.py` 新增 `_as_slot()`、`_resource_label()` 两个防御式转换器，
    重写 `_rows()` 使其跳过非字典元素、强制槽位为整数、校验天序号范围；
    `main.py` 导出端点异常捕获从 `(ValueError,KeyError,TypeError)` 扩到
    `(ValueError,KeyError,TypeError,AttributeError,IndexError)`。
  - 回归验证：10 组畸形输入现全部返回 200（优雅降级）或 422，**500 归零**。
- **版本号漂移**：`backend/app/main.py` 中 FastAPI 的 `version` 硬编码为 `0.1.0`，
  而 `VERSION` / `package.json` 已是 `0.1.3`，导致 `/openapi.json` 与在线接口文档显示错误版本。
  - 修复：改为启动时读取仓库根 `VERSION` 文件（单一事实来源），并把版本号补进
    `/api/health` 响应，便于确认线上实际构建版本。现三者恒一致。

### Verified

- **后端巡检**：`audit_api.py` 44 次调用 + `audit_deep.py` 22 组对抗性探针。
  除上述导出缺陷外，其余全部为**正确行为**（例如无 `reviewed:true` 时 `/api/solve`
  返回 409 是规范要求的「先确认再求解」闸门；`/api/export/json` 返回 404 是
  因为 JSON 导出由前端本地 Blob 生成，后端只负责 xlsx/pdf）。
- **语义巡检**：`audit_semantics.py` **0 问题**。五场景 `hard_violations` 全为 0；
  三种模式权重向量互不相同；`repair` 使约束数 13→12 并恢复 OPTIMAL；
  `diagnose` 的两条建议各自确实能恢复可行；权重覆写生效、未知/负值被忽略；
  `explain` 与 `solve` 一致；`compare` 自反（changed=0, stability=1.0）。
- **前端巡检**：`audit_ui_v2.cjs` **10/10 通过** —— 初始加载就绪、骨架渲染、
  5/5 场景切换可重解、导出按钮组齐全、**实际点击导出并落盘校验文件魔数**
  （XLSX `PK\x03\x04` 7577B / PDF `%PDF` 2489B）、权重滑块可交互、
  导航路由切换、运行期 0 个未捕获 JS 错误。
- **线上端到端**：对已发布地址验证 17 个端点、5/5 场景模板、solve→diagnose→
  compare→export 全链路，XLSX 含 3 个工作表、PDF 为合法 `%PDF-1.4`。
- **初始加载体验**：实测界面可交互需约 2.9s，但期间有明确可见的加载提示
  （「求解处理中」+ 空态文案），**非静默冻结**，判定为可接受。
- `pytest backend/tests -q`：**84 passed, 1 skipped**。

## v0.1.3 — 技术栈决策归档（`TECH_STACK.md`）· 2026-10-11

关掉最后一个规格差异项：前端技术栈与 §2 推荐项的偏离，改为**显式决策 + 可答辩文档**。
本轮为**纯文档新增**，未改动任何代码，不影响运行与测试结果。

### Added

- `TECH_STACK.md`：
  - §2 推荐项与实际实现的**逐项对照表**（React/Vite/TS/Tailwind/shadcn/FullCalendar/图表）。
  - 澄清关键事实：**TailwindCSS 已实际接入构建链路**（`@tailwindcss/vite` 插件 +
    `styles.css` 首行 `@import "tailwindcss"`），属「已接入未当主力」，而非「未接入」。
  - 逐条说明 shadcn/ui、FullCalendar、图表库**有意未采用**的理由：
    分别为接力开发「不改前棒成果」约束、领域模型适配成本、以及 §26 禁止过度开发。
  - 给出成本评估表与**两段可直接使用的答辩话术**（应对「为何不用 FullCalendar」类提问）。

### Decision

- **保留现有自写 CSS（2593 行）与自写组件（2575 行）**，不做重构。
  依据 MASTER_SPEC §27 第 2 条「不要随意推翻已经工作的模块」，
  以及本项目三棒接力的交接约束。若评审要求对齐，改造路径与风险已在文档中列出。

### Verified

- 文档引用的全部数据经实测核对：组件 2575 行 / CSS 2593 行 / `Calendar.tsx` 209 行 /
  生产 JS 289KB（gzip 89KB）。
- 未改动代码，`pytest backend/tests -q` 结果与 v0.1.2 一致（**84 passed, 1 skipped**）。

## v0.1.2 — 规格功能补齐（API 契约 + 导出）· 2026-10-11

对照 MASTER_SPEC 原文逐条核对后，补齐最后两处功能缺口。全部为**新增**，无既有行为变更。

### Added

- **独立冲突诊断端点 `POST /api/diagnose`**（MASTER_SPEC §14 / §23）
  - 会**先真实求解**再诊断：对可解问题正确返回 `infeasible: false` 且 `conflicts: []`，
    不会像 `diagnose()` 内部函数那样一律假定无解。
  - 每条修复建议仍带 CP-SAT 可行性见证（`verified: true`），非 LLM 猜测。
- **`POST /api/parse-constraints`**（MASTER_SPEC §23 文档化命名）
  - 作为既有 `/api/constraints/parse` 的别名，两者响应完全一致；原路由保持不变。
- **方案导出 XLSX / PDF `POST /api/export/{fmt}`**（MASTER_SPEC §25 P2）
  - XLSX（openpyxl，既有依赖）：三个工作表——`调度明细`（完整中文课表）、
    `每日负载`、`求解概况`（状态/目标值/资源/约束计数）。
  - PDF：纯 stdlib 手写 PDF（A4、分页、xref 表完整），英文摘要版。
    **刻意的取舍**：内置字体无法绘制 CJK，嵌入中文字体需引入 10–20MB 字体或
    reportlab+pillow 新依赖，违反 §26「禁止过度开发」，因此中文完整版走 XLSX。
    UI 按钮 tooltip 已写明「PDF 为英文摘要版，中文请用 Excel」。
  - 导出数据**完全来自前端已展示的求解结果**（请求回传 `problem` + `result`），
    导出器是纯函数，绝不重新求解，与屏幕永不不一致（§27 #6）。
- **前端**：结果面板右上角新增导出按钮组（Excel / PDF / JSON 三态），
  求解前禁用、求解后启用，导出中显示 busy 状态。
- **测试**：`backend/tests/test_api_surface_exports.py`（9 例）——诊断端点语义、
  OpenAPI 契约、XLSX 结构与非标量 metrics 回归、PDF 可被 pypdf 解析、导出器幂等。

### Fixed

- XLSX 导出在 `metrics` 含列表值（每日负载数组）时崩溃：
  `ValueError: Cannot convert [4.5, 4.5, ...] to Excel`。新增 `_cell_value()` 归一化。

### Verified

- 后端：`pytest backend/tests -q` → **84 passed, 1 skipped**（新增 9 例，零回归）。
- 前端：`tsc -b` 退出 0；`vite build` 成功（`index-CyfDce-f.js` / `index-D7n9yArD.css`）。
- 浏览器实测（Edge headless + CDP）：3 个导出按钮渲染正确；求解后启用；
  点击 `/api/export/xlsx` 与 `/api/export/pdf` 均返回 **200** 且 MIME 正确；
  **0 控制台错误、0 失败请求**。
- 端点总数 14 → **17**（新增 diagnose / parse-constraints / export）。

## v0.1.1 — 上线发布版（公网可访问）· 2026-10-11

应用户要求把站点发布为公网链接以供真人测试。本轮改动集中在**部署链路**，业务逻辑未变。

### Added

- `backend/app/webapp/`：前端生产构建的**源码级兜底副本**（`index.html` / JS / CSS / favicon）。
  发布平台会排除 `dist/` 等构建产物目录，导致首次发布后 `/` 与 `/assets/*` 全 404。
  该副本随源码上传，保证服务在只上传后端目录时仍能完整对外提供前端。

### Changed

- `backend/app/main.py` 静态托管改为**双路径回退**：优先仓库布局 `frontend/dist`，
  其次 `backend/app/webapp`，以 `index.html` 是否存在为判据。原 `frontend/dist` 行为不变。
- 发布启动命令改用 `sh -c '... ${PORT:-3000}'` 包裹，修复 `--port $PORT` 未被 shell 插值
  导致的 `Option '--port' requires an argument`。
- 发布依赖安装改用 `backend/requirements.txt`（宽松范围）。`requirements-lock.txt`
  锁定了 `numpy==2.5.3` 等要求 Python ≥3.13 的版本，与发布沙箱的 Python 版本不兼容。

### Fixed

- 首次发布后首页与静态资源全部 404（见上「Added」的根因与解法）。
- 发布时依赖安装失败（`Ignored versions that require a different python version`）。

### Verified

- 线上实测：`/`、`/index-*.js`、`/index-*.css`、`/favicon.svg`、`/api/health`、`/api/weights` 均 200。
- 线上端到端求解：`POST /api/solve`（life 模板，35 活动 / 11 约束）→ **OPTIMAL，35/35 分配**。
- 本地回归：`pytest backend/tests -q` → **75 passed, 1 skipped**，零回归。
- 快照：`snapshots/v0.1.1_20261011T035852Z`，74 文件，SHA-256 校验完整。

## v0.1.0 — 第三棒补完（五维权重 + 快照工具）· 2026-10-11

在上一条第三棒交付的基础上，补齐规格列出的最后两项。所有改动仍为**新增或向后兼容扩展**。

### Added

- **五维权重滑块 + 自定义模式**（MASTER_SPEC §15）
  - `GET /api/weights`：暴露 7 个目标维度（goal/compact/balance/robust/lead/stability/regular）
    及三档预设与 `repair_stability`，前端不硬编码求解器目标名。
  - `SolveRequest.weights`（可选）：在所选预设之上覆盖个别目标权重；未知键、负值、
    非数字一律忽略；全零退化档回退为预设 goal，避免求解器失去目标。
  - `solver/engine.py` 的 `solve()` 新增可选 `overrides` 参数。**未改动 WEIGHTS 结构与建模逻辑**，
    无 overrides 时行为与之前完全一致。
  - 前端新增 `WeightPanel.tsx`：7 条滑块、实时数值、一键恢复预设、按自定义权重重新求解。
  - 修复：切换预设时通过显式传参清空自定义权重，避免 React 异步 state 导致的闭包陈旧问题
    （否则切预设仍会沿用旧的自定义权重）。
- **版本快照工具**（MASTER_SPEC §33 / §35）
  - `tools/snapshot.py`：`--label` 打标签、`--bump major|minor|patch` 递增 VERSION、
    `--with-dist` 含前端构建产物、`--list` 列出、`--verify <name>` SHA-256 校验。
  - 快照写入 `snapshots/<v版本>_<UTC时间>/`，含 `manifest.json` 与 `README.md`；
    自动排除 `.venv`/`node_modules`/`dist`（除非 --with-dist）/`snapshots`/`_scratch*` 等。
  - 纯 stdlib 实现，符合"无 Git 版本纪律"。
- **测试**：`backend/tests/test_weights_snapshot.py`（9 个用例）——自定义权重被采纳、未知/负值被忽略、
  全零兜底、复核门禁不受影响、快照排除规则、bump 版本号运算。

### Changed

- `backend/app/schemas.py`：`SolveRequest` 新增 `weights` 字段（纯新增）。
- `backend/app/main.py`：新增 `/api/weights`；`run()` 透传 `request.weights`。
- 前端 `types.ts` 新增 `WeightDimension` / `WeightsMeta`；`InputPanel` 集成权重面板。
- 前端 `styles/input.css` 新增 `.weight-panel` 系列样式；`.gitignore` 忽略 `snapshots/`、`_scratch*`。
- 前端生产构建产物 `frontend/dist` 已重建。

### Fixed

- 切换优化档位时，自定义权重未被正确清空（React state 更新异步导致 `optimize` 读到旧闭包）。

## v0.1.0 — 第三棒（智能层 · Day 4–5）· 2026-10-11

在保留第一、二棒全部成果的前提下，补齐第三棒的剩余缺口。所有改动均为**新增或向后兼容扩展**。

### Added

- **TXT / PDF 文本导入**（MASTER_SPEC §11）
  - `backend/app/importer.py` 新增 `extract_text()`：
    - TXT 支持 UTF-8 / UTF-8-BOM / GB18030 解码回退；
    - PDF 使用 pypdf 逐页提取纯文本，未安装 pypdf 时返回友好错误而非崩溃；
    - 2 MB 上限、20,000 字上限，与既有 CSV/XLSX 分支完全隔离。
  - `POST /api/import/text`：仅返回提取出的文本，**不直接改写问题**——
    文本交给既有解析管线（`/api/constraints/parse`）由用户复核。
  - 前端 `InputPanel` 新增「TXT / PDF」导入按钮。
- **LLM 解释服务**（MASTER_SPEC §18）
  - `backend/app/llm/explanation_service.py`：以 `solver/explain.py` 的确定性事实为唯一事实源，
    仅在配置真实 Provider 时追加一段 LLM 叙事。
  - `demo` 模式或模型失败时，回退为纯确定性解释，保证 Demo 正确性不依赖模型可用性。
  - `/api/explain` 响应新增 `narrative` / `narrative_source` 字段（向后兼容）。
  - 前端解释弹窗在有叙事时展示，并标注「由 LLM 依据本次求解事实生成」。
- **重规划对比**（MASTER_SPEC §16 / §37）
  - `backend/app/solver/compare.py`：逐活动对比新旧两次方案，输出 moved / kept / added / removed、
    `changed` 数量与 `stability` 比例——即 Minimal-Perturbation 的可量化证据。
  - `POST /api/compare`（只读）。
- **交接与治理文档**
  - 新增 `HANDOFF.md`、`CHANGELOG.md`、`PROJECT_STATE.md`（MASTER_SPEC §30 / §33 / §34）。
- **测试**
  - 新增 `backend/tests/test_third_baton.py`（13 个用例）：
    文本解码与拒绝路径、pypdf 缺失降级、文本导入端点不篡改问题、
    解释服务在 demo / 模型失败 / 模型返回畸形数据下的回退、
    方案对比的一致 / 移动 / 增删分类。

### Changed

- `backend/app/main.py`：`/api/explain` 由直接调用 `explain()` 改为经由解释服务（行为向后兼容）。
- `backend/app/schemas.py`：新增 `CompareRequest`（未修改任何既有模型）。
- 前端 `types.ts`：`Explanation` 增加两个可选展示字段。
- 前端 `styles/dialogs.css`：新增 `.narrative` 样式。
- 前端生产构建产物 `frontend/dist` 已重建（新资源哈希）。

### Fixed

- 无（第三棒未修复前两棒 Bug）。

### Notes

- 未改动：`solver/engine.py` 权重与建模、`solver/validator.py`、`adapters.py` 既有场景、
  `llm/providers.py` Provider 边界、既有 CSV/XLSX 导入分支。
- PDF 导入需额外安装 `pypdf`；已在 `backend/requirements.txt`（`pypdf>=4,<6`）
  与 `backend/requirements-lock.txt`（`pypdf==5.9.0`）中声明。

## v0.1.0 — 第一、二棒（架构与平台化）

- FastAPI + React/Vite 项目骨架；SQLAlchemy/SQLite 求解历史。
- UCR 统一约束表示与三个核心场景 Adapter（life / academic / lab）。
- OR-Tools CP-SAT 求解内核、三档偏好、七项目标、独立校验器。
- 自然语言解析双 Provider（demo 离线 / openai / deepseek）；Constraint Review。
- CSV / XLSX 导入、冲突诊断与 CP-SAT 验证的最小修复候选、纯数据解释。
- 扩展场景 meeting / production；benchmark 对比脚本；Render 部署；前端构建守卫。
