# 完整工作流程分析报告

## 一、系统工作流程概述

基于对 [`scripts/run_interactive.py`](scripts/run_interactive.py:1) 的分析，系统采用**8步标准化分析流程**：

### 标准工作流程

```
步骤1: 数据加载与范围确认
  ↓
步骤2: 最新时刻快照提取
  ↓
步骤3: 规则预筛与语义复核
  ↓
步骤4: 工况总览判断
  ↓
步骤5: 时序特征提取与候选复核
  ↓
步骤6: 知识检索与候选措施整理 (Dify API)
  ↓
步骤7: AI 根因诊断 (LLM 推理)
  ↓
步骤8: 决策验证与报告生成
```

## 二、关键流程节点分析

### 2.1 数据加载阶段（步骤1-2）

**输入**：Excel 文件（如 `data/【原始数据】运行诊断.xlsx`）

**处理流程**：
1. 使用 `ExcelDataLoader` 或 `ASUDataLoader` 读取数据
2. 执行质量门禁检查（`quality_gate`）
3. 提取最新时刻快照

**质量门禁检查项**：
- 有效样本数 > 0
- 时间戳完整性
- 传感器数据覆盖率

**潜在问题**：
- ❌ 如果数据质量门禁失败，整个流程会中断
- ❌ 缺少对数据异常值的预处理
- ⚠️ 时间戳格式不统一可能导致解析失败

### 2.2 语义分析阶段（步骤3-5）

**核心服务**：`DataSemanticsService`

**处理流程**：
```python
# 步骤3: 规则预筛与语义复核
semantics_service.update_specs_from_csv_data(standardized_data)
semantic_data = semantics_service.process(latest_records)
abnormal_details = semantics_service.build_abnormal_details(...)

# 步骤4: 工况总览判断
overall_judgement = semantics_service.build_overall_operating_summary(...)
semantic_ai_review = semantics_service.apply_ai_assistance(...)

# 步骤5: 时序特征提取
baseline_profile = semantics_service.build_baseline_profile(...)
```

**输出**：
- `semantic_data`: 所有指标的语义状态
- `abnormal_details`: 异常指标详情
- `overall_judgement`: 工况总览结论
- `baseline_profile`: 历史基线参考

**关键判断逻辑**：
```python
# 是否需要执行推理
should_run_reasoning = (
    abnormal_count > 0 or 
    plant_state in {"optimizable", "risk_rising", "abnormal_unstable"}
)
```

**潜在问题**：
- ⚠️ 语义规则硬编码在配置文件中，扩展性受限
- ⚠️ AI 辅助复核可能失败但不影响主流程
- ✅ 有完善的异常处理机制

### 2.3 知识检索阶段（步骤6）

**核心服务**：`KnowledgeRetrievalService`

**检索策略**：双阶段检索
1. **主检索**（primary）：基于异常候选和工况总览
2. **校核检索**（review）：基于 AI 诊断建议

**配置要求**：
```python
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=dataset-xxxxxxxxxxxxxxxxxxxx
DIFY_DATASET_ID=  # 可选，为空时自动发现
```

**降级策略**：
```python
if not dify_config.get("api_key"):
    return {
        "retrieval_summary": "Dify 检索未执行：缺少 DIFY_API_KEY 配置。",
        "recommended_measures": [],
        ...
    }
```

**潜在问题**：
- ❌ **强依赖外部 Dify 服务**，如果服务不可用会降级
- ⚠️ 检索失败时仅记录错误，不中断流程
- ✅ 有完善的降级机制

### 2.4 AI 推理阶段（步骤7）

**核心服务**：`ReasoningEngineV2`

**输入**：
- `semantic_data`: 语义分析结果
- `core_indicators`: 核心指标
- `knowledge_context`: 知识检索结果
- `overall_judgement`: 工况总览

**推理流程**：
```python
reasoning_result = reasoning_engine.analyze(
    semantic_data=semantic_data,
    core_indicators=core_indicators,
    enable_cot=enable_cot,  # Chain of Thought
    task_note="interactive入口自动诊断",
    knowledge_context=knowledge_retrieval,
    overall_judgement=overall_judgement,
)
```

