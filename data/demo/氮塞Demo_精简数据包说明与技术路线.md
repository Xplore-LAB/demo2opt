# 氮塞诊断 Demo 精简数据包说明

## 1. 本数据包用途

本数据包用于第一版氮塞诊断 Demo，重点展示：

1. 基于 AI705 趋势图识别疑似氮塞区间；
2. 基于原始时序数据截取事件窗口；
3. 联看 AI701、FI702、FIC701、FIQ101、FIQC102、FIC103、FI105、FIC1、PdI2、PdI1 等测点；
4. 输出强疑似、需排除、观察、边界样本的诊断结论。

第一版暂不启用物料平衡计算和流程图加载。

---

## 2. 本数据包包含的文件

```text
01_required_inputs/
├─ demo_selected_events_summary.csv
├─ demo_selected_events_detail.csv
└─ demo_event_window_index.csv

02_event_windows_raw_5s/
├─ E11_window_raw_5s.csv
├─ E19_window_raw_5s.csv
├─ E08_window_raw_5s.csv
├─ E06_window_raw_5s.csv
├─ E15_window_raw_5s.csv
└─ E26_window_raw_5s.csv

03_event_windows_1min/
├─ E11_window_1min_median.csv
├─ E19_window_1min_median.csv
├─ E08_window_1min_median.csv
├─ E06_window_1min_median.csv
├─ E15_window_1min_median.csv
└─ E26_window_1min_median.csv

04_selected_figures/
├─ AI705_full_period_candidates.png
├─ E11_AI705_case_plot.png
├─ E19_AI705_case_plot.png
├─ E08_AI705_case_plot.png
├─ E06_AI705_case_plot.png
├─ E15_AI705_case_plot.png
└─ E26_AI705_case_plot.png

05_config/
├─ selected_demo_cases.json
├─ tag_mapping.json
└─ material_balance_placeholder.json

06_docs/
└─ AI705_氮塞候选区间_初筛分析报告.md
```

---

## 3. 选用事件

| 事件 | 类型 | 用途 |
|---|---|---|
| E11 | 主案例：强疑似氮塞 | 默认展示，突出明显下凹和多测点联动 |
| E19 | 备用正样本：强疑似氮塞 | 作为第二个强疑似样本 |
| E08 | 对照案例：疑似但需排除负荷扰动 | 展示负荷扰动排查 |
| E06 | 观察案例：联动证据不足 | 展示有下凹但不直接判氮塞 |
| E15 | 边界案例：短时小幅下凹 | 展示低风险边界样本 |
| E26 | 边界案例：短时小幅下凹 | 展示短时小幅波动处理 |

---

## 4. Demo 技术路线

```text
读取 selected_demo_cases.json
    ↓
默认加载 E11
    ↓
展示 04_selected_figures/E11_AI705_case_plot.png
    ↓
读取 01_required_inputs/demo_selected_events_summary.csv
    ↓
展示开始时间、谷底时间、结束时间、持续时间、下凹幅度
    ↓
读取 03_event_windows_1min/E11_window_1min_median.csv
    ↓
绘制 AI705、AI701、FI702、FIC701、FIQ101 等联动曲线
    ↓
读取 01_required_inputs/demo_selected_events_detail.csv
    ↓
展示前30均值、区间均值、后30均值和变化率
    ↓
生成诊断卡片
```

---

## 5. 第一版诊断逻辑

### 5.1 强疑似氮塞

满足以下特征时，输出“强疑似氮塞”：

1. AI705 下凹明显；
2. 持续时间较长；
3. AI701、FI702、FIC701 中至少两个出现联动；
4. 负荷扰动不能完全解释该下凹。

### 5.2 疑似但需排除

满足以下特征时，输出“疑似但需排除负荷扰动”：

1. AI705 有明显下凹；
2. 同时 FIQ101、FIQC102、FIC103 等负荷变量变化较大；
3. 需要先核对调负荷或产品抽取变化。

### 5.3 观察候选

满足以下特征时，输出“观察候选”：

1. AI705 有下凹；
2. 下凹幅度较小或持续时间较短；
3. AI701、FI702、FIC701 联动证据不足。

---

## 6. 第一版不启用的内容

| 内容 | 原因 |
|---|---|
| 完整 50 万行原始数据 | 已切出所需事件窗口，Demo 不需要加载全量数据 |
| 流程图.rar | 第一版只用于测点说明，不作为运行输入 |
| 物料平衡.sfit | 需先导出系数和基准值，第一版先预留接口 |
| 分子筛切换记录 | 当前未提供，后续可扩展 |
| 报警 / 操作记录 | 当前未提供，后续可扩展 |
| 专家标签 | 当前未提供，后续可补充用于验证准确率 |

---

## 7. 页面建议

第一版页面只需四块：

1. **候选事件列表**：读取 `demo_selected_events_summary.csv`；
2. **AI705 图像识别区**：展示 `04_selected_figures/` 中的对应图片；
3. **多测点联动曲线区**：读取 `03_event_windows_1min/` 中的事件窗口数据；
4. **诊断卡片区**：根据摘要表、明细表和规则输出判断依据、可能原因、建议检查。

---

## 8. 结论

本精简数据包已经去掉全量数据依赖，只保留第一版 Demo 必需内容。开发时优先使用 `E11` 做主案例，使用 `E08` 展示排除能力，使用 `E06/E15/E26` 展示观察和边界样本处理能力。
