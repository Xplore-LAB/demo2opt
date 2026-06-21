"""最小化目录整理 - 只修复关键问题"""
import os
import shutil
from pathlib import Path

print("=" * 70)
print("最小化目录整理")
print("=" * 70)

# 1. 创建 resources 目录
print("\n[1/3] 创建 resources 目录...")
Path("resources/fonts").mkdir(parents=True, exist_ok=True)
Path("resources/templates").mkdir(parents=True, exist_ok=True)
print("✓ 创建完成")

# 2. 移动资源文件（如果存在）
print("\n[2/3] 移动资源文件...")
moves = [
    ("src/resets/fonts/方正小标宋简体.ttf", "resources/fonts/fangzheng_xiaobiaosong.ttf"),
    ("src/resets/fonts/仿宋_GB2312.ttf", "resources/fonts/fangsong_gb2312.ttf"),
    ("src/resets/公文格式要求.doc", "resources/templates/official_document_format.doc"),
]

for src, dst in moves:
    if Path(src).exists() and not Path(dst).exists():
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"✓ 复制: {src} -> {dst}")

# 3. 更新 .gitignore
print("\n[3/3] 更新 .gitignore...")
gitignore_additions = [
    "# 运行时文件",
    "*.pid",
    "main-run.pid",
    "",
    "# 临时文件",
    "*.tmp",
    "*.log",
]

gitignore_path = Path(".gitignore")
if gitignore_path.exists():
    content = gitignore_path.read_text(encoding='utf-8')
    if "main-run.pid" not in content:
        with open(gitignore_path, 'a', encoding='utf-8') as f:
            f.write("\n" + "\n".join(gitignore_additions) + "\n")
        print("✓ 更新 .gitignore")
    else:
        print("⚠️  .gitignore 已包含相关规则")

print("\n" + "=" * 70)
print("✅ 整理完成！")
print("=" * 70)
print("\n说明：")
print("- 资源文件已复制到 resources/ 目录")
print("- 原文件保留，确保兼容性")
print("- .gitignore 已更新")
