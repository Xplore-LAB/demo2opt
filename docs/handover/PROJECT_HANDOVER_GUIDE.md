# 项目接手指南：工业空分装置智能优化系统

**版本**: 1.0  
**作者**: 资深系统架构师  
**日期**: 2026-02-26

---

## 1. 核心技术栈 (Core Tech Stack)

本项目采用 **Python 3.12** 作为核心语言，构建了一套结合传统工控逻辑与现代 LLM 推理的混合系统。

| 维度 | 技术选型 | 关键说明 |
| :--- | :--- | :--- |
| **Web 框架** | **Flask** (REST API) + **Websockets** (Real-time) | 双通道架构：API 用于任务管理，WS 用于实时日志流。 |
| **数据处理** | **Pandas** + **NumPy** | 必须使用向量化操作处理时间序列数据，严禁低效循环。 |
| **大模型集成** | **Dify API** + **LangChain** | Dify 封装了 Prompt 和 RAG 逻辑，LangChain 用于本地编排。 |
| **向量检索** | **FAISS** | 本地轻量级向量库，用于存储和检索专家知识库。 |
| **文档解析** | **MinerU (Magic-PDF)** / PyMuPDF | 用于解析非结构化 PDF 技术文档（MinerU 为首选，PyMuPDF 为兜底）。 |
| **数据校验** | **Pydantic** | 用于定义 `SemanticDataModel`, `ReasoningResultModel` 等强类型 Schema。 |
| **配置管理** | YAML + `python-dotenv` | 敏感信息（API Keys）通过环境变量管理，业务参数通过 YAML 配置。 |

---

## 2. 架构与分层 (Architecture & Layering)

项目遵循 **领域驱动设计 (DDD)** 思想，将业务逻辑严格分层，各模块职责边界清晰。

### 目录结构说明

*   **`src/services/` (核心业务层)**
    *   [asu_pipeline.py](src/services/asu_pipeline.py): **数据接入层**。负责 Excel/CSV 读取、清洗、元数据映射及物理公式衍生指标计算。
    *   [data_semantics.py](src/services/data_semantics.py): **语义分析层**。将冷冰冰的数值转化为业务语义（如“严重偏低”），计算模糊隶属度。
    *   [reasoning_engine_v2.py](src/services/reasoning_engine_v2.py): **推理层**。负责组装 Context，调用 Dify API 进行根因分析。
    *   [decision_service.py](src/services/decision_service.py): **决策层**。基于推理结果生成操作建议，并进行（目前的 Mock）仿真验证。
    *   [knowledge_base.py](src/services/knowledge_base.py): **知识层**。管理 RAG 索引，处理文档解析与向量化。
    *   [task_manager.py](src/services/task_manager.py): **任务状态管理**。追踪异步任务进度。

*   **`src/schemas.py` (领域模型)**
    *   定义了所有跨层传输的数据结构（DTO），确保类型安全。

*   **`web_server.py` & `api_server.py` (接口层)**
    *   `web_server.py`: 提供 WebSocket 服务，用于前端实时展示“思考过程”。
    *   `api_server.py`: 提供 REST API，目前仅用于任务查询。

*   **`src/report_generator.py` (基础设施)**
    *   基于 ReportLab 和模版引擎生成 PDF/Markdown 交付报告。

---

## 3. 核心业务流 (Core Business Flow)

目前系统已打通的端到端主链路如下：

1.  **数据摄入**: 用户上传/读取传感器数据 -> `ASUExcelReader` 解析 -> `DerivedMetricsEngine` 计算衍生指标（如冷损）。
2.  **语义转化**: 数值与设计规范 (`metric_design_values.yaml`) 对比 -> `DataSemanticsService` 识别异常（Anomaly Detection）。
3.  **AI 根因分析**: 提取异常特征 + 检索知识库 -> `ReasoningEngineV2` 组装 Prompt -> Dify API 推理 -> 输出根因与初步建议。
4.  **决策仿真与验证**: `DecisionService` 接收建议 -> **[待完善]** 仿真模型预测效果 -> 生成风险评估 -> 输出最终决策。
5.  **交付与反馈**: `ReportGenerator` 生成报告 -> **[断点]** `write_back_case` 闭环学习。

