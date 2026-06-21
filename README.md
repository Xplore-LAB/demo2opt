# 空分装置智能运行优化系统（demo2opt）

面向工业空分场景的分析与决策系统，包含：
- Python 后端（REST + WebSocket + 分析服务）
- Vue 3 前端（会话、对话流、实时监控、报告）
- PDF/Markdown 报告导出与测试链路（pytest + Playwright）

## 环境要求

- Python 3.10+
- Node.js 20+
- npm 10+
- Windows/macOS/Linux（当前提供 Windows 一键脚本）

## 目录结构（推荐关注）

```text
demo2opt/
├─ src/                    # 后端核心源码
├─ frontend/               # 前端工程
├─ tests/                  # 后端测试
├─ e2e/                    # 前端端到端测试
├─ config/                 # 指标/规则配置
├─ data/                   # 示例与输入数据
├─ scripts/                # 启动与工具脚本
├─ docs/                   # 项目文档
├─ reports/                # 运行产物：分析报告
├─ logs/                   # 运行产物：日志
└─ task_progress/          # 运行产物：任务快照
```

详细目录职责见：`docs/PROJECT_STRUCTURE.md`。

## 快速启动

### 方式一：一键启动（Windows）

```bat
start_all.bat
```

### 方式二：手动启动

1. 后端

```bash
pip install -r requirements.txt
python scripts/start_web.py
```

2. 前端

```bash
cd frontend
npm install
npm run dev
```

## 配置说明

1. 复制配置模板：

```bash
cp .env.example .env
```

2. 在 `.env` 中填写模型访问参数（如 `LLM_API_KEY`、`DIFY_API_KEY`）。
3. `.env` 已被 `.gitignore` 忽略，不应提交到仓库。

### 知识库检索模式（统一）

- 运行时仅使用 `POST /datasets/{dataset_id}/retrieve`。
- 若 `DIFY_DATASET_ID` 为空，系统会在启动时先调用 `GET /datasets` 自动选择第一个可用知识库，并在本次运行内缓存复用。
- `DIFY_DATASETS_KEYWORD`、`DIFY_DATASETS_TAG_IDS`、`DIFY_DATASETS_PAGE`、`DIFY_DATASETS_LIMIT`、`DIFY_DATASETS_INCLUDE_ALL` 仅用于上述自动发现阶段。
- 闭环验证默认关闭（可插拔）：仅当 `ENABLE_CLOSED_LOOP_VALIDATION=true` 时执行并写入闭环字段。

## 测试与质量

- 后端单元测试：

```bash
pytest
```

- 前端构建验证：

```bash
cd frontend
npm run build
```

- 端到端测试（可选）：

```bash
npm run test:e2e
```

## 常用接口

- REST: `http://127.0.0.1:5000`
- WS: `ws://127.0.0.1:8001`
- 示例文件列表: `GET /api/samples`

## 文档索引

- `docs/PROJECT_STRUCTURE.md`：目录结构与维护约定
- `docs/specs/BACKEND_API_CONTRACT.md`：后端接口协议
- `docs/specs/BACKEND_LOGIC.md`：后端流程说明
- `docs/guides/USER_GUIDE.md`：用户使用说明
- `docs/guides/WEB_README.md`：Web 运行说明
- `docs/handover/PROJECT_HANDOVER_GUIDE.md`：项目交接说明
- `docs/business/PATENT_DISCLOSURE_DRAFT.md`：专利披露草案
- `docs/paper/README.md`：论文工作区（索引）
- `docs/paper/01_paper_outline.md`：论文写作大纲（可投稿版）
- `CONTRIBUTING.md`：贡献流程
- `SECURITY.md`：安全漏洞提报
- `CODE_OF_CONDUCT.md`：社区行为准则

## 论文导向要求（Research-Ready）

本项目除工程可用外，默认按“可投稿研究原型”维护。后续开发需满足以下要求。
论文相关文档统一放在 `docs/paper/`。

### 1) 研究定位与问题定义

- 研究问题：面向空分装置的风险约束优化决策，目标是在异常工况下输出可执行、可解释、可审计的操作建议。
- 任务形式：`状态时序 + 异常候选 + 知识检索 + 推理决策 + 人工门控` 的闭环。
- 约束要求：高风险场景必须经过人工确认节点；知识检索步骤为必经步骤。

### 2) 方法学要求

- 方法主线必须统一为：规则预筛 -> 语义复核 -> 工况总览 -> 知识检索 -> 根因诊断 -> 决策验证。
- 检索增强推理（RAG）要求可解释输出：摘要、候选手段、知识来源、风险提示。
- 论文描述不得仅停留工程实现，必须给出形式化定义（输入、输出、优化目标、约束）。

### 3) 实验与评估要求

- 必做对比基线：
  - 仅规则
  - 仅直连 LLM
  - 规则 + 直连 LLM
  - 规则 + 检索 + 推理（完整方法）
- 必做消融实验：
  - 去知识检索
  - 去语义复核
  - 去人工门控
- 指标至少覆盖四类：
  - 任务效果（异常定位/建议有效性）
  - 安全性（高风险误判率、违规建议率）
  - 时效性（端到端延迟、分步骤耗时）
  - 可解释性（专家一致性/可读性评分）
- 实验结果需报告方差并进行统计显著性检验。

### 4) 可复现与可审计要求

- 所有关键实验必须固定随机种子并记录配置。
- 每次完整运行需保留结构化轨迹：
  - `reports/run_trace_raw_*.json`
  - `reports/run_trace_summary_*.json`
  - `reports/run_trace_timeline_*.md/.csv`
- 关键模块需有独立测试文件（例如 Dify 检索模块测试）。
- 论文图表对应数据必须可从仓库脚本一键重建。

### 5) 论文交付最低门槛（Definition of Done）

- 有一套可命名的方法（而非模块拼接说明）。
- 有完整主实验表 + 消融表 + 鲁棒性实验。
- 有至少 1 个端到端真实案例追踪（输入/中间状态/输出全链路）。
- 有可公开复现实验说明（环境、命令、数据范围、结果校验）。

### 6) 里程碑建议（12 周）

- 第 1-2 周：问题形式化、方法定稿、实验协议冻结。
- 第 3-6 周：实现与基线对齐，完成主实验与消融。
- 第 7-9 周：鲁棒性、安全性、失效案例分析。
- 第 10-12 周：论文撰写、图表统一、复现打包与投稿材料整理。

## 维护约定

- 源码仅放在 `src/` 与 `frontend/src/`。
- 运行产物（`reports/`、`logs/`、`task_progress/`）不参与业务开发。
- 手工脚本统一放在 `scripts/manual/`（如 `scripts/manual/test_api.py`），不纳入默认测试。
- 历史前端备份文件统一放在 `frontend/**/_archive/`（当前根级归档：`frontend/_archive/root_legacy/`）。
- 根目录运行日志统一归档到 `logs/legacy/YYYY-MM-DD/`，避免根目录堆积临时文件。
