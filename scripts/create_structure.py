"""创建标准化目录结构"""
import os
from pathlib import Path

# 定义新的目录结构
new_dirs = [
    "resources/fonts",
    "resources/templates",
    "data/samples",
    "data/references",
    "scripts/dev",
    "scripts/maintenance",
    "scripts/experiments",
    "scripts/testing",
]

print("创建标准化目录结构...")
for dir_path in new_dirs:
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    print(f"✓ 创建目录: {dir_path}")

print("\n✅ 目录结构创建完成！")