---

## 4. 半完工状态评估 (Status Assessment)

### ✅ 已完成模块
*   **数据管道**: 完整的 Excel 解析与衍生指标计算逻辑。
*   **语义服务**: 基于统计学和规则的异常检测已跑通。
*   **报告生成**: PDF/Markdown 报告生成器功能完整，支持中文字体兜底。
*   **Web 骨架**: WebSocket 实时流框架已就绪。

### 🚧 关键断点与 TODO
1.  **决策仿真虚假 (Critical)**
    *   位置: [decision_service.py](src/services/decision_service.py) -> `_mock_simulation`
    *   问题: 当前返回硬编码的字符串（"预计提升 0.5%"），完全没有依据。
    *   **需求**: 需要引入基于物理公式或历史数据的回归模型。

2.  **知识闭环缺失**
    *   位置: [decision_service.py](src/services/decision_service.py) -> `write_back_case`
    *   问题: 函数体为 `pass`。
    *   **需求**: 系统无法将成功的优化案例沉淀回知识库，缺乏“自进化”能力。

3.  **API 能力受限**
    *   位置: [api_server.py](api_server.py)
    *   问题: 仅有任务查询接口，无法通过 REST API 触发新的分析任务。

4.  **外部依赖脆弱**
    *   位置: [knowledge_base.py](src/services/knowledge_base.py)
    *   问题: 强依赖 `magic-pdf` (MinerU) 命令行工具，且错误处理较为基础。

---

## 5. 潜在风险与改进建议 (Risks & Recommendations)

1.  **风险：Dify API 强依赖**
    *   **描述**: 如果外网不通或 Dify 服务宕机，核心推理功能将直接瘫痪。
    *   **建议**: 增加 Local LLM (如 Ollama) 适配层作为 Fallback 方案。

2.  **隐患：配置加载安全性**
    *   **描述**: `src/config.py` 对 YAML 的加载缺乏 Schema 校验。
    *   **建议**: 使用 Pydantic 对配置文件进行 Strict Loading，防止配置错误导致运行时 Crash。

3.  **设计：缺乏持久化存储**
    *   **描述**: 分析历史仅以文件形式（Report）存在，无法进行历史趋势分析。
    *   **建议**: 引入 SQLite 或 PostgreSQL，存储每次分析的 Input/Output 结构化数据。

---

## 6. 下一步行动建议 (Next Steps)

为了让项目达到 **Alpha 可交付状态**，建议优先完成以下三个任务（按优先级排序）：

### 任务一：重构决策仿真模型 (Refactor Simulation)
*   **目标**: 移除 `_mock_simulation` 中的硬编码。
*   **行动**: 在 `DecisionService` 中实现一个基础的计算引擎，根据调整参数（如“液氮回流”）的幅度，基于简单的物理公式（或线性回归系数）计算对 KPIs（如“纯度”、“能耗”）的理论影响值。

### 任务二：打通 API 触发链路 (Enable API Trigger)
*   **目标**: 使外部系统能集成此服务。
*   **行动**: 在 `api_server.py` 中新增 `POST /api/analysis/start` 接口，异步调用 `AirSeparationOptimizer.run_analysis`，并返回 `task_id` 供查询。

### 任务三：实现知识闭环 (Implement Knowledge Loop)
*   **目标**: 让系统越用越聪明。
*   **行动**: 实现 `write_back_case` 方法。将验证通过的案例（故障现象+解决措施+效果）格式化为 Markdown，写入 `knowledge_docs/cases/` 目录，并调用 `KnowledgeBaseManager` 触发增量索引更新。
