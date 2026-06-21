"""
ASU (Air Separation Unit) Time-series Pipeline Service

This module provides functionality for:
- Reading ASU Excel data with data dictionary mapping
- Computing derived metrics from raw sensor data
- Quality control and flagging for computed metrics
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import yaml
import os


@dataclass
class ReadResult:
    facts: pd.DataFrame
    meta: pd.DataFrame


@dataclass
class DerivedResult:
    derived: pd.DataFrame
    quality: Dict


class ASUExcelReader:
    def __init__(self, sheet_name=0, timezone: Optional[str]=None):
        self.sheet_name = sheet_name
        self.timezone = timezone

    def read(self, path: str, data_dictionary_csv: str) -> ReadResult:
        raw = pd.read_excel(path, sheet_name=self.sheet_name, header=None)

        tag_codes = raw.iloc[0, 1:].astype(str).tolist()
        tag_names = raw.iloc[1, 1:].astype(str).tolist()

        meta = pd.read_csv(data_dictionary_csv)
        if set(tag_codes) - set(meta["tag_code"].astype(str)):
            missing = sorted(list(set(tag_codes) - set(meta["tag_code"].astype(str))))
            raise ValueError(f"data_dictionary.csv missing tag_code(s): {missing[:5]} ... total={len(missing)}")

        df = raw.iloc[2:, :].copy()
        df.columns = ["time"] + tag_codes
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"])

        facts = df.melt(id_vars=["time"], var_name="tag_code", value_name="value")
        facts["value"] = pd.to_numeric(facts["value"], errors="coerce")
        facts = facts.dropna(subset=["value"])

        facts = facts.merge(meta[["tag_code", "unified_field", "tag_name_cn", "unit", "kpi_role"]],
                            on="tag_code", how="left")

        return ReadResult(facts=facts, meta=meta)


class DerivedMetricsEngine:
    def __init__(self, derived_yaml: str):
        with open(derived_yaml, "r", encoding="utf-8") as f:
            self.spec = yaml.safe_load(f)

    def compute(self, facts: pd.DataFrame) -> DerivedResult:
        wide = facts.pivot_table(index="time", columns="unified_field", values="value", aggfunc="last").sort_index()

        derived_series = {}
        flags = {}

        def add_flag(metric_code: str, mask: pd.Series, flag: str):
            if mask is None or not mask.any():
                return
            flags.setdefault(metric_code, {})
            for t in mask[mask].index:
                flags[metric_code].setdefault(t, []).append(flag)

        if {"Pump1_Loss_kW", "Pump2_Loss_kW"}.issubset(wide.columns):
            s = wide["Pump1_Loss_kW"] + wide["Pump2_Loss_kW"]
            derived_series["Pump_Loss_kW"] = s

        if {"ExpA_Cold_kW", "ExpB_Cold_kW"}.issubset(wide.columns):
            s = wide["ExpA_Cold_kW"] + wide["ExpB_Cold_kW"]
            derived_series["ExpanderCold_kW"] = s

        needed = {"HX_Loss_kW", "ColdBox_Loss_kW", "Pump_Loss_kW"}
        if needed.issubset(set(list(wide.columns)) | set(derived_series.keys())):
            hx = wide.get("HX_Loss_kW")
            cb = wide.get("ColdBox_Loss_kW")
            pump = derived_series.get("Pump_Loss_kW")
            s = hx + cb + pump
            derived_series["TotalColdLoss_kW"] = s

        eps = float(self.spec.get("metrics", [])[-1].get("quality", {}).get("eps", 1e-6))
        if {"TotalColdLoss_kW", "ExpanderCold_kW"}.issubset(derived_series.keys()):
            num = derived_series["TotalColdLoss_kW"]
            denom = derived_series["ExpanderCold_kW"]
            div0 = denom.abs() <= eps
            add_flag("ColdLossRatio", div0, "DIV0")
            ratio = num / denom.where(~div0, np.nan)
            derived_series["ColdLossRatio"] = ratio

        out = (
            pd.DataFrame(derived_series)
            .reset_index()
            .melt(id_vars=["time"], var_name="metric_code", value_name="value")
            .dropna(subset=["value"])
            .sort_values(["time", "metric_code"])
        )

        if flags:
            flag_rows = []
            for metric_code, by_time in flags.items():
                for t, fl in by_time.items():
                    flag_rows.append({"time": t, "metric_code": metric_code, "quality_flags": "|".join(sorted(set(fl)))})
            flag_df = pd.DataFrame(flag_rows)
            out = out.merge(flag_df, on=["time", "metric_code"], how="left")
        else:
            out["quality_flags"] = np.nan

        quality = {
            "n_points": int(out.shape[0]),
            "metrics": sorted(out["metric_code"].unique().tolist()),
        }
        return DerivedResult(derived=out, quality=quality)


class ASUPipelineService:
    def __init__(self, derived_yaml: Optional[str] = None):
        if derived_yaml is None:
            # 修改为指向 config 目录
            # src/services/asu_pipeline.py -> src/services -> src -> demo2opt -> config
            derived_yaml = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "derived_metrics.yaml")
        self.derived_yaml = derived_yaml
        self.reader = ASUExcelReader()
        self.engine = DerivedMetricsEngine(derived_yaml)

    def load_and_process(self, excel_path: str, data_dictionary_csv: Optional[str] = None) -> Dict:
        if data_dictionary_csv is None:
            # src/services/asu_pipeline.py -> src/services -> src -> demo2opt -> data
            data_dictionary_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "data_dictionary.csv")

        read_result = self.reader.read(excel_path, data_dictionary_csv)
        derived_result = self.engine.compute(read_result.facts)

        return {
            "facts": read_result.facts,
            "meta": read_result.meta,
            "derived": derived_result.derived,
            "quality": derived_result.quality
        }

    def get_available_metrics(self) -> List[str]:
        with open(self.derived_yaml, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        return [m["metric_code"] for m in spec.get("metrics", [])]

    def get_metric_info(self, metric_code: str) -> Optional[Dict]:
        with open(self.derived_yaml, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        for m in spec.get("metrics", []):
            if m["metric_code"] == metric_code:
                return m
        return None
