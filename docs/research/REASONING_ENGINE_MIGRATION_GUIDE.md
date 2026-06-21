# 推理引擎重构迁移指南

## 概述

本文档说明推理引擎（ReasoningEngineV2）的重构内容和迁移方法。

## 重构目标

✅ 将推理引擎与 LLM 客户端解耦  
✅ 提取响应解析逻辑为独立模块  
✅ 支持依赖注入，提升可测试性  
✅ 国际化支持模块化  

## 新模块结构

```
src/services/reasoning/
├── __init__.py           # 模块导出
├── engine.py             # 推理引擎核心（重构版）
├── llm_adapter.py        # LLM 适配器抽象
├── response_parser.py    # 响应解析器
└── i18n.py              # 国际化支持
```

## 核心变更

### 1. LLM 适配器抽象（llm_adapter.py）

**新增接口**：
```python
class LLMAdapter(ABC):
    @abstractmethod
    def chat(self, query: str, system_prompt: str = "", 
             temperature: float = 0.1, **kwargs) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def analyze_with_knowledge(self, abnormal_items: List[Dict], 
                               enable_cot: bool = True, **kwargs) -> Any:
        pass
```

**默认实现**：
```python
class SimpleLLMAdapter(LLMAdapter):
    # 封装现有的 SimpleLLMClient
```

### 2. 响应解析器（response_parser.py）

**功能**：
- 解析 LLM 返回的 JSON 响应
- 支持 Markdown 代码块提取
- 统一错误处理

**使用示例**：
```python
parser = ResponseParser()
result = parser.parse(llm_response)
```

### 3. 国际化支持（i18n.py）

**功能**：
- 中英文短语映射
- 文本本地化

**使用示例**：
```python
text = I18n.localize("Energy and extraction indicators may be coupled.")
# 输出: "能耗指标与提取率指标可能存在耦合关系。"
```

## 迁移方法

### 方式 1：保持兼容（推荐）

现有代码无需修改，继续使用：

```python
from src.services.reasoning_engine_v2 import ReasoningEngineV2

engine = ReasoningEngineV2(llm_config={
    "api_key": "...",
    "base_url": "...",
    "model": "..."
})
```

### 方式 2：使用新接口（推荐用于新代码）

```python
from src.services.reasoning import ReasoningEngineV2, SimpleLLMAdapter

# 创建适配器
adapter = SimpleLLMAdapter(
    api_url="...",
    api_key="...",
    model_name="..."
)

# 注入适配器
engine = ReasoningEngineV2(llm_adapter=adapter)
```

### 方式 3：自定义适配器（高级用法）

```python
from src.services.reasoning import LLMAdapter, ReasoningEngineV2

class CustomLLMAdapter(LLMAdapter):
    def chat(self, query, system_prompt="", temperature=0.1, **kwargs):
        # 自定义实现
        pass
    
    def analyze_with_knowledge(self, abnormal_items, enable_cot=True, **kwargs):
        # 自定义实现
        pass

adapter = CustomLLMAdapter()
engine = ReasoningEngineV2(llm_adapter=adapter)
```

## 优势

### 1. 可测试性提升

**重构前**：
```python
# 难以测试，需要真实的 LLM API
engine = ReasoningEngineV2(llm_config=real_config)
result = engine.analyze(data)
```

**重构后**：
```python
# 使用 Mock 适配器轻松测试
mock_adapter = MockLLMAdapter()
engine = ReasoningEngineV2(llm_adapter=mock_adapter)
result = engine.analyze(data)
```

### 2. 支持多种 LLM 提供商

可以轻松添加新的 LLM 提供商：
- OpenAI
- Claude (Anthropic)
- 本地模型（Ollama）
- 自定义 API

### 3. 响应解析逻辑独立

可以单独测试和优化响应解析：
```python
parser = ResponseParser()
result = parser.parse(complex_response)
```

## 向后兼容性

✅ 完全向后兼容  
✅ 现有代码无需修改  
✅ 新旧接口可以共存  

## 测试验证

运行验证脚本：
```bash
python scripts/verify_reasoning_refactor.py
```

运行单元测试：
```bash
pytest tests/test_reasoning_refactored.py -v
```

## 后续计划

- [ ] 添加更多 LLM 适配器（Claude、本地模型）
- [ ] 优化响应解析性能
- [ ] 扩展国际化支持（支持更多语言）
- [ ] 添加响应缓存机制

## 常见问题

### Q: 是否需要修改现有代码？
A: 不需要。重构保持了完全的向后兼容性。

### Q: 如何切换到新接口？
A: 使用 `from src.services.reasoning import ReasoningEngineV2` 并注入适配器。

### Q: 性能是否受影响？
A: 不会。重构仅改变了代码组织方式，不影响运行时性能。

---

**文档版本**：v1.0  
**创建日期**：2026-03-12  
**维护者**：架构团队
