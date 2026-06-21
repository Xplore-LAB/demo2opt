"""测试完整工作流程"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 检查环境配置
print("=" * 70)
print("检查环境配置...")
print("=" * 70)

required_env = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"]
missing = [key for key in required_env if not os.getenv(key)]

if missing:
    print(f"❌ 缺少必需的环境变量: {', '.join(missing)}")
    print("\n请创建 .env 文件并配置以下变量：")
    for key in missing:
        print(f"  {key}=...")
    sys.exit(1)

print("✓ 环境配置检查通过")
print(f"  LLM Provider: {os.getenv('LLM_BASE_URL')}")
print(f"  LLM Model: {os.getenv('LLM_MODEL_NAME')}")

# 检查数据文件
data_file = "data/【原始数据】运行诊断.xlsx"
if not os.path.exists(data_file):
    print(f"❌ 数据文件不存在: {data_file}")
    sys.exit(1)

print(f"✓ 数据文件: {data_file}")