**输出结构**：
```json
{
  "root_cause": "根因分析",
  "operation_suggestion": "操作建议",
  "safety_warning": "安全警告",
  "thought_process": "思考过程",
  "bottleneck_indicators": ["瓶颈指标"],
  "coupling_analysis": "耦合分析",
  "indicator_diagnoses": [...]
}
```

**潜在问题**：
- ❌ **强依赖 LLM API**，如果 API 不可用会导致流程失败
- ⚠️ LLM 响应格式不稳定可能导致解析失败
- ⚠️ 缺少响应缓存机制，相同输入会重复调用
- ✅ 有完善的错误处理和响应解析

### 2.5 决策验证阶段（步骤8）

**核心服务**：`DecisionService`

**验证流程**：
```python
decision_result = decision_service.verify_and_suggest(
    reasoning_result=reasoning_result,
    ask_model=ask_ai,
    knowledge_context=knowledge_retrieval,
    overall_judgement=overall_judgement,
    task_note="interactive入口自动决策校核",
    execution_feedback=execution_feedback,
    enable_closed_loop_validation=True/False,
)
```

**验证状态**：
- `Passed`: 通过验证
- `Pending`: 待人工确认
- `Failed`: 验证失败

**闭环验证**（可选）：
```bash
ENABLE_CLOSED_LOOP_VALIDATION=true
```

**潜在问题**：
- ⚠️ 闭环验证默认关闭，可能缺少执行反馈
- ✅ 支持人工门控机制

## 三、报告生成分析

### 3.1 报告内容结构

**核心字段**：
```python
analysis_result = {
    "status": "abnormal" | "healthy",
    "abnormal_count": int,
    "semantic_data": [...],
    "core_indicators": {...},
    "quality_gate": {...},
    "baseline_profile": {...},
    "reasoning_result": {...},
    "decision_result": {...},
    "data_overview": {...},
    "analysis_steps": [...],
    "overall_judgement": {...},
    "semantic_ai_review": {...},
    "knowledge_retrieval": {...},
    "abnormal_details": [...],
    "optimization_context": {...},
    "traceability": {...}
}
```

### 3.2 可追溯性设计

**追溯信息**：
```python
"traceability": {
    "task_id": "interactive-20260312_112345",
    "session_id": "interactive_cli",
    "mode": "统一流程",
    "data_source": "样本数据",
    "llm_provider": "direct",
    "llm_model": "deepseek-chat",
    "retrieval_provider": "dify",
    "quality_gate_status": "PASS",
    "baseline_tag_count": 42,
    "generated_at": "2026-03-12T11:23:45",
    "step_traces": [...]
}
```

**步骤追踪**：
```python
"step_traces": [
    {
        "step": 1,
        "title": "数据加载与范围确认",
        "started_at": "2026-03-12T11:23:45",
        "ended_at": "2026-03-12T11:23:46",
        "duration_ms": 1234,
        "input_summary": "...",
        "processing_summary": "...",
        "output_summary": "...",
        "manual_verification": "...",
        "interaction_checkpoint": "",
        "interaction_response": "未触发",
        "llm_tasks": []
    },
    ...
]
```

### 3.3 报告格式

**生成格式**：
- PDF 报告（用于打印和归档）
- Markdown 报告（用于在线查看）

**生成器**：`ReportGenerator`

```python
report_base = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
report_generator.generate_both_formats(analysis_result, report_base)
```

**输出位置**：
- `reports/analysis_report_20260312_112345.pdf`
- `reports/analysis_report_20260312_112345.md`

## 四、识别的关键问题

### 4.1 高优先级问题

#### 问题1: 强依赖外部服务
**影响**：如果 LLM API 或 Dify API 不可用，核心功能无法使用

**建议**：
- 实现本地 LLM 适配器（Ollama）
- 添加知识库本地缓存
- 提供离线降级模式

#### 问题2: 缺少响应缓存
**影响**：相同输入重复调用 LLM，浪费资源和时间

