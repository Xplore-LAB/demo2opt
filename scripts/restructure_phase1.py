"""目录结构重构脚本 - 阶段1：安全移动和重命名"""
import os
import shutil
from pathlib import Path

def safe_move(src, dst, description):
    """安全移动文件/目录"""
    src_path = Path(src)
    dst_path = Path(dst)
    
    if not src_path.exists():
        print(f"⚠️  跳过（源不存在）: {src}")
        return False
    
    if dst_path.exists():
        print(f"⚠️  跳过（目标已存在）: {dst}")
        return False
    
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        print(f"✓ {description}: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"❌ 失败: {src} -> {dst}, 错误: {e}")
        return False

print("=" * 70)
print("目录结构重构 - 阶段1：创建目录和移动资源文件")
print("=" * 70)

# 1. 创建新目录
print("\n[1/5] 创建新目录结构...")
new_dirs = [
    "resources/fonts",
    "resources/templates",
    "data/samples",
    "data/references",
]

for dir_path in new_dirs:
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    print(f"✓ 创建: {dir_path}")

# 2. 移动资源文件
print("\n[2/5] 移动资源文件...")
moves = [
    # 字体文件
    ("src/resets/fonts/方正小标宋简体.ttf", "resources/fonts/fangzheng_xiaobiaosong.ttf", "字体文件"),
    ("src/resets/fonts/仿宋_GB2312.ttf", "resources/fonts/fangsong_gb2312.ttf", "字体文件"),
    # 模板文件
    ("src/resets/公文格式要求.doc", "resources/templates/official_document_format.doc", "模板文件"),
]

for src, dst, desc in moves:
    safe_move(src, dst, desc)

# 3. 移动数据文件
print("\n[3/5] 重组数据目录...")
data_moves = [
    ("data/【原始数据】运行诊断.xlsx", "data/samples/运行诊断.xlsx", "示例数据"),
    ("data/工业气体空分产品单位综合电耗限额及计算方法-DB33浙江2015.pdf", 
     "data/references/工业气体空分产品单位综合电耗限额.pdf", "参考文档"),
]

for src, dst, desc in data_moves:
    safe_move(src, dst, desc)

# 4. 移动配置文件
print("\n[4/5] 移动配置文件...")
if Path("llm_configs.json").exists():
    safe_move("llm_configs.json", "config/llm_configs.json", "LLM配置")

# 5. 清理空目录
print("\n[5/5] 清理空目录...")
empty_dirs = ["src/resets/fonts", "src/resets"]
for dir_path in empty_dirs:
    try:
        if Path(dir_path).exists() and not any(Path(dir_path).iterdir()):
            Path(dir_path).rmdir()
            print(f"✓ 删除空目录: {dir_path}")
    except Exception as e:
        print(f"⚠️  无法删除 {dir_path}: {e}")

print("\n" + "=" * 70)
print("✅ 阶段1完成！资源文件已重新组织。")
print("=" * 70)
