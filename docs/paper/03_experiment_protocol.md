# 实验协议与复现规范

## 1. 实验目标

- 验证完整框架在效果、安全、时延、可解释性上的增益。  
- 量化“必经知识检索 + 风险门控”对结果质量的贡献。  

## 2. 实验设置

### 2.1 数据划分

- 建议至少三段划分：训练集 / 验证集 / 测试集。  
- 保持时间连续性，避免未来信息泄漏。  
- 固定随机种子并记录在实验配置中。  

### 2.2 方法组

1. Rule-only  
2. Direct-LLM-only  
3. Rule + Direct-LLM  
4. Full framework（Rule + Semantic + Retrieval + Reasoning + Gate）  

### 2.3 消融组

1. 去知识检索（Step 6）  
2. 去语义复核（Step 3 AI review）  
3. 去人工门控（interaction bypass）  

## 3. 指标定义

### 3.1 效果指标

- 异常定位准确率 / 召回率  
- 建议命中率（专家认可）  
- 建议可执行率（是否可操作、是否具备前置条件）  

### 3.2 安全指标

- 高风险误判率  
- 违规建议率（触碰工艺安全边界）  
- 人工拦截有效率  

### 3.3 时延指标

- 端到端总耗时（ms）  
- 分步骤耗时（Step 1~8）  
- 检索耗时 / 推理耗时占比  

### 3.4 可解释性指标

- 专家一致性（Cohen's Kappa）  
- 解释完整度评分（摘要、证据、手段、风险提示）  

## 4. 统计检验

- 每组至少运行 N 次，报告均值 ± 标准差。  
- 进行显著性检验（t-test 或 Wilcoxon）。  
- 报告 p-value，并给出效应量。  

## 5. 产物规范（必须落盘）

- 运行轨迹：  
  - `reports/run_trace_raw_*.json`  
  - `reports/run_trace_summary_*.json`  
  - `reports/run_trace_timeline_*.md`  
  - `reports/run_trace_timeline_*.csv`  
- 模块真实 I/O：  
  - `reports/dify_retrieval_real_io_*.json/.md`  

## 6. 图表对应关系

- Table 1：主实验（4组方法对比）  
- Table 2：消融实验（3组 ablation）  
- Table 3：鲁棒性实验（噪声/缺失/漂移）  
- Figure 1：方法框架图  
- Figure 2：步骤耗时堆叠图  
- Figure 3：案例决策链图  

## 7. 复现命令（模板）

```bash
# 1) 后端测试
pytest

# 2) 指定模块测试（例：Dify 检索）
pytest tests/test_dify_retrieval_module.py -q

# 3) 端到端（可选）
npm run test:e2e
```

## 8. 审核清单（提交前）

1. 所有表格是否可从脚本重建。  
2. 所有核心结论是否有对应指标。  
3. 是否包含失败案例与边界说明。  
4. 是否给出配置与随机种子。  
