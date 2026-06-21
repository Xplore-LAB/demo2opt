# 项目文件结构说明

本文档用于统一说明 `demo2opt` 的目录职责、运行产物边界和维护约定。

## 1. 顶层目录

```text
demo2opt/
├─ src/                    # Python 后端核心源码（API、服务、工具）
├─ frontend/               # Vue 前端源码与构建配置
├─ tests/                  # Python 单元/集成测试
├─ e2e/                    # Playwright 端到端测试
├─ config/                 # 业务配置（指标、衍生指标等）
├─ data/                   # 示例与输入数据（xlsx/csv/pdf）
├─ scripts/                # 启动、修复、测试辅助脚本
├─ docs/                   # 项目文档（本文件等）
├─ reports/                # 分析报告输出（运行产物）
├─ logs/                   # 运行日志（运行产物）
├─ task_progress/          # 任务进度快照（运行产物）
└─ start_all.bat           # 一键启动脚本
```

## 2. 后端结构（`src/`）

```text
src/
├─ api/
│  ├─ rest/server.py       # REST API（含 /api/samples）
│  └─ ws/server.py         # WebSocket 分析流程与事件推送
├─ services/               # 业务服务（语义分析、推理、决策、知识检索）
├─ prompts/                # 提示词模板与 LLM 客户端封装
├─ utils/                  # 通用工具（logger、业务函数、报告生成等）
├─ models/                 # 数据模型与协议对象
└─ resets/fonts/           # 报告导出字体资源
```

## 3. 前端结构（`frontend/src/`）

```text
frontend/src/
├─ views/Home.vue                          # 主页面（会话、对话流、工作区）
├─ components/
│  ├─ AnalysisComposerCard.vue             # 数据来源 + 任务输入卡
│  ├─ WorkspaceCollapsedRail.vue           # 右侧折叠窄边条
│  ├─ AnalysisStepGroup.vue                # 步骤分组块
│  └─ ...                                  # 报告与行动卡等组件
├─ composables/
│  ├─ useWorkspaceLayout.ts                # 工作区布局与折叠状态
│  └─ useTimelineSession.js                # 时间线会话数据逻辑
├─ router/
└─ _archive/                               # 历史备份文件（不参与构建）
```

## 4. 运行产物与源码边界

下列目录/文件均视为运行产物，不应参与业务源码维护：

- `reports/`
- `logs/`
- `task_progress/`
- `playwright-report/`
- `test-results/`
- `frontend/dist/`
- `frontend/vite-dev.log`、`frontend/vite-dev.err.log`

## 5. 维护约定

1. 业务代码只放在 `src/`、`frontend/src/`，临时验证文件放 `scripts/` 或 `_archive/`。
2. 手工脚本统一放 `scripts/manual/`，默认不纳入自动化测试。
3. 前端备份文件分层管理：
   - 可编译源码级备份：`frontend/src/_archive/`
   - 根级历史页面/参考文件：`frontend/_archive/`（如 `frontend/_archive/root_legacy/`）
4. 根目录服务日志统一归档到 `logs/legacy/YYYY-MM-DD/`。
5. 新增接口时同步更新：
   - `docs/specs/BACKEND_API_CONTRACT.md`
   - 对应测试（`tests/` 或 `e2e/`）
6. 运行产物不提交到仓库，依赖 `.gitignore` 统一排除。
