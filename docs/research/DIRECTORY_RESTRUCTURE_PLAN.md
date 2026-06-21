# 目录结构重构计划

## 当前问题分析

### 🔴 严重问题

1. **前端参考文件混乱**
   - `frontend/参考的layouts/` - 中文目录名
   - `frontend/_archive/` - 归档文件与源码混合
   - `frontend/layouts/` 与 `frontend/参考的layouts/` 重复

2. **资源文件位置不当**
   - `src/resets/` - 命名不规范
   - `src/resets/公文格式要求.doc` - 中文文件名
   - 字体文件应该在 `assets/` 或 `resources/`

3. **根目录文件过多**
   - `main-run.pid` - 运行时文件
   - `llm_configs.json` - 应该在 config/
   - `main.py` - 入口文件命名不清晰

4. **测试文件命名不一致**
   - 有些带 `test_semantics.py`（新）
   - 有些带 `test_semantics_ai_assist.py`（旧）

### 🟡 中等问题

5. **文档分类不清晰**
   - `docs/paper/` - 论文相关
   - `docs/research/` - 研究相关
   - `docs/business/` - 商业相关
   - 分类重叠

6. **脚本目录混乱**
   - `scripts/` 下有各种用途的脚本
   - `scripts/manual/` 只有一个文件

7. **知识库目录空置**
   - `knowledge_docs/` 空目录

## 重构方案

### 标准化目录结构

```
demo2opt/
├── .github/                    # GitHub 配置
├── config/                     # 配置文件
│   ├── indicators.yaml
│   ├── derived_metrics.yaml
│   ├── metric_design_values.yaml
│   └── llm_configs.json       # 移动到这里
├── data/                       # 数据文件
│   ├── samples/               # 示例数据
│   │   └── 运行诊断.xlsx
│   ├── references/            # 参考文档
│   │   └── 工业气体空分产品单位综合电耗限额.pdf
│   └── data_dictionary.csv
├── docs/                       # 文档
│   ├── api/                   # API 文档
│   │   ├── rest_api.md
│   │   └── websocket_api.md
│   ├── architecture/          # 架构文档
│   │   ├── optimization_plan.md
│   │   ├── workflow_analysis.md
│   │   └── migration_guides/
│   ├── development/           # 开发文档
│   │   ├── contributing.md
│   │   └── project_structure.md
│   ├── research/              # 研究文档
│   │   ├── paper/
│   │   └── experiments/
│   └── user/                  # 用户文档
│       ├── user_guide.md
│       └── web_guide.md
├── frontend/                   # 前端代码
│   ├── public/
│   ├── src/
│   │   ├── assets/           # 静态资源
│   │   ├── components/
│   │   ├── composables/
│   │   ├── router/
│   │   └── views/
│   ├── package.json
│   └── vite.config.js
├── resources/                  # 资源文件（新增）
│   ├── fonts/                 # 字体文件
│   │   ├── fangzheng_xiaobiaosong.ttf
│   │   └── fangsong_gb2312.ttf
│   └── templates/             # 模板文件
│       └── official_document_format.doc
├── scripts/                    # 脚本
│   ├── dev/                   # 开发脚本
│   │   ├── start_web.py
│   │   └── test_api.py
│   ├── maintenance/           # 维护脚本
│   │   └── fix_task_statuses.py
│   ├── experiments/           # 实验脚本
│   │   ├── run_interactive.py
│   │   └── run_sample_flow_with_timing.py
│   └── testing/               # 测试脚本
│       └── run_e2e_test.py
├── src/                        # 源代码
│   ├── agent/                 # Agent 模块
│   ├── api/                   # API 层
│   │   ├── rest/
│   │   └── ws/
│   ├── core/                  # 核心模块
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   ├── error_handler.py
│   │   └── task_manager.py
│   ├── prompts/               # 提示词模板
│   ├── schemas/               # 数据模型
│   ├── services/              # 业务服务
│   │   ├── reasoning/        # 推理服务
│   │   ├── data_loader.py
│   │   ├── data_semantics.py
│   │   └── ...
│   └── utils/                 # 工具函数
├── tests/                      # 测试
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   └── e2e/                   # 端到端测试
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── setup.py                   # 新增：标准化安装
```

## 执行步骤

### 阶段 1：清理和移动（不影响功能）

1. 移动资源文件
2. 重命名中文文件/目录
3. 整理前端归档文件
4. 清理空目录
5. 移动配置文件

### 阶段 2：重组文档

1. 按用途重新分类文档
2. 更新文档内链接

### 阶段 3：重组脚本

1. 按用途分类脚本
2. 更新脚本导入路径

### 阶段 4：重组测试

1. 按类型分类测试
2. 更新测试导入路径

### 阶段 5：验证

1. 运行所有测试
2. 验证 Web 服务启动
3. 验证交互式脚本

## 风险评估

- **低风险**：移动资源文件、文档重组
- **中风险**：脚本重组（需要更新路径）
- **高风险**：测试重组（可能影响 CI/CD）

## 回滚策略

- 使用 Git 分支进行重构
- 每个阶段单独提交
- 保留旧文件的符号链接（临时）
