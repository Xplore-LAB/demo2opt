"""测试程序完整性 - 验证核心功能"""
import sys
import os

print("=" * 70)
print("程序完整性测试")
print("=" * 70)

# 1. 检查环境配置
print("\n[1/4] 检查环境配置...")
required_env = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"]
missing = []
for key in required_env:
    if not os.getenv(key):
        missing.append(key)
        print(f"❌ 缺少: {key}")
    else:
        print(f"✓ {key}: {os.getenv(key)[:20]}...")

if missing:
    print(f"\n⚠️  缺少必需环境变量: {', '.join(missing)}")
    print("请创建 .env 文件并配置这些变量")
    print("\n跳过 LLM 相关测试，继续其他测试...")

# 2. 测试核心模块导入
print("\n[2/4] 测试核心模块导入...")
try:
    from src.services.reasoning import ReasoningEngineV2, SimpleLLMAdapter
    print("✓ 推理引擎模块")
    
    from src.utils.cache import ResponseCache
    print("✓ 缓存模块")
    
    from src.core.exceptions import ConfigurationError, LLMError
    print("✓ 异常处理模块")
    
    from src.services.data_loader import ExcelDataLoader
    print("✓ 数据加载模块")
    
    from src.services.data_semantics import DataSemanticsService
    print("✓ 语义分析模块")
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# 3. 测试数据文件
print("\n[3/4] 检查数据文件...")
data_files = [
    "data/【原始数据】运行诊断.xlsx",
    "data/data_dictionary.csv",
]
for file_path in data_files:
    if os.path.exists(file_path):
        print(f"✓ {file_path}")
    else:
        print(f"⚠️  未找到: {file_path}")

# 4. 测试缓存功能
print("\n[4/4] 测试缓存功能...")
try:
    cache = ResponseCache(enabled=True)
    cache.set("test_key", "test_value")
    value = cache.get("test_key")
    if value == "test_value":
        print("✓ 缓存读写正常")
    else:
        print("❌ 缓存读写异常")
except Exception as e:
    print(f"❌ 缓存测试失败: {e}")

print("\n" + "=" * 70)
print("✅ 基础测试完成")
print("=" * 70)