**建议**：
- 实现基于输入哈希的缓存机制
- 缓存有效期可配置
- 支持缓存预热

#### 问题3: 错误处理不统一
**影响**：不同模块的错误处理方式不一致，难以追踪

**建议**：
- 统一异常类型定义
- 实现全局错误处理器
- 增强错误日志记录

### 4.2 中优先级问题

#### 问题4: 配置管理分散
**影响**：配置项分散在多个文件，难以管理

**建议**：
- 使用 Pydantic 统一配置管理
- 配置验证前置
- 生成配置文档

#### 问题5: 测试覆盖不足
**影响**：重构风险高，难以保证质量

**建议**：
- 增加单元测试覆盖率
- 实现集成测试
- 添加性能基准测试

### 4.3 低优先级问题

#### 问题6: 报告格式单一
**影响**：不同场景需求难以满足

**建议**：
- 支持 HTML 交互式报告
- 支持 JSON API 输出
- 支持自定义报告模板

## 五、优化建议总结

### 5.1 立即实施（1-2周）

✅ **已完成**：推理引擎解耦
- [x] LLM 适配器抽象
- [x] 响应解析器独立
- [x] 国际化支持模块化

⏳ **待实施**：
- [ ] 添加响应缓存机制
- [ ] 统一错误处理
- [ ] 增加单元测试覆盖

### 5.2 短期实施（3-4周）

- [ ] WebSocket 服务器重构
- [ ] 配置管理统一（Pydantic）
- [ ] 实现本地 LLM 适配器
- [ ] 知识库本地缓存

### 5.3 中期实施（5-8周）

- [ ] 数据管道抽象
- [ ] 性能优化（异步 I/O）
- [ ] 集成测试框架
- [ ] 报告格式扩展

## 六、论文实验支持评估

### 6.1 当前支持能力

✅ **完整的可追溯性**
- 每次运行都有唯一 task_id
- 完整的步骤追踪
- LLM 调用记录

✅ **结构化输出**
- JSON 格式结果
- 标准化字段
- 易于统计分析

✅ **多模式支持**
- 直连 LLM 模式
- 知识检索模式
- 混合模式

### 6.2 实验需求缺口

⚠️ **对比实验支持不足**
- 缺少实验配置管理
- 难以批量运行对比实验
- 结果对比工具缺失

⚠️ **消融实验支持不足**
- 模块开关不够灵活
- 缺少特性开关（feature flag）
- 难以控制单一变量

### 6.3 改进建议

**实验配置管理**：
```python
experiment_config = {
    "experiment_id": "exp_001",
    "baseline": "rule_only",
    "variants": ["rule_llm", "rule_retrieval_llm"],
    "dataset": "data/test_set.xlsx",
    "metrics": ["accuracy", "latency", "safety"],
    "random_seed": 42
}
```

**批量实验运行器**：
```bash
python scripts/run_experiments.py --config experiments/config.yaml
```

**结果对比工具**：
```bash
python scripts/compare_results.py --exp1 exp_001 --exp2 exp_002
```

## 七、总结

### 7.1 系统优势

✅ **完整的工作流程**：8步标准化流程覆盖全链路  
✅ **良好的可追溯性**：每个步骤都有详细记录  
✅ **灵活的降级策略**：外部服务失败不影响主流程  
✅ **模块化设计**：各服务职责清晰  

### 7.2 核心风险

❌ **强依赖外部服务**：LLM 和 Dify API 不可用时功能受限  
⚠️ **缺少缓存机制**：重复调用浪费资源  
⚠️ **测试覆盖不足**：重构风险较高  

### 7.3 下一步行动

**优先级1**（本周）：
1. 实现响应缓存机制
2. 统一错误处理
3. 增加核心模块单元测试

**优先级2**（下周）：
1. 完成 WebSocket 服务器重构
2. 实现配置管理统一
3. 添加本地 LLM 适配器

**优先级3**（本月）：
1. 实验配置管理
2. 批量实验运行器
3. 性能优化

---

**文档版本**：v1.0  
**分析日期**：2026-03-12  
**分析者**：架构团队
