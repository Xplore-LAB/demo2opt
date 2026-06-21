"""
外压缩空分装置物料平衡模型 Python 版

用途：
1. 将外压缩物料平衡方程封装成可调用函数；
2. 从宽表数据中读取对应测点；
3. 计算 EGOX、PAIR、GAN+LIN、TURBBY、FAR、CAR、LEV、AIR；
4. 与现场实测 AIR、FI702、FIC701、LIC701 等做残差对比。

重要说明：
- 本文件不内置拟合系数。AIRCoef、GANCoef、TURBCoef、FARCoef、CARCoef、LEVCoef
  以及 GARBase、TEMPBase、TURBBase 需要从原 MATLAB 拟合结果或历史稳态数据中确认。
- 如果 TEMP 列无有效数据，可先将 use_temp_correction=False，使温度修正项为 0。
- TURBINE 可在 FI105 和 FIC1_1 两个候选测点间切换，建议用稳态窗口残差验证最终口径。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import json
import numpy as np
import pandas as pd


DEFAULT_TAG_MAPPING = {
    # 方程输入
    "GOX": "HY_2080_1#FIQC102_2.PV",   # 产品氧气流量
    "GAN": "HY_2080_1#FIC103_2.PV",    # 产品氮气流量，字段名待现场确认
    "LIN": "HY_2080_1#FIC8.PV",        # 液氮流量，需确认是否为产品液氮外送量
    "GAR": "HY_2080_1#FI131.PV",       # 中压氮气去用户流量
    "TEMP": "HY_2080_1#TI1003.PV",     # 原料空气入口温度；当前数据中该列可能无有效数值

    # TURBINE 两个候选，实际计算时二选一
    "TURBINE_FIC1": "HY_2080_1#FIC1_1.PV",  # 膨胀空气进上塔流量
    "TURBINE_FI105": "HY_2080_1#FI105.PV",  # 膨胀机增压端空气流量

    # 现场实测输出，用于残差对比
    "AIR_MEAS": "HY_2080_1#FIQ101.PV",      # 原料空气总流量
    "FAR_MEAS": "HY_2080_1#FI702.PV",       # 氩馏分流量
    "CAR_MEAS": "HY_2080_1#FIC701.PV",      # 粗氩流量
    "LEV_MEAS": "HY_2080_1#LIC701.PV",      # 粗氩冷凝器液位
}


@dataclass
class BalanceCoefficients:
    """
    外压缩物料平衡模型系数。
    所有字段必须由拟合结果或现场确认值提供。
    """

    GARBase: float
    TEMPBase: float
    TURBBase: float

    AIRCoef1: float
    AIRCoef2: float
    AIRCoef3: float
    AIRCoef4: float

    GANCoef1: float
    GANCoef2: float
    GANCoef3: float
    GANCoef4: float

    TURBCoef1: float
    TURBCoef2: float
    TURBCoef3: float

    FARCoef1: float
    FARCoef2: float

    CARCoef1: float
    CARCoef2: float

    LEVCoef1: float
    LEVCoef2: float

    @classmethod
    def from_json(cls, path: str | Path) -> "BalanceCoefficients":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        missing = [k for k in cls.__dataclass_fields__ if data.get(k) is None]
        if missing:
            raise ValueError(f"物料平衡系数未填写完整，缺少：{missing}")
        return cls(**{k: float(data[k]) for k in cls.__dataclass_fields__})

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def load_wide_table(csv_path: str | Path) -> pd.DataFrame:
    """
    读取装置宽表。

    你的原始 CSV 第一行是中文描述，不是数据。
    本函数会自动删除该描述行，并把 Unnamed: 0 改为 timestamp。
    """
    df = pd.read_csv(csv_path, low_memory=False)

    if "Unnamed: 0" not in df.columns:
        raise ValueError("未找到时间列 Unnamed: 0，请检查原始宽表格式。")

    # 第一行是中文测点描述，时间列为空；删除这一行
    if pd.isna(df.loc[0, "Unnamed: 0"]):
        df = df.iloc[1:].copy()

    df = df.rename(columns={"Unnamed: 0": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d-%b-%y %H:%M:%S", errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    for c in df.columns:
        if c != "timestamp":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def resample_1min(df: pd.DataFrame, how: str = "median") -> pd.DataFrame:
    """
    将 5 秒级数据重采样为 1 分钟数据。
    默认采用中位数，抗瞬时毛刺能力更好。
    """
    if "timestamp" not in df.columns:
        raise ValueError("df 必须包含 timestamp 列。")

    data = df.set_index("timestamp")
    if how == "mean":
        out = data.resample("1min").mean(numeric_only=True)
    elif how == "median":
        out = data.resample("1min").median(numeric_only=True)
    else:
        raise ValueError("how 只能是 mean 或 median。")
    return out.reset_index()


def check_required_columns(
    df: pd.DataFrame,
    tag_mapping: Dict[str, str] = DEFAULT_TAG_MAPPING,
    turbine_source: str = "TURBINE_FIC1",
) -> pd.DataFrame:
    """
    检查物料平衡计算所需测点是否存在，以及有效数值比例。
    """
    keys = [
        "GOX", "GAN", "LIN", "GAR", "TEMP",
        turbine_source,
        "AIR_MEAS", "FAR_MEAS", "CAR_MEAS", "LEV_MEAS"
    ]

    rows = []
    for key in keys:
        col = tag_mapping[key]
        exists = col in df.columns
        if exists:
            valid_count = pd.to_numeric(df[col], errors="coerce").notna().sum()
            valid_ratio = float(valid_count / len(df)) if len(df) else 0.0
        else:
            valid_count = 0
            valid_ratio = 0.0
        rows.append({
            "variable": key,
            "tag": col,
            "exists": exists,
            "valid_count": int(valid_count),
            "valid_ratio": valid_ratio,
            "can_use": exists and valid_ratio > 0.95,
        })
    return pd.DataFrame(rows)


def _get_series(df: pd.DataFrame, tag: str, name: str) -> pd.Series:
    if tag not in df.columns:
        raise KeyError(f"缺少测点 {name}: {tag}")
    return pd.to_numeric(df[tag], errors="coerce")


def compute_material_balance(
    df: pd.DataFrame,
    coeffs: BalanceCoefficients,
    tag_mapping: Dict[str, str] = DEFAULT_TAG_MAPPING,
    turbine_source: str = "TURBINE_FIC1",
    use_temp_correction: bool = True,
    allowed_percent: float = 0.0125,
) -> pd.DataFrame:
    """
    计算外压缩物料平衡模型。

    参数：
    - turbine_source:
        "TURBINE_FIC1"  = 使用膨胀空气进上塔流量 FIC1_1
        "TURBINE_FI105" = 使用膨胀机增压端空气流量 FI105
    - use_temp_correction:
        True  = 使用 TEMP - TEMPBase 修正项；
        False = 温度修正项置 0，适用于 TEMP 测点无效时的临时验证。
    - allowed_percent:
        合理波动范围，初版可用 ±1.25%。

    返回：
    原始 timestamp + 输入变量 + 模型输出 + 实测值 + 残差 + 语义判断。
    """
    if turbine_source not in ("TURBINE_FIC1", "TURBINE_FI105"):
        raise ValueError("turbine_source 只能是 TURBINE_FIC1 或 TURBINE_FI105")

    GOX = _get_series(df, tag_mapping["GOX"], "GOX 产品氧气流量")
    GAN_meas = _get_series(df, tag_mapping["GAN"], "GAN 产品氮气流量")
    LIN = _get_series(df, tag_mapping["LIN"], "LIN 液氮流量")
    GAR = _get_series(df, tag_mapping["GAR"], "GAR 中压氮气去用户流量")
    TURBINE = _get_series(df, tag_mapping[turbine_source], "TURBINE 膨胀机相关空气流量")

    if use_temp_correction:
        TEMP = _get_series(df, tag_mapping["TEMP"], "TEMP 原料空气入口温度")
        temp_delta = TEMP - coeffs.TEMPBase
    else:
        TEMP = pd.Series(np.nan, index=df.index)
        temp_delta = 0.0

    turbine_delta = TURBINE - coeffs.TURBBase

    # ① 等效全液氧工况的氧气产量
    EGOX = GOX - (125.0 / 136.0) * LIN + (114.0 / 136.0) * (GAR - coeffs.GARBase)

    # ② 进塔分离空气流量
    PAIR = (
        coeffs.AIRCoef1 * EGOX
        + coeffs.AIRCoef2
        + coeffs.AIRCoef3 * temp_delta
        + coeffs.AIRCoef4 * turbine_delta
    )

    # ③ 总氮：GAN + LIN
    GAN_LIN_MODEL = (
        coeffs.GANCoef1 * EGOX
        + coeffs.GANCoef2
        + coeffs.GANCoef3 * temp_delta
        + coeffs.GANCoef4 * turbine_delta
    )

    # ④ 膨胀空气旁通量 / 膨胀空气相关量
    TURBBY = (
        coeffs.TURBCoef1 * EGOX
        + coeffs.TURBCoef2
        + coeffs.TURBCoef3 * turbine_delta
    )

    # ⑤ 氩馏分流量
    FAR = coeffs.FARCoef1 * PAIR + coeffs.FARCoef2

    # ⑥ 粗氩流量
    CAR = coeffs.CARCoef1 * PAIR + coeffs.CARCoef2

    # ⑦ 粗氩冷凝器液位
    LEV = coeffs.LEVCoef1 * PAIR + coeffs.LEVCoef2

    # ⑧ 总空气流量
    AIR = PAIR + TURBBY

    AIR_meas = _get_series(df, tag_mapping["AIR_MEAS"], "AIR 实测总空气流量")
    FAR_meas = _get_series(df, tag_mapping["FAR_MEAS"], "FAR 实测氩馏分流量")
    CAR_meas = _get_series(df, tag_mapping["CAR_MEAS"], "CAR 实测粗氩流量")
    LEV_meas = _get_series(df, tag_mapping["LEV_MEAS"], "LEV 实测粗氩冷凝器液位")

    result = pd.DataFrame({
        "timestamp": df["timestamp"] if "timestamp" in df.columns else pd.NaT,
        "GOX": GOX,
        "GAN_measured": GAN_meas,
        "LIN": LIN,
        "GAR": GAR,
        "TEMP": TEMP,
        "TURBINE": TURBINE,
        "EGOX_model": EGOX,
        "PAIR_model": PAIR,
        "GAN_LIN_model": GAN_LIN_MODEL,
        "TURBBY_model": TURBBY,
        "FAR_model": FAR,
        "CAR_model": CAR,
        "LEV_model": LEV,
        "AIR_model": AIR,
        "AIR_measured": AIR_meas,
        "FAR_measured": FAR_meas,
        "CAR_measured": CAR_meas,
        "LEV_measured": LEV_meas,
    })

    # 残差与偏离百分比
    for var in ["AIR", "FAR", "CAR", "LEV"]:
        model_col = f"{var}_model"
        meas_col = f"{var}_measured"
        residual_col = f"{var}_residual"
        dev_col = f"{var}_deviation_percent"
        semantic_col = f"{var}_semantic"

        result[residual_col] = result[meas_col] - result[model_col]
        result[dev_col] = result[residual_col] / result[model_col].replace(0, np.nan)

        result[semantic_col] = np.select(
            [
                result[dev_col] > allowed_percent,
                result[dev_col] < -allowed_percent,
            ],
            ["偏高", "偏低"],
            default="正常",
        )

    return result


def build_config_template(path: str | Path) -> None:
    """
    生成待填写的物料平衡系数模板。
    """
    data = {k: None for k in BalanceCoefficients.__dataclass_fields__}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_window(result: pd.DataFrame) -> pd.DataFrame:
    """
    对一个事件窗口的物料平衡结果做汇总。
    """
    rows = []
    for var in ["AIR", "FAR", "CAR", "LEV"]:
        rows.append({
            "variable": var,
            "model_mean": result[f"{var}_model"].mean(),
            "measured_mean": result[f"{var}_measured"].mean(),
            "residual_mean": result[f"{var}_residual"].mean(),
            "deviation_percent_mean": result[f"{var}_deviation_percent"].mean(),
            "semantic_mode": result[f"{var}_semantic"].mode().iloc[0] if not result[f"{var}_semantic"].mode().empty else None,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # 示例：
    # 1. 先生成系数模板：
    # build_config_template("material_balance_config_template.json")
    #
    # 2. 检查数据能否支持：
    # df = load_wide_table("衢州杭氧1#42000数据.csv")
    # print(check_required_columns(df))
    #
    # 3. 填好 config 后再计算：
    # coeffs = BalanceCoefficients.from_json("material_balance_config.json")
    # df_1min = resample_1min(df)
    # out = compute_material_balance(df_1min, coeffs, use_temp_correction=False)
    # out.to_csv("material_balance_result.csv", index=False, encoding="utf-8-sig")
    build_config_template("material_balance_config_template.json")
    print("已生成 material_balance_config_template.json，请先填写系数和基准值。")
