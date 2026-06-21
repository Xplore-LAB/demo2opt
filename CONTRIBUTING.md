# 贡献指南

感谢你为 demo2opt 做贡献。提交前请先阅读本文件。

## 开发环境

- Python 3.10+
- Node.js 20+
- npm 10+

## 本地启动

1. 安装后端依赖

```bash
pip install -r requirements.txt
```

2. 启动后端

```bash
python scripts/start_web.py
```

3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## 提交规范

- 新功能请基于分支开发，建议命名：`feat/<topic>`、`fix/<topic>`。
- 提交信息建议使用：`feat: ...`、`fix: ...`、`docs: ...`、`refactor: ...`、`test: ...`。
- 不要提交运行产物和本地密钥文件（如 `.env`、`logs/`、`reports/`、`task_progress/`）。

## 提交前检查

```bash
pytest
cd frontend && npm run build
```

## Pull Request 要求

- 描述清楚变更目标、方案和影响范围。
- 关联对应 Issue（如有）。
- 涉及接口或页面行为变化时，请附截图或示例请求/响应。
