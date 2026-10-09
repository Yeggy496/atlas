# Third-party components

本项目从空目录编写业务代码，没有复制其他排课项目再改名。参考 Google 官方 CP-SAT 调度文档的建模方法。

| 依赖 | 用途 | 许可证 |
|---|---|---|
| React | 交互界面 | MIT |
| Vite | 开发服务与构建 | MIT |
| TypeScript | 前端类型检查 | Apache-2.0 |
| Tailwind CSS | 样式构建 | MIT |
| Lucide | 界面图标 | ISC |
| FastAPI | 后端 API | MIT |
| Pydantic | 数据与引用验证 | MIT |
| SQLAlchemy | SQLite 持久化 | MIT |
| SQLite | 本机数据库 | Public domain |
| Google OR-Tools | CP-SAT 求解 | Apache-2.0 |
| openpyxl | XLSX 读取 | MIT |
| HTTPX | 服务端模型 API 请求 | BSD-3-Clause |
| Uvicorn | ASGI 服务 | BSD-3-Clause |
| pytest | 后端测试 | MIT |
| Playwright | 浏览器验收（开发工具） | Apache-2.0 |

技能使用：Anthropic frontend-design / webapp-testing、wshobson python-testing-patterns，用于指导设计与验证。没有将整个技能仓库打包为产品依赖。实际版本记录于 pnpm-lock.yaml 和 backend/requirements-lock.txt；各依赖及传递依赖的完整许可条款以安装包内原始许可证为准。
