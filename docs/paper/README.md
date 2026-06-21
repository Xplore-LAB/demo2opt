# 论文工作区（docs/paper）

本目录集中存放“论文撰写与投稿”相关文档，目标是把项目从工程可用推进到研究可投稿。

## 文件索引

- `01_paper_outline.md`：论文大纲（可投稿版）
- `02_top_conference_gap_plan.md`：顶会差距清单与 12 周冲刺计划
- `03_experiment_protocol.md`：实验协议、评估指标、复现规范
- `04_writing_template.md`：写作模板（可直接填充）

## 使用顺序（建议）

1. 先读 `02_top_conference_gap_plan.md`，明确缺口与优先级。  
2. 按 `03_experiment_protocol.md` 搭建统一实验脚本与结果表。  
3. 按 `01_paper_outline.md` 写结构化初稿。  
4. 使用 `04_writing_template.md` 快速落地摘要、贡献、实验与讨论。  

## 产出约束

- 论文相关图表与结果必须能从仓库脚本复现。
- 论文中的核心结论必须可追溯到 `reports/` 中的运行证据。
- 新增论文文档统一放在本目录，避免分散到其他 `docs/` 子目录。
