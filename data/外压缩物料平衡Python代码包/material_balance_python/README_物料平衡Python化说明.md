# 外压缩物料平衡方程 Python 版说明

## 1. 结论

你提供的宽表数据 **基本满足物料平衡方程的测点需求**，但目前还不能直接完整计算方程，原因有两点：

1. 方程所需的拟合系数和基准值还没有明确给出；
2. `HY_2080_1#TI1003.PV` 原料空气入口温度在当前数据表中没有有效数值，显示为 `I/O Timeout`，温度修正项暂时不能直接使用。

因此当前状态为：

| 项目 | 状态 |
|---|---|
| 测点字段 | 基本齐全 |
| 氧、氮、液氮、中压氮、空气、氩馏分、粗氩、液位 | 可从宽表读取 |
| TEMP 温度项 | 当前不可用，需要更换有效温度测点或暂时关闭温度修正 |
| 拟合系数 | 缺失，需要从 MATLAB / `.sfit` / 原始拟合结果导出 |
| 是否可直接算最终 AIR、FAR、CAR、LEV | 暂不能 |
| 是否可接入程序 | 可以，先接入代码框架和数据校验 |

---

## 2. 当前数据表字段满足性

| 方程变量 | 含义 | 推荐字段 | 当前数据是否满足 |
|---|---|---|---|
| GOX | 产品氧气流量 | `HY_2080_1#FIQC102_2.PV` | 满足 |
| GAN | 产品氮气流量 | `HY_2080_1#FIC103_2.PV` | 满足，但命名需确认 FIC/FIQC |
| LIN | 液氮流量 | `HY_2080_1#FIC8.PV` | 基本满足，需确认是否为产品液氮外送 |
| GAR | 中压氮气去用户流量 | `HY_2080_1#FI131.PV` | 满足 |
| TEMP | 环境温度 / 原料空气入口温度 | `HY_2080_1#TI1003.PV` | 字段存在，但当前数据无有效数值 |
| TURBINE | 膨胀空气相关流量 | `HY_2080_1#FIC1_1.PV` 或 `HY_2080_1#FI105.PV` | 满足，但需二选一验证 |
| AIR | 总空气流量 | `HY_2080_1#FIQ101.PV` | 满足 |
| FAR | 氩馏分流量 | `HY_2080_1#FI702.PV` | 满足 |
| CAR | 粗氩流量 | `HY_2080_1#FIC701.PV` | 满足 |
| LEV | 粗氩冷凝器液位 | `HY_2080_1#LIC701.PV` | 满足 |

---

## 3. 文件说明

本目录包含两个文件：

```text
asu_material_balance_model.py
material_balance_config_template.json
```

### 3.1 `asu_material_balance_model.py`

提供以下功能：

1. 读取原始宽表；
2. 删除中文描述行；
3. 时间列解析；
4. 1 min 重采样；
5. 检查方程所需测点是否存在；
6. 计算物料平衡模型；
7. 输出模型值、实测值、残差、偏高/偏低判断。

### 3.2 `material_balance_config_template.json`

这是待填写的系数模板。

需要补齐：

```text
GARBase、TEMPBase、TURBBase
AIRCoef1~4
GANCoef1~4
TURBCoef1~3
FARCoef1~2
CARCoef1~2
LEVCoef1~2
```

---

## 4. 推荐使用方式

### 4.1 先检查数据

```python
from asu_material_balance_model import load_wide_table, check_required_columns

df = load_wide_table("衢州杭氧1#42000数据.csv")
check = check_required_columns(df, turbine_source="TURBINE_FIC1")
print(check)
```

### 4.2 填写系数

打开：

```text
material_balance_config_template.json
```

把所有 `null` 替换为实际系数和基准值。

### 4.3 计算物料平衡

```python
from asu_material_balance_model import (
    load_wide_table,
    resample_1min,
    BalanceCoefficients,
    compute_material_balance,
    summarize_window
)

df = load_wide_table("衢州杭氧1#42000数据.csv")
df_1min = resample_1min(df)

coeffs = BalanceCoefficients.from_json("material_balance_config.json")

result = compute_material_balance(
    df_1min,
    coeffs,
    turbine_source="TURBINE_FIC1",
    use_temp_correction=False,  # 当前 TI1003 无有效数值，先关闭温度修正
    allowed_percent=0.0125
)

summary = summarize_window(result)
print(summary)
```

---

## 5. 关于 TURBINE 变量

当前有两个候选：

| 候选 | 字段 | 含义 |
|---|---|---|
| 方案 A | `HY_2080_1#FIC1_1.PV` | 膨胀空气进上塔流量 |
| 方案 B | `HY_2080_1#FI105.PV` | 膨胀机增压端空气流量 |

建议后续做两版计算：

```python
result_a = compute_material_balance(df_1min, coeffs, turbine_source="TURBINE_FIC1", use_temp_correction=False)
result_b = compute_material_balance(df_1min, coeffs, turbine_source="TURBINE_FI105", use_temp_correction=False)
```

比较 AIR、FAR、CAR、LEV 的残差，哪一版在正常稳态窗口中残差更小、更稳定，就采用哪一版。

---

## 6. 关于 TEMP 变量

当前数据中的：

```text
HY_2080_1#TI1003.PV
```

字段存在，但数值解析后有效数据为 0，说明当前文件内该测点基本不可用。

处理建议：

1. 第一版计算时设置 `use_temp_correction=False`；
2. 找到其他有效环境温度或空气入口温度测点替代；
3. 如果原方程温度修正项影响很小，也可以在 Demo 中说明“温度修正暂不启用”。

---

## 7. 关于 MATLAB 文件

你上传的 `a1.m` ~ `a8.m` 是 MATLAB Curve Fitting 自动导出的拟合脚本，里面能看出拟合关系类型，例如：

| 文件 | 关系 | 拟合类型 |
|---|---|---|
| a1.m | PAIR vs EGOX | poly2 |
| a2.m | FIC103AVG vs EGOX | poly1 |
| a3.m | FI702AVG vs PAIR | poly1 |
| a4.m | FIC701AVG vs PAIR | poly1 |
| a8.m | FIC1AVG vs EGOX | poly1 |

但这些 `.m` 文件本身没有给出最终系数值。需要在 MATLAB 中运行拟合后导出 `fitresult.p1`、`fitresult.p2` 等系数，或直接保存成 JSON。

---

## 8. 当前建议

当前建议分两步：

### 第一步：先接入代码框架

在 Demo 里先把：

1. 字段映射；
2. 数据读取；
3. 1 min 重采样；
4. 变量检查；
5. 物料平衡接口；
6. 残差输出结构；

都接好。

### 第二步：补齐系数后再启用计算

等系数和基准值确认后，再正式启用：

1. AIR 模型值；
2. FAR 模型值；
3. CAR 模型值；
4. LEV 模型值；
5. 偏高 / 偏低判断；
6. 残差诊断。

---

## 9. 一句话结论

你的数据表 **测点基本够用**，但当前 **系数和温度测点还不够**。  
程序可以先接入 Python 版物料平衡代码，第一版用于数据校验和接口预留；等 MATLAB 拟合系数、GARBase、TEMPBase、TURBBase 补齐后，就可以正式计算物料平衡残差。
