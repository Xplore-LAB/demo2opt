import asyncio
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.prompts.templates import build_semantic_ai_review_prompts
from src.schemas.models import ASUDerivedResultModel, CoreIndicatorsModel, validate_semantic_data
from src.utils.business_logic import is_abnormal_state
from src.utils.llm_json import extract_json_object, repair_llm_text
from src.utils.logger import get_logger, setup_logger

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


INDICATOR_PROFILES: Dict[str, Dict[str, Any]] = {
    "HY_2030_1#ZB_1_Cooling_MainHeatExchanger_1": {"objective": "minimize", "industry_benchmark": 70.0},
    "HY_2030_1#ZB_1_Cooling_Expander_2": {
        "objective": "maximize",
        "industry_benchmark": 380.0,
        "standby_pair": {
            "pair_tag": "HY_2030_1#ZB_1_Cooling_Expander_6",
            "self_idle_threshold": 15.0,
            "pair_active_threshold": 260.0,
        },
    },
    "HY_2030_1#ZB_1_Cooling_Expander_6": {
        "objective": "maximize",
        "industry_benchmark": 360.0,
        "standby_pair": {
            "pair_tag": "HY_2030_1#ZB_1_Cooling_Expander_2",
            "self_idle_threshold": 15.0,
            "pair_active_threshold": 260.0,
        },
    },
    "HY_2030_1#ZB_1_Energy_AirCompress_8": {
        "objective": "range",
        "industry_range": {"min": 88.0, "max": 100.0, "target": 94.0},
    },
}

DEFAULT_MEMBERSHIP_WEIGHTS = {
    "优秀": 1.0,
    "良好": 0.9,
    "一般": 0.7,
    "较差": 0.35,
    "差": 0.2,
    "偏高": 0.15,
    "偏低": 0.15,
    "异常": 0.12,
    "偏差较大": 0.1,
    "偏离显著": 0.05,
    "严重偏高": 0.0,
    "严重偏低": 0.0,
    "正常": 0.85,
    "待机备用": 0.88,
    "Unknown": 0.0,
}

DEFAULT_SEVERITY_CONFIG = {
    "level_scores": {"严重偏高": 1.0, "严重偏低": 1.0, "偏离显著": 0.95, "异常": 0.9, "差": 0.88, "偏差较大": 0.82, "偏高": 0.72, "偏低": 0.72, "较差": 0.68},
    "base_score": 0.6,
    "diff_weight": 0.35,
    "duration_weight": 0.04,
    "duration_cap": 0.2,
}

DEFAULT_EXPANDER_IDLE_THRESHOLD = 10.0
DEFAULT_SEMANTICS_CONFIG_PATH = str(Path("config") / "indicators.yaml")
DEFAULT_RULE_REGISTRY_PATH = str(Path("config") / "semantic_rule_registry.yaml")
DEFAULT_HISTORY_MODEL_CONFIG_PATH = str(Path("config") / "history_model.yaml")
DEFAULT_HISTORY_MODEL_CONFIG = {
    "anchor_tag": "HY_2030_1#ZB_1_Energy_AirCompress_8",
    "regime_quantiles": {"low_max": 0.33, "high_min": 0.67},
    "parameters": {
        "min_samples_per_regime": 40,
        "min_samples_global": 90,
        "trend_short_window": 7,
        "trend_long_window": 30,
        "persistence_cap_points": 12,
        "robust_z_clip": 3.0,
        "fusion_weight": 0.25,
        "enter_exit_hysteresis": 0.05,
        "hybrid_aggregation_enabled": False,
    },
    "cache": {"path": str(Path("tmp") / "history_profiles.json")},
    "key_indicator_tags": list(INDICATOR_PROFILES.keys()),
}
DEFAULT_REFERENCE_PROVENANCE_FALLBACK = "未声明来源性质，仅按当前配置参考值执行；该参考值当前用于工程规则判级，不代表已完成统计标定。"
DEFAULT_RULE_ORIGIN_STATEMENT = "当前工程规则 / 初始标定，来源可追溯，尚未形成独立统计标定报告。"
RULE_REGISTRY_REQUIRED_KEYS = {
    "subsystem_state",
    "plant_state",
    "risk_level",
    "indicator_state",
    "severity_formula",
}
SUBSYSTEM_TAG_RULES = {
    "cold": ("cold", "cool", "expander", "膨胀", "冷", "换热"),
    "separation": ("column", "tower", "提取", "纯度", "氧", "氮", "氩", "分离"),
    "energy": ("energy", "compress", "power", "能耗", "电", "压缩"),
    "stability": ("pressure", "temperature", "flow", "level", "压", "温", "流量", "液位", "稳定"),
}


class DataSemanticsService:
    def __init__(self, design_specs_path: Optional[str] = None):
        setup_logger("demo2opt.semantics")
        self.logger = get_logger("demo2opt.semantics")
        self.specs: Dict[str, Dict[str, Any]] = {}
        self.indicator_profiles = dict(INDICATOR_PROFILES)
        self.membership_weights = dict(DEFAULT_MEMBERSHIP_WEIGHTS)
        self.expander_idle_threshold = float(DEFAULT_EXPANDER_IDLE_THRESHOLD)
        self.semantics_config_path = os.getenv("SEMANTICS_CONFIG_PATH", DEFAULT_SEMANTICS_CONFIG_PATH)
        self.rule_registry_path = os.getenv("SEMANTIC_RULE_REGISTRY_PATH", DEFAULT_RULE_REGISTRY_PATH)
        self.history_model_config_path = os.getenv("HISTORY_MODEL_CONFIG_PATH", DEFAULT_HISTORY_MODEL_CONFIG_PATH)
        self.rule_registry: Dict[str, Any] = {}
        self.rule_origin_statement = DEFAULT_RULE_ORIGIN_STATEMENT
        self.history_model_config: Dict[str, Any] = json.loads(json.dumps(DEFAULT_HISTORY_MODEL_CONFIG))
        self.history_model_params: Dict[str, Any] = dict(DEFAULT_HISTORY_MODEL_CONFIG["parameters"])
        self.history_model_cache_path = Path(DEFAULT_HISTORY_MODEL_CONFIG["cache"]["path"])
        self.severity_config = {
            "level_scores": {},
            "base_score": 0.6,
            "diff_weight": 0.35,
            "duration_weight": 0.04,
            "duration_cap": 0.2,
        }
        self._load_external_semantics_config()
        self._load_rule_registry()
        self._load_history_model_config()
        if design_specs_path:
            self.specs = self._load_json(design_specs_path)

    def _load_json(self, path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_external_semantics_config(self) -> None:
        path = Path(self.semantics_config_path)
        if not path.is_file() or yaml is None:
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = yaml.safe_load(f) or {}
        except Exception:
            return
        if isinstance(payload.get("indicator_profiles"), dict):
            self.indicator_profiles = payload["indicator_profiles"] or self.indicator_profiles
        weights = payload.get("membership", {}).get("state_weights")
        if isinstance(weights, dict):
            self.membership_weights.update(weights)
        idle = payload.get("expander", {}).get("idle_threshold")
        if isinstance(idle, (int, float)):
            self.expander_idle_threshold = float(idle)

    def _load_yaml_file(self, path: Path) -> Dict[str, Any]:
        if yaml is None:
            raise ValueError("PyYAML is required to load semantics configuration.")
        if not path.is_file():
            raise ValueError(f"Required config file is missing: {path}")
        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid YAML payload in {path}")
        return payload

    def _load_rule_registry(self) -> None:
        payload = self._load_yaml_file(Path(self.rule_registry_path))
        rules = payload.get("rules")
        if not isinstance(rules, dict):
            raise ValueError("semantic_rule_registry.yaml must define a top-level rules mapping.")
        missing = sorted(RULE_REGISTRY_REQUIRED_KEYS - set(rules.keys()))
        if missing:
            raise ValueError(f"semantic_rule_registry.yaml is missing required rules: {', '.join(missing)}")
        for rule_key in RULE_REGISTRY_REQUIRED_KEYS:
            self._validate_rule_definition(rule_key, rules.get(rule_key))

        self.rule_registry = payload
        self.rule_origin_statement = str(payload.get("origin_statement") or DEFAULT_RULE_ORIGIN_STATEMENT)

        severity_rule = rules["severity_formula"]
        parameters = severity_rule.get("parameters") or {}
        level_scores = parameters.get("level_scores")
        if not isinstance(level_scores, dict):
            raise ValueError("severity_formula.parameters.level_scores must be a mapping.")
        for key in ("base_score", "diff_weight", "duration_weight", "duration_cap"):
            if not isinstance(parameters.get(key), (int, float)):
                raise ValueError(f"severity_formula.parameters.{key} must be numeric.")
        self.severity_config = {
            "level_scores": dict(level_scores),
            "base_score": float(parameters.get("base_score")),
            "diff_weight": float(parameters.get("diff_weight")),
            "duration_weight": float(parameters.get("duration_weight")),
            "duration_cap": float(parameters.get("duration_cap")),
        }

    def _load_history_model_config(self) -> None:
        path = Path(self.history_model_config_path)
        if not path.is_file() or yaml is None:
            return
        try:
            payload = self._load_yaml_file(path)
        except Exception:
            return

        merged = json.loads(json.dumps(DEFAULT_HISTORY_MODEL_CONFIG))
        if isinstance(payload.get("anchor_tag"), str) and payload.get("anchor_tag"):
            merged["anchor_tag"] = payload["anchor_tag"]
        if isinstance(payload.get("regime_quantiles"), dict):
            merged["regime_quantiles"].update(payload["regime_quantiles"])
        if isinstance(payload.get("parameters"), dict):
            merged["parameters"].update(payload["parameters"])
        if isinstance(payload.get("cache"), dict):
            merged["cache"].update(payload["cache"])
        if isinstance(payload.get("key_indicator_tags"), list):
            merged["key_indicator_tags"] = [str(item) for item in payload["key_indicator_tags"] if str(item).strip()]

        self.history_model_config = merged
        self.history_model_params = dict(merged.get("parameters") or {})
        self.history_model_cache_path = Path(str((merged.get("cache") or {}).get("path") or DEFAULT_HISTORY_MODEL_CONFIG["cache"]["path"]))

    def _validate_rule_definition(self, rule_key: str, rule_value: Any) -> None:
        if not isinstance(rule_value, dict):
            raise ValueError(f"Rule '{rule_key}' must be a mapping.")
        for required_key in (
            "rule_name",
            "rule_version",
            "origin_type",
            "origin_note",
            "validation_status",
            "applicability",
            "parameters",
        ):
            if required_key not in rule_value:
                raise ValueError(f"Rule '{rule_key}' is missing required field '{required_key}'.")
        if not isinstance(rule_value.get("parameters"), dict):
            raise ValueError(f"Rule '{rule_key}' parameters must be a mapping.")

    def _rule_definition(self, rule_key: str) -> Dict[str, Any]:
        rules = self.rule_registry.get("rules") or {}
        rule = rules.get(rule_key)
        if not isinstance(rule, dict):
            raise ValueError(f"Rule '{rule_key}' is not configured.")
        return rule

    def _rule_parameters(self, rule_key: str) -> Dict[str, Any]:
        params = self._rule_definition(rule_key).get("parameters")
        if not isinstance(params, dict):
            raise ValueError(f"Rule '{rule_key}' parameters are invalid.")
        return params

    def _safe_number(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _basis_kind_label(self, value: Any) -> str:
        return {
            "design_value": "设计值",
            "operation_target": "运行目标值",
            "simulation_rated": "仿真额定值",
            "expert_config": "专家初始化配置值",
        }.get(str(value or "").strip(), "未声明来源性质")

    def _validation_status_label(self, value: Any) -> str:
        return {
            "traceable_unvalidated": "来源可追溯，尚未形成独立统计标定报告",
            "expert_initialized": "专家初始化，尚未形成独立统计标定报告",
            "simulation_aligned": "与仿真额定值对齐，尚未形成独立统计标定报告",
            "historically_calibrated": "历史标定口径，当前仓库未附独立标定报告",
        }.get(str(value or "").strip(), "来源可追溯，尚未形成独立统计标定报告")

    def _provenance_fallback_text(self) -> str:
        return DEFAULT_REFERENCE_PROVENANCE_FALLBACK

    def _sanitize_hypothesis_text(self, value: Any) -> str:
        text = str(repair_llm_text(value or "")).strip()
        if not text:
            return ""
        replacements = [
            ("已确认根因", "待核查假设"),
            ("根因已锁定", "疑似根因链待现场确认"),
            ("已锁定根因", "疑似根因链待现场确认"),
            ("核心根因", "主导异常"),
            ("锁定根因链起点", "疑似根因链起点"),
            ("锁定根因", "收敛到疑似根因链"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    def _percentile(self, values: List[float], q: float) -> Optional[float]:
        vals = sorted(v for v in values if v is not None)
        if not vals:
            return None
        if len(vals) == 1:
            return vals[0]
        pos = (len(vals) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(vals) - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)

    def _percentile_rank(self, value: Optional[float], ordered_values: List[float]) -> Optional[float]:
        if value is None:
            return None
        vals = sorted(v for v in ordered_values if v is not None)
        if not vals:
            return None
        count = sum(1 for item in vals if item <= value)
        return count / len(vals)

    def _group_history_values(self, history_data: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        grouped: Dict[str, List[float]] = {}
        for row in history_data or []:
            tag = str(row.get("tag_id") or "").strip()
            value = self._safe_number(row.get("value"))
            if tag and value is not None:
                grouped.setdefault(tag, []).append(value)
        return grouped

    def _feature_map(self, features: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not isinstance(features, dict):
            return {}
        per_tag = features.get("per_tag")
        if isinstance(per_tag, dict):
            return per_tag
        return features

    def _history_signature(self, history_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        timestamps = sorted(str(row.get("timestamp") or "") for row in history_data or [] if row.get("timestamp"))
        tags = sorted({str(row.get("tag_id") or "").strip() for row in history_data or [] if row.get("tag_id")})
        return {
            "record_count": len(history_data or []),
            "tag_count": len(tags),
            "min_timestamp": timestamps[0] if timestamps else None,
            "max_timestamp": timestamps[-1] if timestamps else None,
        }

    def _load_history_profile_cache(self, history_signature: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        path = self.history_model_cache_path
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        cached_signature = payload.get("signature") if isinstance(payload.get("signature"), dict) else {}
        baseline_profile = payload.get("baseline_profile") if isinstance(payload.get("baseline_profile"), dict) else payload
        if not isinstance(baseline_profile, dict) or cached_signature != history_signature:
            return None
        metadata = dict(baseline_profile.get("history_model_metadata") or {})
        metadata["profile_source"] = "cache"
        metadata["cache_path"] = str(path)
        metadata["signature"] = history_signature
        baseline_profile["history_model_metadata"] = metadata
        return baseline_profile

    def _history_rows_by_tag(self, history_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in history_data or []:
            tag = str(row.get("tag_id") or "").strip()
            if tag:
                grouped.setdefault(tag, []).append(row)
        for rows in grouped.values():
            rows.sort(key=lambda item: str(item.get("timestamp") or ""))
        return grouped

    def _history_values_by_time(self, history_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        values_by_time: Dict[str, Dict[str, float]] = {}
        for row in history_data or []:
            timestamp = str(row.get("timestamp") or "")
            tag = str(row.get("tag_id") or "").strip()
            value = self._safe_number(row.get("value"))
            if timestamp and tag and value is not None:
                values_by_time.setdefault(timestamp, {})[tag] = value
        return values_by_time

    def _stats_from_values(self, values: List[float]) -> Dict[str, Optional[float]]:
        vals = [value for value in values if value is not None]
        if not vals:
            return {
                "mean": None,
                "std": None,
                "min": None,
                "max": None,
                "p10": None,
                "median": None,
                "p90": None,
                "mad": None,
                "iqr": None,
            }
        mean = sum(vals) / len(vals)
        variance = sum((value - mean) ** 2 for value in vals) / len(vals)
        median = self._percentile(vals, 0.5)
        q1 = self._percentile(vals, 0.25)
        q3 = self._percentile(vals, 0.75)
        mad = None
        if median is not None:
            abs_dev = [abs(value - median) for value in vals]
            mad = self._percentile(abs_dev, 0.5)
        return {
            "mean": mean,
            "std": math.sqrt(max(variance, 0.0)),
            "min": min(vals),
            "max": max(vals),
            "p10": self._percentile(vals, 0.1),
            "median": median,
            "p90": self._percentile(vals, 0.9),
            "mad": mad,
            "iqr": (q3 - q1) if q1 is not None and q3 is not None else None,
        }

    def _regime_for_anchor_value(self, value: Optional[float], cut_points: Dict[str, Optional[float]]) -> str:
        if value is None:
            return "global"
        low_cut = self._safe_number(cut_points.get("low_max"))
        high_cut = self._safe_number(cut_points.get("high_min"))
        if low_cut is not None and value <= low_cut:
            return "low"
        if high_cut is not None and value >= high_cut:
            return "high"
        return "nominal"

    def _is_active_profile_row(
        self,
        *,
        tag: str,
        timestamp: str,
        value: Optional[float],
        values_by_time: Dict[str, Dict[str, float]],
    ) -> Tuple[bool, Optional[str]]:
        if value is None:
            return False, "missing_value"
        profile = self._get_indicator_profile(tag, "") or {}
        standby_pair = profile.get("standby_pair") or {}
        if not isinstance(standby_pair, dict) or not standby_pair:
            return True, None

        self_idle_threshold = self._safe_number(standby_pair.get("self_idle_threshold"))
        pair_active_threshold = self._safe_number(standby_pair.get("pair_active_threshold"))
        pair_tag = str(standby_pair.get("pair_tag") or "").strip()
        if value <= float(self_idle_threshold if self_idle_threshold is not None else self.expander_idle_threshold):
            return False, "standby_self_idle"

        pair_value = self._safe_number((values_by_time.get(timestamp) or {}).get(pair_tag))
        if (
            pair_tag
            and pair_value is not None
            and pair_active_threshold is not None
            and pair_value >= pair_active_threshold
            and pair_value > value
        ):
            return False, "standby_pair_dominant"
        return True, None

    def _infer_standby_pair_name(self, current_name: Any, pair_tag: str) -> str:
        text = str(current_name or "").strip()
        if "膨胀机A" in text:
            return text.replace("膨胀机A", "膨胀机B")
        if "膨胀机B" in text:
            return text.replace("膨胀机B", "膨胀机A")
        return pair_tag or "对偶设备"

    def _standby_suppression_context(
        self,
        *,
        tag_id: str,
        name: Any,
        value: Optional[float],
        realtime_context: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        profile = self._get_indicator_profile(tag_id or "", str(name or "")) or {}
        standby_pair = profile.get("standby_pair") or {}
        if not isinstance(standby_pair, dict) or not standby_pair:
            return {}

        pair_tag = str(standby_pair.get("pair_tag") or "").strip()
        self_idle_threshold = self._safe_number(standby_pair.get("self_idle_threshold"))
        pair_active_threshold = self._safe_number(standby_pair.get("pair_active_threshold"))
        pair_value = self._safe_number((realtime_context or {}).get(pair_tag)) if pair_tag else None
        idle_threshold = float(self_idle_threshold if self_idle_threshold is not None else self.expander_idle_threshold)
        active_threshold = float(pair_active_threshold if pair_active_threshold is not None else 0.0)
        current_value = self._safe_number(value)
        if current_value is None:
            return {}

        standby_reason = ""
        if current_value <= idle_threshold:
            standby_reason = "standby_self_idle"
        elif pair_tag and pair_value is not None and pair_value >= active_threshold and pair_value > current_value:
            standby_reason = "standby_pair_dominant"
        if not standby_reason:
            return {}

        pair_name = self._infer_standby_pair_name(name, pair_tag)
        if standby_reason == "standby_self_idle":
            summary = f"{str(name or tag_id)} 当前值低于待机阈值 {idle_threshold:.1f}，按备用机待机口径处理。"
        else:
            summary = (
                f"{pair_name} 当前制冷量 {self._format_number_text(pair_value)} 已达到主运行阈值，"
                f"{str(name or tag_id)} 按一备一用工况视作备用机待机。"
            )

        return {
            "is_standby_suppressed": True,
            "reason": standby_reason,
            "pair_tag": pair_tag,
            "pair_name": pair_name,
            "pair_value": pair_value,
            "self_idle_threshold": idle_threshold,
            "pair_active_threshold": active_threshold if pair_tag else None,
            "summary": summary,
        }

    def _window_slope(self, values: List[float], window_size: int) -> float:
        if not values:
            return 0.0
        window = values[-max(2, min(window_size, len(values))):]
        n = len(window)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(window) / n
        denominator = sum((index - x_mean) ** 2 for index in range(n))
        if denominator <= 1e-9:
            return 0.0
        numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(window))
        return numerator / denominator

    def _ewma_last(self, values: List[float], window_size: int) -> float:
        if not values:
            return 0.0
        alpha = 2.0 / (max(window_size, 1) + 1.0)
        ewma = values[0]
        for value in values[1:]:
            ewma = alpha * value + (1.0 - alpha) * ewma
        return ewma

    def _detect_change_point(self, values: List[float], min_window: int) -> Optional[int]:
        if len(values) < max(min_window * 2, 6):
            return None
        best_index = None
        best_gap = -1.0
        for split in range(min_window, len(values) - min_window + 1):
            left = values[:split]
            right = values[split:]
            if not left or not right:
                continue
            gap = abs((sum(left) / len(left)) - (sum(right) / len(right)))
            if gap > best_gap:
                best_gap = gap
                best_index = split - 1
        return best_index

    def _trend_from_slopes(self, slope_short: float, slope_long: float, std_value: Optional[float]) -> str:
        tolerance = max(abs(self._safe_number(std_value) or 0.0) * 0.05, 1e-6)
        if abs(slope_short) <= tolerance and abs(slope_long) <= tolerance:
            return "stable"
        if slope_short >= tolerance and slope_long >= -tolerance:
            return "increasing"
        if slope_short <= -tolerance and slope_long <= tolerance:
            return "decreasing"
        return "volatile"

    def _is_bad_side_value(
        self,
        *,
        objective: str,
        value: Optional[float],
        baseline_value: Optional[float],
        low: Optional[float],
        high: Optional[float],
        hysteresis: float,
    ) -> bool:
        if value is None:
            return False
        baseline = self._safe_number(baseline_value)
        if objective == "maximize":
            threshold = baseline * (1.0 - hysteresis) if baseline is not None else baseline
            return baseline is not None and value < threshold
        if objective == "minimize":
            threshold = baseline * (1.0 + hysteresis) if baseline is not None else baseline
            return baseline is not None and value > threshold
        low_bound = self._safe_number(low)
        high_bound = self._safe_number(high)
        if low_bound is not None and value < low_bound * (1.0 - hysteresis):
            return True
        if high_bound is not None and value > high_bound * (1.0 + hysteresis):
            return True
        if baseline is not None:
            tolerance = max(abs(baseline) * hysteresis, 1e-6)
            return abs(value - baseline) > tolerance
        return False

    def _series_run_length(
        self,
        values: List[float],
        *,
        objective: str,
        baseline_value: Optional[float],
        low: Optional[float],
        high: Optional[float],
    ) -> int:
        hysteresis = float(self.history_model_params.get("enter_exit_hysteresis", 0.05))
        run_length = 0
        for value in reversed(values):
            if self._is_bad_side_value(
                objective=objective,
                value=value,
                baseline_value=baseline_value,
                low=low,
                high=high,
                hysteresis=hysteresis,
            ):
                run_length += 1
            else:
                break
        return run_length

    def _directed_tail_score(
        self,
        *,
        current_value: Optional[float],
        objective: str,
        baseline_row: Dict[str, Any],
        low: Optional[float],
        high: Optional[float],
    ) -> float:
        current = self._safe_number(current_value)
        median = self._safe_number(baseline_row.get("median") if baseline_row.get("median") is not None else baseline_row.get("baseline_value"))
        p10 = self._safe_number(baseline_row.get("p10"))
        p90 = self._safe_number(baseline_row.get("p90"))
        iqr = max(abs(self._safe_number(baseline_row.get("iqr")) or 0.0), 1e-6)
        if current is None:
            return 0.0
        if objective == "maximize":
            if median is None or current >= median:
                return 0.0
            floor = p10 if p10 is not None else median - iqr
            if current <= floor:
                return 1.0
            return max(0.0, min(1.0, (median - current) / max(median - floor, 1e-6)))
        if objective == "minimize":
            if median is None or current <= median:
                return 0.0
            ceiling = p90 if p90 is not None else median + iqr
            if current >= ceiling:
                return 1.0
            return max(0.0, min(1.0, (current - median) / max(ceiling - median, 1e-6)))
        low_bound = self._safe_number(low)
        high_bound = self._safe_number(high)
        if low_bound is not None and current < low_bound:
            return max(0.0, min(1.0, (low_bound - current) / iqr))
        if high_bound is not None and current > high_bound:
            return max(0.0, min(1.0, (current - high_bound) / iqr))
        if median is None:
            return 0.0
        return max(0.0, min(1.0, abs(current - median) / iqr))

    def _robust_z_score(self, current_value: Optional[float], baseline_row: Dict[str, Any]) -> float:
        current = self._safe_number(current_value)
        median = self._safe_number(baseline_row.get("median"))
        mad = self._safe_number(baseline_row.get("mad"))
        mean = self._safe_number(baseline_row.get("mean"))
        std = self._safe_number(baseline_row.get("std"))
        if current is None:
            return 0.0
        if median is not None and mad is not None and mad > 1e-6:
            return 0.6745 * (current - median) / mad
        if mean is not None and std is not None and std > 1e-6:
            return (current - mean) / std
        return 0.0

    def _statistical_state(self, anomaly_score: float) -> str:
        if anomaly_score >= 0.7:
            return "high"
        if anomaly_score >= 0.4:
            return "warning"
        return "normal"

    def _statistical_direction(
        self,
        *,
        objective: str,
        current_value: Optional[float],
        baseline_row: Dict[str, Any],
        low: Optional[float],
        high: Optional[float],
    ) -> str:
        current = self._safe_number(current_value)
        median = self._safe_number(baseline_row.get("median") if baseline_row.get("median") is not None else baseline_row.get("baseline_value"))
        if current is None:
            return "normal"
        if objective == "maximize":
            return "low" if median is not None and current < median else "normal"
        if objective == "minimize":
            return "high" if median is not None and current > median else "normal"
        low_bound = self._safe_number(low)
        high_bound = self._safe_number(high)
        if low_bound is not None and current < low_bound:
            return "low"
        if high_bound is not None and current > high_bound:
            return "high"
        return "normal"

    def _rule_direction(
        self,
        *,
        rule_state: str,
        objective: str,
        current_value: Optional[float],
        low: Optional[float],
        high: Optional[float],
    ) -> str:
        if not self._is_abnormal_state(rule_state):
            return "normal"
        if objective == "maximize":
            return "low"
        if objective == "minimize":
            return "high"
        current = self._safe_number(current_value)
        low_bound = self._safe_number(low)
        high_bound = self._safe_number(high)
        if current is not None and low_bound is not None and current < low_bound:
            return "low"
        if current is not None and high_bound is not None and current > high_bound:
            return "high"
        return "outside"

    def _agreement_flag(
        self,
        *,
        rule_state: str,
        objective: str,
        current_value: Optional[float],
        low: Optional[float],
        high: Optional[float],
        statistical_state: str,
        statistical_direction: str,
    ) -> str:
        rule_abnormal = self._is_abnormal_state(rule_state)
        history_abnormal = statistical_state in {"warning", "high"}
        if rule_abnormal and history_abnormal:
            rule_direction = self._rule_direction(
                rule_state=rule_state,
                objective=objective,
                current_value=current_value,
                low=low,
                high=high,
            )
            if statistical_direction not in {"normal", rule_direction, "outside"} and rule_direction not in {"outside", statistical_direction}:
                return "conflict"
            return "agree"
        if rule_abnormal:
            return "rule_only"
        if history_abnormal:
            return "history_only"
        return "agree"

    def _risk_level_order(self) -> List[str]:
        return ["stable", "attention", "warning", "critical"]

    def _upgrade_status_level(self, current_level: str) -> str:
        order = self._risk_level_order()
        try:
            index = order.index(current_level)
        except ValueError:
            return current_level
        return order[min(index + 1, len(order) - 1)]

    def _state_to_membership(self, state_desc: str) -> float:
        return float(self.membership_weights.get(state_desc, 0.5))

    def _normalize_match_key(self, value: Any) -> str:
        return "".join(str(value or "").split()).lower()

    def _get_indicator_profile(self, tag_id: str, name: str = "") -> Optional[Dict[str, Any]]:
        return self.indicator_profiles.get(tag_id)

    def update_specs_from_csv_data(self, history_data: List[Dict[str, Any]]) -> None:
        grouped: Dict[str, List[float]] = {}
        for row in history_data or []:
            tag = row.get("tag_id")
            value = self._safe_number(row.get("value"))
            if tag and value is not None:
                grouped.setdefault(tag, []).append(value)
        self.specs = {
            tag: {"design": self._percentile(vals, 0.5) or vals[-1], "min": min(vals), "max": max(vals), "p10": self._percentile(vals, 0.1), "p90": self._percentile(vals, 0.9), "median": self._percentile(vals, 0.5)}
            for tag, vals in grouped.items()
            if vals
        }

    def _resolve_optimization_direction(self, objective: str, current_value: Optional[float], baseline_value: Optional[float]) -> str:
        if current_value is None or baseline_value is None:
            return "stabilize"
        if objective == "maximize":
            return "increase" if current_value < baseline_value else "stabilize"
        if objective == "minimize":
            return "decrease" if current_value > baseline_value else "stabilize"
        return "stabilize"

    def _standby_highlights(self, semantic_data: List[Dict[str, Any]]) -> List[str]:
        notes: List[str] = []
        for item in semantic_data or []:
            standby_context = item.get("standby_context") or {}
            if not isinstance(standby_context, dict) or not standby_context.get("is_standby_suppressed"):
                continue
            pair_name = str(standby_context.get("pair_name") or standby_context.get("pair_tag") or "对偶设备")
            current_name = str(item.get("name") or item.get("tag_id") or "当前指标")
            pair_value = self._format_number_text(standby_context.get("pair_value"))
            notes.append(
                f"{pair_name} 为当前主运行机，{current_name} 按一备一用工况视作待机备用；"
                f"{pair_name} 当前值={pair_value}，不将 {current_name} 低负荷直接判为主导异常。"
            )
        deduped: List[str] = []
        seen = set()
        for note in notes:
            if not note or note in seen:
                continue
            deduped.append(note)
            seen.add(note)
            if len(deduped) >= 3:
                break
        return deduped

    def _resolve_subsystem_name(self, tag_id: Any, name: Any) -> str:
        text = f"{str(tag_id or '').lower()} {str(name or '').lower()}"
        for token in SUBSYSTEM_TAG_RULES["cold"]:
            if token in text:
                return "冷量系统"
        for token in SUBSYSTEM_TAG_RULES["separation"]:
            if token in text:
                return "分离系统"
        for token in SUBSYSTEM_TAG_RULES["energy"]:
            if token in text:
                return "能耗系统"
        for token in SUBSYSTEM_TAG_RULES["stability"]:
            if token in text:
                return "稳定性系统"
        return "工艺通用系统"

    def _to_variable_semantics_label(self, state_desc: str, trend: str, diff_percent: Optional[float]) -> str:
        state_text = str(state_desc or "未知").strip() or "未知"
        trend_text = str(trend or "stable").strip() or "stable"
        if diff_percent is None:
            return f"{state_text}|趋势={trend_text}"
        return f"{state_text}|偏差={diff_percent:+.1f}%|趋势={trend_text}"

    def _subsystem_state_from_scores(self, abnormal_ratio: float, avg_severity: float) -> str:
        if abnormal_ratio <= 0.0:
            return "stable"
        params = self._rule_parameters("subsystem_state")
        constrained = params.get("constrained") or {}
        suboptimal = params.get("suboptimal") or {}
        if avg_severity >= float(constrained.get("avg_severity_gte")) or abnormal_ratio >= float(constrained.get("abnormal_ratio_gte")):
            return "constrained"
        if avg_severity >= float(suboptimal.get("avg_severity_gte")) or abnormal_ratio >= float(suboptimal.get("abnormal_ratio_gte")):
            return "suboptimal"
        return "attention"

    def _format_number_text(self, value: Any, digits: int = 2) -> str:
        number = self._safe_number(value)
        if number is None:
            return "-"
        text = f"{number:.{digits}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def _objective_label(self, objective: str) -> str:
        return {
            "maximize": "越高越好",
            "minimize": "越低越好",
            "range": "区间控制",
        }.get(str(objective or "range"), "区间控制")

    def _relative_diff_percent(self, current_value: Any, reference_value: Any) -> Optional[float]:
        current = self._safe_number(current_value)
        reference = self._safe_number(reference_value)
        if current is None or reference is None or abs(reference) <= 1e-6:
            return None
        return (current - reference) / abs(reference) * 100.0

    def _grade_basis_metadata(self, has_target_reference: bool) -> Dict[str, str]:
        if has_target_reference:
            return {
                "basis": "target_reference",
                "basis_label": "目标参考值",
                "basis_reason": "最终异常判级按目标参考值执行；历史基线仅用于判断是否偏离历史常态；优态基线仅用于衡量优化空间。",
            }
        return {
            "basis": "history_baseline",
            "basis_label": "历史运行基线",
            "basis_reason": "当前缺少目标参考值，异常判级临时退回到历史运行基线；优态基线仍仅用于衡量优化空间。",
        }

    def _build_reference_framework(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "目标参考值",
                "priority": 1,
                "purpose": "用于判断是否偏离设计/操作目标，并作为最终异常判级依据。",
                "drives_grading": True,
            },
            {
                "name": "历史运行基线",
                "priority": 2,
                "purpose": "用于判断当前值是否偏离装置历史常态，不直接决定异常级别。",
                "drives_grading": False,
            },
            {
                "name": "优态基线",
                "priority": 3,
                "purpose": "用于衡量距离较优工况还有多远，反映优化空间，不直接决定异常级别。",
                "drives_grading": False,
            },
        ]

    def _indicator_state_rule_trace(
        self,
        *,
        objective: str,
        diff_ratio: Optional[float],
        current_value: Optional[float],
        low: Optional[float],
        high: Optional[float],
    ) -> Dict[str, Any]:
        params = self._rule_parameters("indicator_state")
        if objective == "maximize":
            maximize = params.get("maximize") or {}
            thresholds = [
                ("优秀", float(maximize.get("excellent_gte")), ">=", None),
                ("良好", float(maximize.get("good_gte")), ">=", float(maximize.get("excellent_gte"))),
                ("一般", float(maximize.get("fair_gte")), ">=", float(maximize.get("good_gte"))),
                ("较差", float(maximize.get("poor_gte")), ">=", float(maximize.get("fair_gte"))),
                ("偏低", float(maximize.get("low_gte")), ">=", float(maximize.get("poor_gte"))),
            ]
            ratio = diff_ratio if diff_ratio is not None else 0.0
            for state, lower, operator, upper in thresholds:
                if ratio >= lower:
                    return {
                        "state": state,
                        "matched_interval": (
                            f"diff_ratio {operator} {lower:+.2f}"
                            if upper is None
                            else f"{lower:+.2f} <= diff_ratio < {upper:+.2f}"
                        ),
                        "thresholds": {
                            "objective": objective,
                            "lower_bound": lower,
                            "upper_bound": upper,
                        },
                    }
            return {
                "state": "严重偏低",
                "matched_interval": f"diff_ratio < {float(maximize.get('low_gte')):+.2f}",
                "thresholds": {
                    "objective": objective,
                    "upper_bound": float(maximize.get("low_gte")),
                },
            }

        if objective == "minimize":
            minimize = params.get("minimize") or {}
            thresholds = [
                ("优秀", float(minimize.get("excellent_lte")), "<=", None),
                ("良好", float(minimize.get("good_lte")), "<=", float(minimize.get("excellent_lte"))),
                ("一般", float(minimize.get("fair_lte")), "<=", float(minimize.get("good_lte"))),
                ("较差", float(minimize.get("poor_lte")), "<=", float(minimize.get("fair_lte"))),
                ("偏高", float(minimize.get("high_lte")), "<=", float(minimize.get("poor_lte"))),
            ]
            ratio = diff_ratio if diff_ratio is not None else 0.0
            for state, upper, operator, lower in thresholds:
                if ratio <= upper:
                    return {
                        "state": state,
                        "matched_interval": (
                            f"diff_ratio {operator} {upper:+.2f}"
                            if lower is None
                            else f"{lower:+.2f} < diff_ratio <= {upper:+.2f}"
                        ),
                        "thresholds": {
                            "objective": objective,
                            "lower_bound": lower,
                            "upper_bound": upper,
                        },
                    }
            return {
                "state": "严重偏高",
                "matched_interval": f"diff_ratio > {float(minimize.get('high_lte')):+.2f}",
                "thresholds": {
                    "objective": objective,
                    "lower_bound": float(minimize.get("high_lte")),
                },
            }

        range_params = params.get("range") or {}
        if low is not None and high is not None and current_value is not None and low <= current_value <= high:
            return {
                "state": str(range_params.get("inside_state") or "良好"),
                "matched_interval": f"{low:.2f} <= current_value <= {high:.2f}",
                "thresholds": {"objective": objective, "low": low, "high": high},
            }
        if low is not None and current_value is not None and current_value < low:
            return {
                "state": str(range_params.get("below_state") or "偏低"),
                "matched_interval": f"current_value < {low:.2f}",
                "thresholds": {"objective": objective, "low": low, "high": high},
            }
        return {
            "state": str(range_params.get("above_state") or "偏高"),
            "matched_interval": f"current_value > {high:.2f}" if high is not None else "current_value above target range",
            "thresholds": {"objective": objective, "low": low, "high": high},
        }

    def _calculate_severity_components(self, level: str, diff_percent: Optional[float], duration_points: int) -> Dict[str, Any]:
        ls = self.severity_config["level_scores"]
        level_score = float(ls.get(level, self.severity_config["base_score"]))
        diff_ratio = min(abs(diff_percent or 0.0) / 100.0, 1.0)
        diff_component = diff_ratio * float(self.severity_config["diff_weight"])
        raw_duration_component = max(duration_points - 1, 0) * float(self.severity_config["duration_weight"])
        duration_component = min(raw_duration_component, float(self.severity_config["duration_cap"]))
        return {
            "level_score": round(level_score, 4),
            "diff_component": round(diff_component, 4),
            "duration_component": round(duration_component, 4),
            "duration_component_raw": round(raw_duration_component, 4),
            "duration_cap": float(self.severity_config["duration_cap"]),
            "duration_cap_applied": raw_duration_component > float(self.severity_config["duration_cap"]),
            "severity_score": round(level_score + diff_component + duration_component, 4),
            "base_score_fallback": float(self.severity_config["base_score"]),
        }

    def _reference_source_metadata(
        self,
        profile: Optional[Dict[str, Any]],
        spec: Optional[Dict[str, Any]],
        fallback_value: Optional[float],
    ) -> Dict[str, Any]:
        profile = profile or {}
        spec = spec or {}
        configured_reference = self._safe_number(profile.get("reference_value"))
        benchmark = self._safe_number(profile.get("industry_benchmark"))
        range_target = self._safe_number(((profile.get("industry_range") or {}).get("target")))
        design_ref = self._safe_number(spec.get("design"))
        basis_kind = str(profile.get("reference_basis_kind") or "").strip()
        basis_text = str(profile.get("reference_basis_text") or "").strip()
        applicable_scope = str(profile.get("applicable_scope") or "当前装置指标配置").strip()
        applicable_conditions = str(profile.get("applicable_conditions") or "未声明").strip()
        reference_owner = str(profile.get("reference_owner") or "").strip()
        last_reviewed_at = str(profile.get("last_reviewed_at") or "").strip()
        validation_status = str(profile.get("validation_status") or "").strip()

        def _payload(
            *,
            label: str,
            value: Optional[float],
            source_label: str,
            source_type: str,
            scope: str,
            comparison_method: str,
            basis_kind_value: str,
            basis_text_value: str,
            conditions: str,
            owner: str,
            reviewed_at: str,
            validation: str,
        ) -> Dict[str, Any]:
            summary_text = basis_text_value or self._provenance_fallback_text()
            return {
                "reference_label": label,
                "reference_value": value,
                "reference_source_type": source_type,
                "reference_source_label": source_label,
                "reference_scope": scope,
                "comparison_method": comparison_method,
                "reference_basis_kind": basis_kind_value,
                "reference_basis_text": summary_text,
                "applicable_scope": scope,
                "applicable_conditions": conditions or "未声明",
                "reference_owner": owner,
                "last_reviewed_at": reviewed_at,
                "validation_status": validation,
                "reference_summary": summary_text,
            }

        if configured_reference is not None:
            return _payload(
                label="reference_value",
                value=configured_reference,
                source_label="当前配置参考值",
                source_type="indicator_profile",
                scope=applicable_scope,
                comparison_method="latest_snapshot_vs_fixed_reference",
                basis_kind_value=basis_kind,
                basis_text_value=basis_text,
                conditions=applicable_conditions,
                owner=reference_owner,
                reviewed_at=last_reviewed_at,
                validation=validation_status,
            )
        if benchmark is not None:
            return _payload(
                label="industry_benchmark",
                value=benchmark,
                source_label="当前配置参考值",
                source_type="indicator_profile",
                scope=applicable_scope,
                comparison_method="latest_snapshot_vs_fixed_reference",
                basis_kind_value=basis_kind,
                basis_text_value=basis_text,
                conditions=applicable_conditions,
                owner=reference_owner,
                reviewed_at=last_reviewed_at,
                validation=validation_status,
            )
        if range_target is not None:
            return _payload(
                label="range_target",
                value=range_target,
                source_label="当前配置目标值",
                source_type="indicator_profile",
                scope=applicable_scope,
                comparison_method="latest_snapshot_vs_target_reference",
                basis_kind_value=basis_kind,
                basis_text_value=basis_text,
                conditions=applicable_conditions,
                owner=reference_owner,
                reviewed_at=last_reviewed_at,
                validation=validation_status,
            )
        if design_ref is not None:
            return _payload(
                label="historical_design_reference",
                value=design_ref,
                source_label="历史设计参考值",
                source_type="historical_specs",
                scope="历史样本自动提取",
                comparison_method="latest_snapshot_vs_history_design_reference",
                basis_kind_value="design_value",
                basis_text_value="当前缺少显式配置参考值，临时采用历史设计参考值执行。",
                conditions="未声明",
                owner="",
                reviewed_at="",
                validation="traceable_unvalidated",
            )
        return _payload(
            label="current_value_fallback",
            value=fallback_value,
            source_label="当前值回退基准",
            source_type="fallback",
            scope="缺少外部参考时的保底口径",
            comparison_method="latest_snapshot_self_reference",
            basis_kind_value="",
            basis_text_value=self._provenance_fallback_text(),
            conditions="未声明",
            owner="",
            reviewed_at="",
            validation="traceable_unvalidated",
        )

    def _indicator_verification_points(self, detail: Dict[str, Any]) -> List[str]:
        name = str(detail.get("name") or detail.get("tag_id") or "未命名指标")
        points = [f"先确认{name}测点、量纲与最新采样时刻是否有效。"]
        if "膨胀机" in name:
            points.extend(
                [
                    "核查膨胀机入口/出口温压、导叶或阀位、转速与振动趋势。",
                    "确认膨胀机并联切换、旁通分配及防喘振动作记录。",
                ]
            )
        elif "主换" in name:
            points.extend(
                [
                    "核查主换压降、冷热端温差与复热不足相关点位是否同步恶化。",
                    "确认主换相关冷量分配和保冷状态，排除局部堵塞或泄漏迹象。",
                ]
            )
        elif "液氩" in name or "氩" in name:
            points.extend(
                [
                    "结合冷量侧变化复核氩系统回流、塔压与精馏负荷是否匹配。",
                    "确认液氩产量下降是否为结果项，而非独立测量异常。",
                ]
            )
        else:
            points.append(f"观察{name}在处置后是否向参考区间回归并保持至少 2 个观察窗口。")
        return points[:3]

    def _build_indicator_rule_trace(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        window = detail.get("window") or {}
        state_rule_trace = detail.get("state_rule_trace") or {}
        severity_breakdown = detail.get("severity_breakdown") or {}
        return {
            "rule_id": "indicator_deviation_duration_severity",
            "rule_name": "单指标偏差-持续性判级",
            "inputs": {
                "objective": detail.get("objective"),
                "reference_value": detail.get("reference_value"),
                "reference_label": detail.get("reference_source_label") or detail.get("reference_label"),
                "diff_ratio": detail.get("diff_ratio"),
                "diff_percent": detail.get("diff_percent"),
                "duration_points": int(self._safe_number(window.get("duration_points")) or 0),
                "trend": detail.get("trend"),
            },
            "decision": {
                "level": detail.get("level"),
                "matched_threshold": state_rule_trace.get("matched_interval"),
                "state_thresholds": state_rule_trace.get("thresholds") or {},
                "severity_components": severity_breakdown,
                "severity_score": detail.get("severity_score"),
                "optimization_direction": detail.get("optimization_direction"),
            },
            "description": (
                f"按{self._objective_label(str(detail.get('objective') or 'range'))}目标，"
                f"结合相对参考值偏差、持续点数与趋势，判定 {detail.get('name') or detail.get('tag_id') or '未命名指标'} 为"
                f"{detail.get('level') or '异常'}；命中阈值区间={state_rule_trace.get('matched_interval') or '未记录'}。"
            ),
        }

    def _build_indicator_evidence_layers(self, detail: Dict[str, Any]) -> Dict[str, List[str]]:
        name = str(detail.get("name") or detail.get("tag_id") or "未命名指标")
        current_value = self._format_number_text(detail.get("current_value"))
        target_reference = self._safe_number(detail.get("target_reference") or detail.get("reference_value"))
        target_reference_text = self._format_number_text(target_reference)
        reference_label = str(detail.get("reference_source_label") or detail.get("reference_label") or "参考值")
        target_diff_percent = self._safe_number(detail.get("target_diff_percent") if detail.get("target_diff_percent") is not None else detail.get("diff_percent"))
        history_baseline = self._safe_number(detail.get("history_baseline") if detail.get("history_baseline") is not None else detail.get("baseline_value"))
        history_diff_percent = self._safe_number(detail.get("history_diff_percent"))
        optimal_reference = self._safe_number(detail.get("optimal_reference"))
        optimal_diff_percent = self._safe_number(detail.get("optimal_diff_percent"))
        window = detail.get("window") or {}
        duration_points = int(self._safe_number(window.get("duration_points")) or 0)
        trend = str(detail.get("trend") or "stable")
        severity = self._format_number_text(detail.get("severity_score"), digits=3)
        severity_breakdown = detail.get("severity_breakdown") or {}
        final_grade_basis_label = str(detail.get("final_grade_basis_label") or "目标参考值")
        final_grade_basis_reason = str(detail.get("final_grade_basis_reason") or "")

        facts = [f"{name}当前值为 {current_value}。"]
        if target_reference is not None:
            facts.append(
                f"相对{reference_label} {target_reference_text} 的偏差为 {self._format_signed_percent(target_diff_percent)}。"
            )
        if duration_points > 0:
            facts.append(f"{name}已连续 {duration_points} 个采样点保持“{detail.get('level') or '异常'}”状态。")
        if history_baseline is not None:
            facts.append(
                f"相对历史运行基线 {self._format_number_text(history_baseline)} 的偏差为 "
                f"{self._format_signed_percent(history_diff_percent)}。"
            )
        if optimal_reference is not None:
            facts.append(
                f"相对优态基线 {self._format_number_text(optimal_reference)} 的偏差为 "
                f"{self._format_signed_percent(optimal_diff_percent)}。"
            )
        if (
            target_diff_percent is not None
            and history_diff_percent is not None
            and target_diff_percent * history_diff_percent < 0
        ):
            facts.append(
                f"{name}相对目标与相对历史常态的方向不一致，说明历史常态不等同于目标工况或优态工况。"
            )

        rules = [
            f"最终判级依据：{final_grade_basis_label}；{final_grade_basis_reason}",
            (
                f"单指标规则判定：按{self._objective_label(str(detail.get('objective') or 'range'))}目标，{name}被判为“{detail.get('level') or '异常'}”；"
                f"命中阈值区间={((detail.get('state_rule_trace') or {}).get('matched_interval')) or '未记录'}。"
            ),
            (
                f"持续性规则判定：趋势={trend}，持续点数={duration_points}，综合严重度={severity}；"
                f"level_score={self._format_number_text(severity_breakdown.get('level_score'), 3)}，"
                f"diff_component={self._format_number_text(severity_breakdown.get('diff_component'), 3)}，"
                f"duration_component={self._format_number_text(severity_breakdown.get('duration_component'), 3)}。"
            ),
        ]

        return {
            "facts": facts[:6],
            "rules": rules[:3],
            "hypotheses": [],
            "actions": self._indicator_verification_points(detail),
        }

    def _build_baseline_references(
        self,
        abnormal_details: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        baseline_method = str((baseline_profile or {}).get("method_label") or (baseline_profile or {}).get("method") or "")
        references: List[Dict[str, Any]] = []
        for item in abnormal_details[:5]:
            source_label = str(item.get("reference_source_label") or item.get("reference_label") or "未标注参考")
            reference_value = self._safe_number(item.get("target_reference") if item.get("target_reference") is not None else item.get("reference_value"))
            indicator = str(item.get("name") or item.get("tag_id") or "未命名指标")
            scope = str(item.get("reference_scope") or "未标注适用范围")
            comparison_method = str(item.get("comparison_method") or "未标注比较口径")
            history_baseline = self._safe_number(item.get("history_baseline") if item.get("history_baseline") is not None else item.get("baseline_value"))
            optimal_reference = self._safe_number(item.get("optimal_reference"))
            final_grade_basis_label = str(item.get("final_grade_basis_label") or "目标参考值")
            text = (
                f"{indicator}：目标参考值={source_label}"
                f"{f'（{self._format_number_text(reference_value)}）' if reference_value is not None else ''}；"
                f"历史运行基线={self._format_number_text(history_baseline)}；"
                f"优态基线={self._format_number_text(optimal_reference)}；"
                f"最终判级依据={final_grade_basis_label}；"
                f"适用范围={scope}；比较口径={comparison_method}"
            )
            if baseline_method:
                text = f"{text}；历史基线方法={baseline_method}"
            references.append(
                {
                    "indicator": indicator,
                    "target_reference_label": source_label,
                    "reference_source_label": source_label,
                    "reference_value": reference_value,
                    "history_baseline": history_baseline,
                    "optimal_reference": optimal_reference,
                    "final_grade_basis_label": final_grade_basis_label,
                    "reference_scope": scope,
                    "comparison_method": comparison_method,
                    "text": text,
                }
            )
        return references

    def _build_state_aggregation_rules(self) -> List[Dict[str, str]]:
        subsystem = self._rule_definition("subsystem_state")
        subsystem_params = subsystem.get("parameters") or {}
        plant = self._rule_definition("plant_state")
        plant_params = plant.get("parameters") or {}
        risk = self._rule_definition("risk_level")
        risk_params = risk.get("parameters") or {}
        severity = self._rule_definition("severity_formula")
        severity_params = severity.get("parameters") or {}

        constrained = subsystem_params.get("constrained") or {}
        suboptimal = subsystem_params.get("suboptimal") or {}
        abnormal_unstable = plant_params.get("abnormal_unstable") or {}
        risk_rising = plant_params.get("risk_rising") or {}
        no_abnormal = plant_params.get("no_abnormal") or {}
        critical = risk_params.get("critical") or {}
        warning = risk_params.get("warning") or {}

        return [
            {
                "stage": "单指标判级",
                "rule_id": severity.get("rule_name", "indicator_severity_formula"),
                "description": (
                    f"严重度公式=level_score + diff_component + duration_component；"
                    f"diff_weight={self._format_number_text(severity_params.get('diff_weight'), 2)}，"
                    f"duration_weight={self._format_number_text(severity_params.get('duration_weight'), 2)}，"
                    f"duration_cap={self._format_number_text(severity_params.get('duration_cap'), 2)}。"
                ),
            },
            {
                "stage": "子系统聚合",
                "rule_id": subsystem.get("rule_name", "subsystem_state_thresholds"),
                "description": (
                    f"abnormal_ratio>={self._format_number_text(constrained.get('abnormal_ratio_gte'), 2)} "
                    f"或 avg_severity>={self._format_number_text(constrained.get('avg_severity_gte'), 2)} 判为 constrained；"
                    f"abnormal_ratio>={self._format_number_text(suboptimal.get('abnormal_ratio_gte'), 2)} "
                    f"或 avg_severity>={self._format_number_text(suboptimal.get('avg_severity_gte'), 2)} 判为 suboptimal；"
                    "存在异常但未触发前述条件判为 attention；否则 stable。"
                ),
            },
            {
                "stage": "装置状态",
                "rule_id": plant.get("rule_name", "plant_state_thresholds"),
                "description": (
                    f"有异常时，abnormal_ratio>={self._format_number_text(abnormal_unstable.get('abnormal_ratio_gte'), 2)} "
                    f"或 max_severity>={self._format_number_text(abnormal_unstable.get('max_severity_gte'), 2)} 判为 abnormal_unstable；"
                    f"abnormal_ratio>={self._format_number_text(risk_rising.get('abnormal_ratio_gte'), 2)} "
                    f"或 max_severity>={self._format_number_text(risk_rising.get('max_severity_gte'), 2)} 判为 risk_rising；"
                    "其余为 optimizable。无异常时再按优态偏离区分 optimal/stable/optimizable，"
                    f"optimal_gap<={self._format_number_text(no_abnormal.get('optimal_gap_lte'), 2)} 为 optimal，"
                    f"optimal_gap<={self._format_number_text(no_abnormal.get('stable_gap_lte'), 2)} 为 stable。"
                ),
            },
            {
                "stage": "风险等级",
                "rule_id": risk.get("rule_name", "risk_level_thresholds"),
                "description": (
                    f"max_severity>={self._format_number_text(critical.get('max_severity_gte'), 2)} "
                    f"或异常占比>={self._format_number_text(critical.get('abnormal_ratio_gte'), 2)} 为高风险；"
                    f"max_severity>={self._format_number_text(warning.get('max_severity_gte'), 2)} "
                    f"或异常占比>={self._format_number_text(warning.get('abnormal_ratio_gte'), 2)} 为预警；"
                    "否则为需关注或稳定。"
                ),
            },
        ]

    def _build_triggered_rules(
        self,
        *,
        abnormal_count: int,
        total_count: int,
        max_severity: float,
        level_text: str,
        three_level: Dict[str, Any],
    ) -> List[str]:
        ratio = abnormal_count / max(total_count, 1)
        risk_rule = self._rule_definition("risk_level")
        plant_rule = self._rule_definition("plant_state")
        triggered = [
            (
                f"风险等级触发：规则={risk_rule.get('rule_name', 'risk_level_thresholds')}@{risk_rule.get('rule_version', 'v1')}；"
                f"异常占比 {ratio:.1%}、最大严重度 {max_severity:.3f}，当前判为“{level_text}”。"
            ),
            (
                f"装置状态触发：规则={plant_rule.get('rule_name', 'plant_state_thresholds')}@{plant_rule.get('rule_version', 'v1')}；"
                f"当前装置判为“{three_level.get('plant_state_label', '未知')}”，主导矛盾为“{three_level.get('main_contradiction', '未识别')}”。"
            ),
        ]
        for item in (three_level.get("subsystem_states") or [])[:3]:
            triggered.append(
                f"子系统聚合：{item.get('name', '未命名系统')} abnormal_count={item.get('abnormal_count', 0)}/"
                f"{item.get('total_count', 0)}，状态={item.get('state', 'unknown')}，置信度={self._format_number_text(item.get('confidence'), 3)}。"
            )
        return triggered

    def _build_verification_loop(self, abnormal_details: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        if not abnormal_details:
            return {
                "check_first": ["当前未识别主导异常，先完成测点有效性与班组点检表复核。"],
                "observe": ["继续观察核心工况是否稳定并保持在既有工艺边界内。"],
                "success_criteria": ["关键指标维持在可控范围，且未出现新的异常扩散。"],
                "rollback_triggers": ["若核心指标继续恶化或逼近联锁边界，立即回退至上一稳定工况。"],
            }

        primary = abnormal_details[0]
        secondary = abnormal_details[1] if len(abnormal_details) > 1 else None
        primary_name = str(primary.get("name") or primary.get("tag_id") or "首要异常指标")
        direction = self._resolve_optimization_direction(
            str(primary.get("objective") or "range"),
            self._safe_number(primary.get("current_value")),
            self._safe_number(primary.get("baseline_value")),
        )
        direction_text = {"increase": "回升", "decrease": "回落"}.get(direction, "改善")
        observe = [
            f"观察{primary_name}是否按预期向{direction_text}方向改善，并连续保持至少 2 个观察窗口。",
        ]
        success = [
            f"{primary_name}偏差收敛且持续点数不再扩展。",
        ]
        rollback = [
            f"若{primary_name}未改善或继续恶化，立即停止当前调整并回退。",
        ]
        check_first = [f"优先核查{primary_name}对应设备、测点和关键操作条件。"] + self._indicator_verification_points(primary)[1:3]

        if secondary:
            secondary_name = str(secondary.get("name") or secondary.get("tag_id") or "次级异常指标")
            observe.append(f"同步观察{secondary_name}是否出现联动改善，避免只修正表象而未消除主矛盾。")
            success.append(f"{secondary_name}不继续恶化，并与主导异常保持同向改善。")
            rollback.append(f"若{secondary_name}继续恶化，说明当前判断可能偏离主因，需回到复核步骤。")

        return {
            "check_first": check_first[:3],
            "observe": observe[:3],
            "success_criteria": success[:3],
            "rollback_triggers": rollback[:3],
        }

    def _build_overall_evidence_layers(
        self,
        abnormal_details: List[Dict[str, Any]],
        three_level: Dict[str, Any],
        triggered_rules: List[str],
        verification_loop: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        facts: List[str] = []
        rules: List[str] = list(triggered_rules)
        actions: List[str] = []

        for item in abnormal_details[:3]:
            evidence = item.get("evidence_layers") or {}
            facts.extend(evidence.get("facts") or [])
            rules.extend(evidence.get("rules") or [])
            actions.extend(evidence.get("actions") or [])

        if three_level.get("main_contradiction"):
            rules.append(f"主导矛盾提取：{three_level.get('main_contradiction')}")

        for label in ("check_first", "observe", "success_criteria", "rollback_triggers"):
            for entry in verification_loop.get(label) or []:
                actions.append(entry)

        return {
            "facts": facts[:6],
            "rules": rules[:6],
            "hypotheses": [],
            "actions": actions[:6],
        }

    def _build_reference_provenance(self, abnormal_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        provenance: List[Dict[str, Any]] = []
        for item in abnormal_details[:5]:
            basis_kind = str(item.get("reference_basis_kind") or "").strip()
            basis_text = str(item.get("reference_basis_text") or "").strip()
            validation_status = str(item.get("validation_status") or "").strip()
            final_grading_basis = str(item.get("final_grade_basis_label") or "目标参考值")
            comparison_basis = str(item.get("comparison_method") or "latest_snapshot_vs_fixed_reference")
            entry = {
                "indicator_name": str(item.get("name") or item.get("tag_id") or "未命名指标"),
                "reference_value": self._safe_number(item.get("target_reference") if item.get("target_reference") is not None else item.get("reference_value")),
                "reference_basis_kind": basis_kind,
                "reference_basis_kind_label": self._basis_kind_label(basis_kind),
                "reference_basis_text": basis_text or self._provenance_fallback_text(),
                "applicable_scope": str(item.get("applicable_scope") or item.get("reference_scope") or "当前装置指标配置"),
                "applicable_conditions": str(item.get("applicable_conditions") or "未声明"),
                "reference_owner": str(item.get("reference_owner") or ""),
                "last_reviewed_at": str(item.get("last_reviewed_at") or ""),
                "validation_status": validation_status or "traceable_unvalidated",
                "validation_status_label": self._validation_status_label(validation_status),
                "comparison_basis": comparison_basis,
                "final_grading_basis": final_grading_basis,
            }
            entry["text"] = (
                f"{entry['indicator_name']}：参考值={self._format_number_text(entry['reference_value'])}；"
                f"来源性质={entry['reference_basis_kind_label']}；"
                f"来源说明={entry['reference_basis_text']}；"
                f"适用范围={entry['applicable_scope']}；"
                f"适用边界={entry['applicable_conditions']}；"
                f"比较口径={entry['comparison_basis']}；"
                f"最终判级依据={entry['final_grading_basis']}；"
                f"成熟度={entry['validation_status_label']}。"
            )
            provenance.append(entry)
        return provenance

    def _build_rule_parameter_explanations(
        self,
        *,
        abnormal_count: int,
        total_count: int,
        max_severity: float,
        status_level: str,
        status_text: str,
        three_level: Dict[str, Any],
        abnormal_details: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ratio = abnormal_count / max(total_count, 1)
        risk_rule = self._rule_definition("risk_level")
        risk_params = risk_rule.get("parameters") or {}
        critical = risk_params.get("critical") or {}
        warning = risk_params.get("warning") or {}
        if status_level == "critical":
            risk_branch = "critical"
        elif status_level == "warning":
            risk_branch = "warning"
        else:
            risk_branch = "attention"

        plant_rule = self._rule_definition("plant_state")
        plant_params = plant_rule.get("parameters") or {}
        abnormal_unstable = plant_params.get("abnormal_unstable") or {}
        risk_rising = plant_params.get("risk_rising") or {}

        plant_state = str(three_level.get("plant_state") or "unknown")
        if plant_state == "abnormal_unstable":
            plant_branch = "abnormal_unstable"
        elif plant_state == "risk_rising":
            plant_branch = "risk_rising"
        else:
            plant_branch = plant_state

        top = abnormal_details[0] if abnormal_details else {}
        severity_rule = self._rule_definition("severity_formula")
        severity_params = severity_rule.get("parameters") or {}
        severity_breakdown = top.get("severity_breakdown") or {}
        severity_inputs = {
            "level": top.get("level") or top.get("state_desc"),
            "diff_percent": self._safe_number(top.get("diff_percent")),
            "duration_points": int(self._safe_number(((top.get("window") or {}).get("duration_points"))) or 0),
        }

        explanations = [
            {
                "type": "triggered_rule",
                "category": "risk_level",
                "title": "当前命中的风险等级规则",
                "rule_name": str(risk_rule.get("rule_name") or "risk_level_thresholds"),
                "rule_version": str(risk_rule.get("rule_version") or "v1"),
                "current_inputs": {
                    "abnormal_ratio": round(ratio, 4),
                    "max_severity": round(max_severity, 4),
                },
                "thresholds": {"critical": critical, "warning": warning},
                "matched_branch": risk_branch,
                "output": {"status_level": status_level, "status_text": status_text},
                "origin_statement": self.rule_origin_statement,
                "text": (
                    f"风险等级规则 {risk_rule.get('rule_name', 'risk_level_thresholds')}@{risk_rule.get('rule_version', 'v1')}："
                    f"当前 abnormal_ratio={ratio:.1%}，current_max_severity={max_severity:.3f}；"
                    f"critical 阈值为 abnormal_ratio>={float(critical.get('abnormal_ratio_gte')):.2f} 或 max_severity>={float(critical.get('max_severity_gte')):.2f}；"
                    f"warning 阈值为 abnormal_ratio>={float(warning.get('abnormal_ratio_gte')):.2f} 或 max_severity>={float(warning.get('max_severity_gte')):.2f}；"
                    f"当前命中分支={risk_branch}，输出结果={status_text}。"
                ),
            },
            {
                "type": "triggered_rule",
                "category": "plant_state",
                "title": "当前命中的装置状态规则",
                "rule_name": str(plant_rule.get("rule_name") or "plant_state_thresholds"),
                "rule_version": str(plant_rule.get("rule_version") or "v1"),
                "current_inputs": {
                    "abnormal_ratio": round(ratio, 4),
                    "max_severity": round(max_severity, 4),
                    "plant_state": plant_state,
                },
                "thresholds": {
                    "abnormal_unstable": abnormal_unstable,
                    "risk_rising": risk_rising,
                },
                "matched_branch": plant_branch,
                "output": {
                    "plant_state": plant_state,
                    "plant_state_label": three_level.get("plant_state_label"),
                },
                "origin_statement": self.rule_origin_statement,
                "text": (
                    f"装置状态规则 {plant_rule.get('rule_name', 'plant_state_thresholds')}@{plant_rule.get('rule_version', 'v1')}："
                    f"当前 abnormal_ratio={ratio:.1%}，current_max_severity={max_severity:.3f}；"
                    f"abnormal_unstable 阈值为 abnormal_ratio>={float(abnormal_unstable.get('abnormal_ratio_gte')):.2f} 或 max_severity>={float(abnormal_unstable.get('max_severity_gte')):.2f}；"
                    f"risk_rising 阈值为 abnormal_ratio>={float(risk_rising.get('abnormal_ratio_gte')):.2f} 或 max_severity>={float(risk_rising.get('max_severity_gte')):.2f}；"
                    f"当前命中分支={plant_branch}，输出结果={three_level.get('plant_state_label', '未知')}。"
                ),
            },
            {
                "type": "severity_formula",
                "category": "severity_formula",
                "title": "严重度计算说明",
                "rule_name": str(severity_rule.get("rule_name") or "indicator_severity_formula"),
                "rule_version": str(severity_rule.get("rule_version") or "v1"),
                "weights": {
                    "base_score_fallback": self._safe_number(severity_params.get("base_score")),
                    "diff_weight": self._safe_number(severity_params.get("diff_weight")),
                    "duration_weight": self._safe_number(severity_params.get("duration_weight")),
                    "duration_cap": self._safe_number(severity_params.get("duration_cap")),
                },
                "current_inputs": severity_inputs,
                "current_output": {
                    "indicator_name": top.get("name") or top.get("tag_id"),
                    "severity_score": self._safe_number(top.get("severity_score")),
                    "severity_breakdown": severity_breakdown,
                },
                "origin_statement": self.rule_origin_statement,
                "text": (
                    f"严重度公式 {severity_rule.get('rule_name', 'indicator_severity_formula')}@{severity_rule.get('rule_version', 'v1')}："
                    f"level_score + diff_component + duration_component；"
                    f"base_score_fallback={self._format_number_text(severity_params.get('base_score'), 2)}，"
                    f"diff_weight={self._format_number_text(severity_params.get('diff_weight'), 2)}，"
                    f"duration_weight={self._format_number_text(severity_params.get('duration_weight'), 2)}，"
                    f"duration_cap={self._format_number_text(severity_params.get('duration_cap'), 2)}；"
                    f"本轮示例指标={top.get('name') or top.get('tag_id') or '未命名指标'}，"
                    f"level={severity_inputs['level']}，diff_percent={self._format_signed_percent(severity_inputs['diff_percent'])}，"
                    f"duration_points={severity_inputs['duration_points']}，"
                    f"level_score={self._format_number_text(severity_breakdown.get('level_score'), 3)}，"
                    f"diff_component={self._format_number_text(severity_breakdown.get('diff_component'), 3)}，"
                    f"duration_component={self._format_number_text(severity_breakdown.get('duration_component'), 3)}，"
                    f"current_severity_score={self._format_number_text(top.get('severity_score'), 3)}。"
                ),
            },
            {
                "type": "rule_origin",
                "category": "rule_origin",
                "title": "规则来源状态",
                "origin_statement": self.rule_origin_statement,
                "text": self.rule_origin_statement,
            },
        ]
        return explanations

    def _build_dominant_anomaly_explanation(
        self,
        abnormal_details: List[Dict[str, Any]],
        three_level: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not abnormal_details:
            return {
                "classification": "none",
                "candidate_label": "当前未识别主导异常候选",
                "rank_explanation": "当前未识别主导异常候选。",
                "duration_explanation": "当前未形成持续异常证据。",
                "subsystem_impact_explanation": "当前未形成可解释的子系统聚合影响。",
                "coupling_consistency_explanation": "当前未形成可解释的耦合一致性。",
                "temporal_precedence_explanation": "当前未形成稳定时间先后证据，仅按严重度与持续性作为优先核查依据。",
                "exclusion_boundary_explanation": "本项为优先核查对象 / 疑似根因链起点，不等于已确认根因。当前仍需排除测点异常、整体负荷或上游供气变化、主换或下游设备先发异常。",
            }

        top = abnormal_details[0]
        second = abnormal_details[1] if len(abnormal_details) > 1 else None
        top_subsystem = self._resolve_subsystem_name(top.get("tag_id"), top.get("name"))
        top_duration = int(self._safe_number(((top.get("window") or {}).get("duration_points"))) or 0)
        top_severity = float(top.get("severity_score") or 0.0)
        same_subsystem = False
        severity_gap = None
        duration_gap = None
        if second:
            second_subsystem = self._resolve_subsystem_name(second.get("tag_id"), second.get("name"))
            same_subsystem = second_subsystem == top_subsystem
            severity_gap = abs(float(top.get("severity_score") or 0.0) - float(second.get("severity_score") or 0.0))
            duration_gap = abs(
                int(self._safe_number(((top.get("window") or {}).get("duration_points"))) or 0)
                - int(self._safe_number(((second.get("window") or {}).get("duration_points"))) or 0)
            )

        co_primary = bool(second and severity_gap is not None and duration_gap is not None and severity_gap < 0.05 and duration_gap < 12 and same_subsystem)
        candidate_label = "并列主导异常候选" if co_primary else "优先核查对象 / 疑似根因链起点"

        subsystem_state = {}
        for item in three_level.get("subsystem_states") or []:
            if item.get("name") == top_subsystem:
                subsystem_state = item
                break

        if co_primary and second:
            rank_explanation = (
                f"{top.get('name') or top.get('tag_id')} 与 {second.get('name') or second.get('tag_id')} 的 severity_score 差值 "
                f"{severity_gap:.3f} < 0.05，按并列主导异常候选处理。"
            )
        else:
            rank_explanation = (
                f"{top.get('name') or top.get('tag_id')} 在本轮异常中 severity_score={top_severity:.3f} 排名第一，"
                "因此被列为优先核查对象。"
            )

        duration_explanation = (
            f"{top.get('name') or top.get('tag_id')} 已连续 {top_duration} 个采样点保持异常状态，"
            "持续性满足优先核查条件。"
        )

        subsystem_impact_explanation = (
            f"{top_subsystem} 当前聚合状态为 {subsystem_state.get('state', 'unknown')}，"
            f"异常数={subsystem_state.get('abnormal_count', 0)}/{subsystem_state.get('total_count', 0)}，"
            "说明该异常已进入子系统聚合判断。"
        )

        if second:
            coupling_consistency_explanation = (
                f"次级异常 {second.get('name') or second.get('tag_id')} 与主导异常同处于 {three_level.get('main_contradiction', '当前主导矛盾')}，"
                "当前耦合方向一致，可作为联动异常而非单点孤立异常理解。"
            )
        else:
            coupling_consistency_explanation = "当前未形成稳定的次级异常耦合链，仅能确认该项是本轮最强异常表现。"

        if second and str((top.get("window") or {}).get("end") or "") == str((second.get("window") or {}).get("end") or "") and top_duration > int(self._safe_number(((second.get("window") or {}).get("duration_points"))) or 0):
            temporal_precedence_explanation = (
                f"{top.get('name') or top.get('tag_id')} 领先于次级异常 "
                f"{top_duration - int(self._safe_number(((second.get('window') or {}).get('duration_points'))) or 0)} 个采样点，"
                "可作为时间先后性上的优先核查依据。"
            )
        else:
            temporal_precedence_explanation = "当前未形成稳定时间先后证据，仅按严重度与持续性作为优先核查依据。"

        exclusion_boundary_explanation = (
            "本项为优先核查对象 / 疑似根因链起点，不等于已确认根因。"
            "当前仍需排除测点异常、整体负荷或上游供气变化、主换或下游设备先发异常。"
        )

        return {
            "classification": "co_primary" if co_primary else "dominant",
            "candidate_label": candidate_label,
            "rank_explanation": rank_explanation,
            "duration_explanation": duration_explanation,
            "subsystem_impact_explanation": subsystem_impact_explanation,
            "coupling_consistency_explanation": coupling_consistency_explanation,
            "temporal_precedence_explanation": temporal_precedence_explanation,
            "exclusion_boundary_explanation": exclusion_boundary_explanation,
            "indicator_name": top.get("name") or top.get("tag_id"),
            "text_sections": [
                rank_explanation,
                duration_explanation,
                subsystem_impact_explanation,
                coupling_consistency_explanation,
                temporal_precedence_explanation,
                exclusion_boundary_explanation,
            ],
        }

    def _build_three_level_state_engine(
        self,
        semantic_data: List[Dict[str, Any]],
        abnormal_details: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        abnormal_by_tag = {str(item.get("tag_id") or ""): item for item in (abnormal_details or []) if item.get("tag_id")}

        variable_semantics: List[Dict[str, Any]] = []
        subsystem_bucket: Dict[str, Dict[str, Any]] = {}
        optimal_gap_values: List[float] = []

        for item in semantic_data or []:
            tag = str(item.get("tag_id") or "")
            name = str(item.get("name") or "")
            subsystem = self._resolve_subsystem_name(tag, name)
            abnormal = abnormal_by_tag.get(tag)
            trend = (abnormal or {}).get("trend") or "stable"
            diff_percent = (abnormal or {}).get("diff_percent")
            state_desc = str(item.get("ai_state_desc") or item.get("state_desc") or "Unknown")
            severity = float((abnormal or {}).get("severity_score") or 0.0)
            confidence = float(item.get("ai_confidence") or item.get("membership_degree") or 0.0)
            if confidence > 1:
                confidence = confidence / 100.0
            confidence = max(0.0, min(1.0, confidence))

            baseline_row = baseline_map.get(tag) or {}
            current_value = self._safe_number(item.get("current_value"))
            optimal_ref = self._safe_number(baseline_row.get("optimal_reference"))
            if current_value is not None and optimal_ref is not None and abs(optimal_ref) > 1e-6:
                optimal_gap_values.append(abs(current_value - optimal_ref) / abs(optimal_ref))

            variable_semantics.append(
                {
                    "tag_id": tag,
                    "name": name,
                    "subsystem": subsystem,
                    "semantic_state": state_desc,
                    "semantic_label": self._to_variable_semantics_label(state_desc, str(trend), self._safe_number(diff_percent)),
                    "confidence": round(confidence, 4),
                    "severity_score": round(severity, 4),
                    "trend": trend,
                    "optimization_direction": (abnormal or {}).get("optimization_direction") or "stabilize",
                }
            )

            bucket = subsystem_bucket.setdefault(
                subsystem,
                {
                    "name": subsystem,
                    "total_count": 0,
                    "abnormal_count": 0,
                    "severity_sum": 0.0,
                    "focus_tags": [],
                    "members": [],
                },
            )
            bucket["total_count"] += 1
            bucket["members"].append({"tag_id": tag, "name": name or tag or "未命名指标"})
            if abnormal:
                bucket["abnormal_count"] += 1
                bucket["severity_sum"] += severity
                if len(bucket["focus_tags"]) < 3:
                    bucket["focus_tags"].append(name or tag or "未命名指标")

        subsystem_states: List[Dict[str, Any]] = []
        for bucket in subsystem_bucket.values():
            total_count = max(1, int(bucket["total_count"]))
            abnormal_count = int(bucket["abnormal_count"])
            abnormal_ratio = abnormal_count / total_count
            avg_severity = (bucket["severity_sum"] / abnormal_count) if abnormal_count > 0 else 0.0
            subsystem_state = self._subsystem_state_from_scores(abnormal_ratio, avg_severity)
            confidence = min(0.95, 0.45 + abnormal_ratio * 0.4 + min(avg_severity, 1.2) * 0.3)
            subsystem_states.append(
                {
                    "name": bucket["name"],
                    "state": subsystem_state,
                    "confidence": round(confidence, 4),
                    "abnormal_count": abnormal_count,
                    "total_count": total_count,
                    "abnormal_ratio": round(abnormal_ratio, 4),
                    "avg_severity": round(avg_severity, 4),
                    "focus_tags": bucket["focus_tags"],
                    "members": bucket["members"],
                }
            )

        subsystem_states.sort(key=lambda x: (-x["abnormal_count"], -x["confidence"], x["name"]))

        total_count = len(semantic_data or [])
        abnormal_count = len(abnormal_details or [])
        abnormal_ratio = abnormal_count / max(1, total_count)
        max_severity = max((float(x.get("severity_score") or 0.0) for x in (abnormal_details or [])), default=0.0)
        avg_optimal_gap = (sum(optimal_gap_values) / len(optimal_gap_values)) if optimal_gap_values else 0.0
        plant_params = self._rule_parameters("plant_state")
        abnormal_unstable = plant_params.get("abnormal_unstable") or {}
        risk_rising = plant_params.get("risk_rising") or {}
        no_abnormal = plant_params.get("no_abnormal") or {}

        if abnormal_count == 0:
            if avg_optimal_gap <= float(no_abnormal.get("optimal_gap_lte")):
                plant_state = "optimal"
            elif avg_optimal_gap <= float(no_abnormal.get("stable_gap_lte")):
                plant_state = "stable"
            else:
                plant_state = "optimizable"
        else:
            if abnormal_ratio >= float(abnormal_unstable.get("abnormal_ratio_gte")) or max_severity >= float(abnormal_unstable.get("max_severity_gte")):
                plant_state = "abnormal_unstable"
            elif abnormal_ratio >= float(risk_rising.get("abnormal_ratio_gte")) or max_severity >= float(risk_rising.get("max_severity_gte")):
                plant_state = "risk_rising"
            else:
                plant_state = "optimizable"

        plant_state_label_map = {
            "optimal": "优态",
            "stable": "稳态",
            "optimizable": "可优化态",
            "risk_rising": "风险上升态",
            "abnormal_unstable": "异常失稳态",
        }

        optimization_priority: List[str] = []
        for item in subsystem_states:
            if item["state"] in {"constrained", "suboptimal", "attention"}:
                optimization_priority.append(f"优先处理{item['name']}（状态={item['state']}）")
        if not optimization_priority:
            optimization_priority.append("保持当前策略，持续监控优态偏离。")

        main_contradiction = "未识别明显主导矛盾。"
        if abnormal_details:
            top = sorted(abnormal_details, key=lambda x: float(x.get("severity_score") or 0.0), reverse=True)[0]
            sub_name = self._resolve_subsystem_name(top.get("tag_id"), top.get("name"))
            main_contradiction = f"{sub_name}存在主导偏离：{top.get('name') or top.get('tag_id') or '未命名指标'}。"

        global_semantics = [
            f"装置整体状态={plant_state_label_map.get(plant_state, plant_state)}",
            f"异常占比={abnormal_ratio:.1%}",
            f"优态偏离={avg_optimal_gap:.1%}",
        ]
        for item in subsystem_states[:2]:
            global_semantics.append(f"{item['name']}={item['state']}（置信度{item['confidence']:.2f}）")

        return {
            "plant_state": plant_state,
            "plant_state_label": plant_state_label_map.get(plant_state, plant_state),
            "global_semantics": global_semantics,
            "optimization_priority": optimization_priority[:4],
            "main_contradiction": main_contradiction,
            "subsystem_states": subsystem_states,
            "variable_semantics": variable_semantics,
            "avg_optimal_gap": round(avg_optimal_gap, 4),
        }

    def build_baseline_profile(self, history_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        S3 历史/优态基线建模
        基于历史分位数 + 指标目标方向，给出每个指标的 baseline / optimal 参考。
        """
        grouped: Dict[str, List[float]] = {}
        for row in history_data or []:
            tag = row.get("tag_id")
            value = self._safe_number(row.get("value"))
            if tag and value is not None:
                grouped.setdefault(tag, []).append(value)

        per_tag: Dict[str, Dict[str, Any]] = {}
        for tag, vals in grouped.items():
            if not vals:
                continue
            profile = self._get_indicator_profile(tag, "")
            objective = str((profile or {}).get("objective") or "range")
            p10 = self._percentile(vals, 0.1)
            p50 = self._percentile(vals, 0.5)
            p90 = self._percentile(vals, 0.9)
            target = self._safe_number(((profile or {}).get("industry_range") or {}).get("target"))
            baseline_value = p50 if p50 is not None else vals[-1]
            if objective == "maximize":
                optimal_reference = p90 if p90 is not None else baseline_value
            elif objective == "minimize":
                optimal_reference = p10 if p10 is not None else baseline_value
            else:
                optimal_reference = target if target is not None else baseline_value

            per_tag[tag] = {
                "objective": objective,
                "count": len(vals),
                "min": min(vals),
                "max": max(vals),
                "p10": p10,
                "median": p50,
                "p90": p90,
                "baseline_value": baseline_value,
                "optimal_reference": optimal_reference,
                "baseline_source": {
                    "type": "historical_median",
                    "label": "同装置历史中位基线",
                    "scope": "当前装置历史样本",
                },
                "optimal_source": {
                    "type": "objective_percentile_reference",
                    "label": "按目标方向提取的优态参考",
                    "scope": "当前装置历史样本",
                },
            }

        return {
            "method": "historical_percentile_plus_objective_profile",
            "method_label": "同装置历史分位基线 + 指标目标方向",
            "source_label": "历史样本分位统计",
            "rules": [
                "baseline_value 默认取历史中位数（p50），用于描述当前工况相对常态的偏离。",
                "optimal_reference 根据目标方向提取：maximize 取 p90，minimize 取 p10，range 取 target 或 baseline。",
            ],
            "tag_count": len(per_tag),
            "per_tag": per_tag,
        }

    def calculate_membership(self, value: float, design_value: float, min_value: float, max_value: float) -> float:
        span = max((max_value - min_value), 1e-6)
        return max(0.0, min(1.0, 1.0 - abs(value - design_value) / span * 2.0))

    def get_semantic_state(self, membership: float) -> str:
        if membership >= 0.95:
            return "优秀"
        if membership >= 0.85:
            return "良好"
        if membership >= 0.65:
            return "一般"
        if membership >= 0.4:
            return "较差"
        if membership >= 0.2:
            return "偏差较大"
        return "异常"

    def _build_semantic_snapshot_item(self, item: Dict[str, Any], realtime_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        tag_id = item.get("tag_id")
        name = item.get("name", "Unknown")
        value = self._safe_number(item.get("value"))
        if value is None:
            return {
                "tag_id": tag_id,
                "name": name,
                "current_value": item.get("value"),
                "state_desc": "Unknown",
                "diff": 0.0,
                "membership_degree": 0.0,
                "assessment_reason": "invalid value",
                "comparison_summary": "",
                "reference_label": "invalid_reference",
                "reference_value": None,
                "reference_source_type": "invalid",
                "reference_source_label": "无有效参考",
                "reference_scope": "输入值无效",
                "comparison_method": "not_available",
                "reference_basis_kind": "",
                "reference_basis_text": self._provenance_fallback_text(),
                "applicable_scope": "输入值无效",
                "applicable_conditions": "未声明",
                "reference_owner": "",
                "last_reviewed_at": "",
                "validation_status": "traceable_unvalidated",
            }
        profile = self._get_indicator_profile(tag_id or "", name) or {}
        spec = self.specs.get(tag_id or "", {})
        objective = profile.get("objective", "range")
        reference_meta = self._reference_source_metadata(profile, spec, value)
        ref = self._safe_number(reference_meta.get("reference_value")) or value
        diff = value - ref
        rel = diff / max(abs(ref), 1e-6)
        low = self._safe_number((profile.get("industry_range") or {}).get("min"))
        high = self._safe_number((profile.get("industry_range") or {}).get("max"))
        standby_context = self._standby_suppression_context(
            tag_id=str(tag_id or ""),
            name=name,
            value=value,
            realtime_context=realtime_context,
        )
        if standby_context.get("is_standby_suppressed"):
            state_rule_trace = {
                "state": "待机备用",
                "matched_interval": str(standby_context.get("reason") or "standby_guard"),
                "thresholds": {
                    "objective": str(objective or "range"),
                    "pair_tag": standby_context.get("pair_tag"),
                    "pair_active_threshold": standby_context.get("pair_active_threshold"),
                    "self_idle_threshold": standby_context.get("self_idle_threshold"),
                },
                "standby_context": standby_context,
            }
            return {
                "tag_id": tag_id,
                "name": name,
                "current_value": value,
                "state_desc": "待机备用",
                "diff": diff,
                "diff_ratio": round(rel, 6),
                "membership_degree": self._state_to_membership("待机备用"),
                "assessment_reason": "standby-guard",
                "comparison_summary": str(standby_context.get("summary") or ""),
                "reference_label": reference_meta.get("reference_label"),
                "reference_value": ref,
                "reference_source_type": reference_meta.get("reference_source_type"),
                "reference_source_label": reference_meta.get("reference_source_label"),
                "reference_scope": reference_meta.get("reference_scope"),
                "comparison_method": "standby_pair_guard",
                "reference_basis_kind": reference_meta.get("reference_basis_kind"),
                "reference_basis_text": reference_meta.get("reference_basis_text"),
                "applicable_scope": reference_meta.get("applicable_scope"),
                "applicable_conditions": reference_meta.get("applicable_conditions"),
                "reference_owner": reference_meta.get("reference_owner"),
                "last_reviewed_at": reference_meta.get("last_reviewed_at"),
                "validation_status": reference_meta.get("validation_status"),
                "state_rule_trace": state_rule_trace,
                "standby_context": standby_context,
            }
        state_rule_trace = self._indicator_state_rule_trace(
            objective=str(objective or "range"),
            diff_ratio=rel,
            current_value=value,
            low=low,
            high=high,
        )
        state = str(state_rule_trace.get("state") or "Unknown")
        return {
            "tag_id": tag_id,
            "name": name,
            "current_value": value,
            "state_desc": state,
            "diff": diff,
            "diff_ratio": round(rel, 6),
            "membership_degree": self._state_to_membership(state),
            "assessment_reason": "rule-based",
            "comparison_summary": f"reference {ref:.3f}",
            "reference_label": reference_meta.get("reference_label"),
            "reference_value": ref,
            "reference_source_type": reference_meta.get("reference_source_type"),
            "reference_source_label": reference_meta.get("reference_source_label"),
            "reference_scope": reference_meta.get("reference_scope"),
            "comparison_method": reference_meta.get("comparison_method"),
            "reference_basis_kind": reference_meta.get("reference_basis_kind"),
            "reference_basis_text": reference_meta.get("reference_basis_text"),
            "applicable_scope": reference_meta.get("applicable_scope"),
            "applicable_conditions": reference_meta.get("applicable_conditions"),
            "reference_owner": reference_meta.get("reference_owner"),
            "last_reviewed_at": reference_meta.get("last_reviewed_at"),
            "validation_status": reference_meta.get("validation_status"),
            "state_rule_trace": state_rule_trace,
            "standby_context": standby_context,
        }

    def process(self, realtime_data: List[Dict]) -> List[Dict]:
        context = {x.get("tag_id"): self._safe_number(x.get("value")) for x in (realtime_data or []) if x.get("tag_id")}
        semantic = [self._build_semantic_snapshot_item(x, context) for x in (realtime_data or [])]
        validated = validate_semantic_data(semantic)
        return [x.model_dump() for x in validated]

    async def _process_single_item_async(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return self._build_semantic_snapshot_item(item)

    async def process_async(self, realtime_data: List[Dict], batch_size: int = 100) -> List[Dict]:
        out: List[Dict[str, Any]] = []
        for i in range(0, len(realtime_data or []), batch_size):
            batch = realtime_data[i : i + batch_size]
            results = await asyncio.gather(*[self._process_single_item_async(x) for x in batch], return_exceptions=True)
            out.extend([x for x in results if isinstance(x, dict)])
        validated = validate_semantic_data(out)
        return [x.model_dump() for x in validated]

    def extract_features(self, history_data: List[Dict]) -> Dict:
        grouped: Dict[str, List[float]] = {}
        for row in history_data or []:
            tag = row.get("tag_id")
            value = self._safe_number(row.get("value"))
            if tag and value is not None:
                grouped.setdefault(tag, []).append(value)
        feats: Dict[str, Dict[str, Any]] = {}
        for tag, vals in grouped.items():
            calc = [v for v in vals if ("Expander" not in tag or v > self.expander_idle_threshold)] or vals
            mean = sum(calc) / len(calc)
            std = (sum((x - mean) ** 2 for x in calc) / len(calc)) ** 0.5
            trend = "stable" if len(vals) < 2 else ("increasing" if vals[-1] - vals[0] > std * 0.5 else ("decreasing" if vals[-1] - vals[0] < -std * 0.5 else "stable"))
            feats[tag] = {"mean": mean, "std": std, "trend": trend, "current": vals[-1], "min": min(vals), "max": max(vals), "median": self._percentile(calc, 0.5), "p10": self._percentile(calc, 0.1), "p90": self._percentile(calc, 0.9), "count": len(vals)}
        return feats

    def identify_system_state(self, features: Dict) -> Dict:
        return {"load_condition": "Normal Load", "operation_mode": "Unknown"}

    def _compute_diff_percent(self, current_value: Any, diff: Any) -> Optional[float]:
        c = self._safe_number(current_value)
        d = self._safe_number(diff)
        if c is None or d is None:
            return None
        b = c - d
        if abs(b) < 1e-6:
            return None
        return d / b * 100.0

    def _calculate_severity_score(self, level: str, diff_percent: Optional[float], duration_points: int) -> float:
        return float(self._calculate_severity_components(level, diff_percent, duration_points).get("severity_score") or 0.0)

    def _is_abnormal_state(self, state_desc: str) -> bool:
        return is_abnormal_state(state_desc)

    def _format_signed_percent(self, value: Optional[float]) -> str:
        if value is None:
            return "-"
        return f"{value:+.1f}%"

    def _resolve_status_level(self, abnormal_count: int, total_count: int, max_severity: float) -> str:
        if abnormal_count <= 0:
            return "stable"
        ratio = abnormal_count / max(total_count, 1)
        params = self._rule_parameters("risk_level")
        critical = params.get("critical") or {}
        warning = params.get("warning") or {}
        if max_severity >= float(critical.get("max_severity_gte")) or ratio >= float(critical.get("abnormal_ratio_gte")):
            return "critical"
        if max_severity >= float(warning.get("max_severity_gte")) or ratio >= float(warning.get("abnormal_ratio_gte")):
            return "warning"
        return "attention"

    def _status_level_text(self, status_level: str) -> str:
        return {
            "stable": "稳定",
            "attention": "需关注",
            "warning": "预警",
            "critical": "高风险",
        }.get(status_level, "需关注")

    def _action_hint(self, status_level: str) -> str:
        return {
            "stable": "建议保持当前运行策略，按计划进行巡检。",
            "attention": "建议优先复核重点偏差指标，确认是否存在持续漂移。",
            "warning": "建议尽快执行异常指标复核与工艺参数校准，必要时安排现场排查。",
            "critical": "建议立即启动高风险处置流程，安排人工确认并执行联动检查。",
        }.get(status_level, "建议继续复核异常指标并补充现场确认。")

    def _build_rule_reason(self, detail: Dict[str, Any], history_count: int) -> str:
        level = detail.get("level") or "异常"
        trend = detail.get("trend") or "stable"
        reference_label = detail.get("reference_source_label") or detail.get("reference_label") or "参考值"
        reference_value = self._format_number_text(detail.get("reference_value"))
        duration = int(self._safe_number((detail.get("window") or {}).get("duration_points")) or 0)
        basis_label = detail.get("final_grade_basis_label") or "目标参考值"
        matched_threshold = ((detail.get("state_rule_trace") or {}).get("matched_interval")) or "未记录"
        return (
            f"规则判定为{level}；最终判级依据={basis_label}；参考口径={reference_label}({reference_value})；"
            f"命中阈值={matched_threshold}；历史样本={history_count}条；持续点数={duration}；趋势={trend}。"
        )

    def build_abnormal_details(
        self,
        history_data: List[Dict],
        latest_semantic_data: List[Dict],
        baseline_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        features = self.extract_features(history_data)
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        grouped: Dict[str, List[Dict]] = {}
        for row in history_data or []:
            tag = row.get("tag_id")
            if tag:
                grouped.setdefault(tag, []).append(row)
        out: List[Dict[str, Any]] = []
        for item in latest_semantic_data or []:
            if not self._is_abnormal_state(item.get("state_desc", "")):
                continue
            tag = item.get("tag_id")
            rows = sorted(grouped.get(tag, []), key=lambda x: str(x.get("timestamp", "")))
            if not rows:
                continue
            latest_ts = str(rows[-1].get("timestamp", ""))
            duration = 1
            for row in reversed(rows[:-1]):
                snap = self._build_semantic_snapshot_item(row)
                if self._is_abnormal_state(snap.get("state_desc", "")):
                    duration += 1
                else:
                    break
            diff = item.get("diff", 0.0)
            diff_percent = self._compute_diff_percent(item.get("current_value"), diff)
            profile = self._get_indicator_profile(tag or "", item.get("name", "")) or {}
            objective = str(profile.get("objective") or "range")
            baseline_value = self._safe_number((baseline_map.get(tag) or {}).get("baseline_value"))
            optimal_reference = self._safe_number((baseline_map.get(tag) or {}).get("optimal_reference"))
            if baseline_value is None:
                baseline_value = (self._safe_number(item.get("current_value")) or 0.0) - (self._safe_number(diff) or 0.0)
            current_value = self._safe_number(item.get("current_value"))
            history_values = [self._safe_number(row.get("value")) for row in rows]
            ordered_history_values = [value for value in history_values if value is not None]
            optimization_direction = self._resolve_optimization_direction(objective, current_value, baseline_value)
            gap_to_baseline = None
            if current_value is not None and baseline_value is not None:
                gap_to_baseline = round(current_value - baseline_value, 6)
            gap_to_optimal = None
            if current_value is not None and optimal_reference is not None:
                gap_to_optimal = round(current_value - optimal_reference, 6)

            target_reference = self._safe_number(item.get("reference_value"))
            target_diff_percent = diff_percent
            history_diff_percent = self._relative_diff_percent(current_value, baseline_value)
            optimal_diff_percent = self._relative_diff_percent(current_value, optimal_reference)
            history_percentile_rank = self._percentile_rank(current_value, ordered_history_values)
            grade_basis = self._grade_basis_metadata(target_reference is not None)
            severity_breakdown = self._calculate_severity_components(str(item.get("state_desc") or ""), diff_percent, duration)

            detail = {
                "tag_id": tag,
                "name": item.get("name"),
                "value": item.get("current_value"),
                "current_value": item.get("current_value"),
                "baseline_value": baseline_value,
                "gap_to_baseline": gap_to_baseline,
                "optimization_direction": optimization_direction,
                "objective": objective,
                "diff": diff,
                "diff_ratio": item.get("diff_ratio"),
                "diff_percent": diff_percent,
                "target_reference": target_reference,
                "target_diff_percent": target_diff_percent,
                "history_baseline": baseline_value,
                "history_diff_percent": history_diff_percent,
                "history_percentile_rank": round(history_percentile_rank, 4) if history_percentile_rank is not None else None,
                "optimal_reference": optimal_reference,
                "optimal_diff_percent": optimal_diff_percent,
                "gap_to_optimal": gap_to_optimal,
                "final_grade_basis": grade_basis.get("basis"),
                "final_grade_basis_label": grade_basis.get("basis_label"),
                "final_grade_basis_reason": grade_basis.get("basis_reason"),
                "level": item.get("state_desc"),
                "window": {"start": str(rows[-duration].get("timestamp", latest_ts)), "end": latest_ts, "duration_points": duration, "is_ongoing": True},
                "snapshot_timestamp": latest_ts,
                "trend": (features.get(tag) or {}).get("trend", "stable"),
                "membership_degree": item.get("membership_degree"),
                "ai_reason": "",
                "assessment_reason": item.get("assessment_reason", ""),
                "comparison_summary": item.get("comparison_summary", ""),
                "reference_label": item.get("reference_label"),
                "reference_value": item.get("reference_value"),
                "reference_source_type": item.get("reference_source_type"),
                "reference_source_label": item.get("reference_source_label"),
                "reference_scope": item.get("reference_scope"),
                "comparison_method": item.get("comparison_method"),
                "reference_basis_kind": item.get("reference_basis_kind"),
                "reference_basis_text": item.get("reference_basis_text"),
                "applicable_scope": item.get("applicable_scope"),
                "applicable_conditions": item.get("applicable_conditions"),
                "reference_owner": item.get("reference_owner"),
                "last_reviewed_at": item.get("last_reviewed_at"),
                "validation_status": item.get("validation_status"),
                "state_rule_trace": item.get("state_rule_trace") or {},
            }
            detail["rule_reason"] = self._build_rule_reason(detail, len(rows))
            detail["severity_breakdown"] = severity_breakdown
            detail["severity_score"] = float(severity_breakdown.get("severity_score") or 0.0)
            detail["reference_context"] = {
                "source_type": detail.get("reference_source_type"),
                "source_label": detail.get("reference_source_label"),
                "scope": detail.get("reference_scope"),
                "comparison_method": detail.get("comparison_method"),
                "reference_value": detail.get("reference_value"),
                "history_baseline": detail.get("history_baseline"),
                "optimal_reference": detail.get("optimal_reference"),
                "final_grade_basis": detail.get("final_grade_basis"),
                "final_grade_basis_label": detail.get("final_grade_basis_label"),
                "reference_basis_kind": detail.get("reference_basis_kind"),
                "reference_basis_text": detail.get("reference_basis_text"),
                "applicable_scope": detail.get("applicable_scope"),
                "applicable_conditions": detail.get("applicable_conditions"),
                "reference_owner": detail.get("reference_owner"),
                "last_reviewed_at": detail.get("last_reviewed_at"),
                "validation_status": detail.get("validation_status"),
            }
            detail["rule_trace"] = self._build_indicator_rule_trace(detail)
            detail["evidence_layers"] = self._build_indicator_evidence_layers(detail)
            out.append(detail)
        return sorted(out, key=lambda x: (-x.get("severity_score", 0), -abs(x.get("diff_percent") or 0), x.get("name") or ""))

    def _build_calculation_audit(
        self,
        *,
        semantic_data: List[Dict[str, Any]],
        abnormal_details: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]] = None,
        history_data: Optional[List[Dict[str, Any]]] = None,
        parsing_audit: Optional[Dict[str, Any]] = None,
        three_level: Optional[Dict[str, Any]] = None,
        status_level: str = "",
        status_text: str = "",
        explainability: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        semantic_data = semantic_data or []
        abnormal_details = abnormal_details or []
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        abnormal_by_tag = {str(item.get("tag_id") or ""): item for item in abnormal_details if item.get("tag_id")}
        history_map = self._group_history_values(history_data or [])
        features = self.extract_features(history_data or []) if history_data else {}
        three_level = three_level or {}
        explainability = explainability or {}

        indicators: List[Dict[str, Any]] = []
        for item in semantic_data:
            tag = str(item.get("tag_id") or "")
            detail = abnormal_by_tag.get(tag) or {}
            baseline_row = baseline_map.get(tag) or {}
            current_value = self._safe_number(item.get("current_value"))
            target_reference = self._safe_number(
                detail.get("target_reference")
                if detail.get("target_reference") is not None
                else item.get("reference_value")
            )
            history_baseline = self._safe_number(
                detail.get("history_baseline")
                if detail.get("history_baseline") is not None
                else baseline_row.get("baseline_value")
            )
            optimal_reference = self._safe_number(
                detail.get("optimal_reference")
                if detail.get("optimal_reference") is not None
                else baseline_row.get("optimal_reference")
            )
            diff_percent = self._safe_number(detail.get("diff_percent"))
            if diff_percent is None:
                diff_percent = self._relative_diff_percent(current_value, target_reference)
            history_diff_percent = self._safe_number(detail.get("history_diff_percent"))
            if history_diff_percent is None:
                history_diff_percent = self._relative_diff_percent(current_value, history_baseline)
            optimal_diff_percent = self._safe_number(detail.get("optimal_diff_percent"))
            if optimal_diff_percent is None:
                optimal_diff_percent = self._relative_diff_percent(current_value, optimal_reference)

            history_percentile_rank = self._safe_number(detail.get("history_percentile_rank"))
            if history_percentile_rank is None:
                history_percentile_rank = self._percentile_rank(current_value, history_map.get(tag) or [])

            state_rule_trace = detail.get("state_rule_trace") or item.get("state_rule_trace") or {}
            severity_breakdown = detail.get("severity_breakdown") or {
                "level_score": 0.0,
                "diff_component": 0.0,
                "duration_component": 0.0,
                "duration_component_raw": 0.0,
                "duration_cap": float(self.severity_config["duration_cap"]),
                "duration_cap_applied": False,
                "severity_score": 0.0,
                "base_score_fallback": float(self.severity_config["base_score"]),
            }
            grade_basis = detail or self._grade_basis_metadata(target_reference is not None)
            window = detail.get("window") or {}
            indicators.append(
                {
                    "tag_id": tag,
                    "name": item.get("name"),
                    "objective": baseline_row.get("objective") or detail.get("objective"),
                    "objective_label": self._objective_label(str(baseline_row.get("objective") or detail.get("objective") or "range")),
                    "state_label": item.get("state_desc"),
                    "current_value": current_value,
                    "target_reference": target_reference,
                    "history_baseline": history_baseline,
                    "optimal_reference": optimal_reference,
                    "final_grade_basis": grade_basis.get("final_grade_basis") or grade_basis.get("basis"),
                    "final_grade_basis_label": grade_basis.get("final_grade_basis_label") or grade_basis.get("basis_label"),
                    "final_grade_basis_reason": grade_basis.get("final_grade_basis_reason") or grade_basis.get("basis_reason"),
                    "diff_ratio": self._safe_number(detail.get("diff_ratio") if detail.get("diff_ratio") is not None else item.get("diff_ratio")),
                    "diff_percent": diff_percent,
                    "history_diff_percent": history_diff_percent,
                    "optimal_diff_percent": optimal_diff_percent,
                    "history_percentile_rank": round(history_percentile_rank, 4) if history_percentile_rank is not None else None,
                    "trend": detail.get("trend") or (features.get(tag) or {}).get("trend") or "stable",
                    "duration_points": int(self._safe_number(window.get("duration_points")) or 0),
                    "severity_score": round(float(detail.get("severity_score") or 0.0), 4),
                    "severity_breakdown": severity_breakdown,
                    "state_rule_trace": state_rule_trace,
                    "comparison_method": detail.get("comparison_method") or item.get("comparison_method"),
                    "reference_label": detail.get("reference_source_label") or item.get("reference_source_label") or item.get("reference_label"),
                }
            )

        subsystem_params = self._rule_parameters("subsystem_state")
        constrained = subsystem_params.get("constrained") or {}
        suboptimal = subsystem_params.get("suboptimal") or {}
        subsystems: List[Dict[str, Any]] = []
        for item in (three_level.get("subsystem_states") or []):
            abnormal_ratio = float(item.get("abnormal_ratio") or 0.0)
            avg_severity = float(item.get("avg_severity") or 0.0)
            matched_branch = str(item.get("state") or "stable")
            triggered_by: List[str] = []
            if abnormal_ratio >= float(constrained.get("abnormal_ratio_gte")):
                triggered_by.append(f"abnormal_ratio>={float(constrained.get('abnormal_ratio_gte')):.2f}")
            if avg_severity >= float(constrained.get("avg_severity_gte")):
                triggered_by.append(f"avg_severity>={float(constrained.get('avg_severity_gte')):.2f}")
            if not triggered_by:
                if abnormal_ratio >= float(suboptimal.get("abnormal_ratio_gte")):
                    triggered_by.append(f"abnormal_ratio>={float(suboptimal.get('abnormal_ratio_gte')):.2f}")
                if avg_severity >= float(suboptimal.get("avg_severity_gte")):
                    triggered_by.append(f"avg_severity>={float(suboptimal.get('avg_severity_gte')):.2f}")
            if not triggered_by and int(item.get("abnormal_count") or 0) > 0:
                triggered_by.append("存在异常但未触发 constrained/suboptimal")

            subsystems.append(
                {
                    "name": item.get("name"),
                    "state": matched_branch,
                    "abnormal_count": int(item.get("abnormal_count") or 0),
                    "total_count": int(item.get("total_count") or 0),
                    "abnormal_ratio": round(abnormal_ratio, 4),
                    "avg_severity": round(avg_severity, 4),
                    "members": [member.get("name") for member in (item.get("members") or []) if member.get("name")],
                    "thresholds": {
                        "constrained": constrained,
                        "suboptimal": suboptimal,
                    },
                    "triggered_by": triggered_by,
                }
            )

        total_count = len(semantic_data)
        abnormal_count = len(abnormal_details)
        abnormal_ratio = abnormal_count / max(total_count, 1)
        max_severity = max((float(item.get("severity_score") or 0.0) for item in abnormal_details), default=0.0)
        avg_optimal_gap = float((three_level or {}).get("avg_optimal_gap") or 0.0)
        risk_params = self._rule_parameters("risk_level")
        plant_params = self._rule_parameters("plant_state")
        dominant_explanation = (explainability.get("dominant_anomaly_explanation") or {}) if isinstance(explainability, dict) else {}
        plant_state = str(three_level.get("plant_state") or "unknown")
        if status_level == "critical":
            risk_branch = "critical"
        elif status_level == "warning":
            risk_branch = "warning"
        else:
            risk_branch = "attention"
        if plant_state in {"abnormal_unstable", "risk_rising", "optimizable", "optimal", "stable"}:
            plant_branch = plant_state
        else:
            plant_branch = "unknown"

        return {
            "data_intake": parsing_audit or {},
            "indicators": indicators,
            "subsystems": subsystems,
            "plant": {
                "abnormal_count": abnormal_count,
                "total_count": total_count,
                "abnormal_ratio": round(abnormal_ratio, 4),
                "max_severity": round(max_severity, 4),
                "avg_optimal_gap": round(avg_optimal_gap, 4),
                "risk_level": status_level,
                "risk_level_label": status_text,
                "risk_branch": risk_branch,
                "risk_thresholds": risk_params,
                "plant_state": plant_state,
                "plant_state_label": three_level.get("plant_state_label"),
                "plant_state_branch": plant_branch,
                "plant_state_thresholds": plant_params,
                "main_contradiction": three_level.get("main_contradiction"),
                "dominant_anomaly": {
                    "indicator_name": (abnormal_details[0].get("name") if abnormal_details else None),
                    "candidate_label": dominant_explanation.get("candidate_label"),
                    "rank_explanation": dominant_explanation.get("rank_explanation"),
                    "temporal_precedence_explanation": dominant_explanation.get("temporal_precedence_explanation"),
                    "boundary": dominant_explanation.get("exclusion_boundary_explanation"),
                },
            },
        }

    def build_overall_operating_summary(
        self,
        semantic_data: List[Dict],
        abnormal_details: List[Dict],
        baseline_profile: Optional[Dict[str, Any]] = None,
        history_data: Optional[List[Dict[str, Any]]] = None,
        parsing_audit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        semantic_data = semantic_data or []
        abnormal_details = abnormal_details or []
        total = len(semantic_data)
        abnormal = len(abnormal_details)
        good_count = sum(1 for x in semantic_data if x.get("state_desc") in {"优秀", "良好", "待机备用"})
        normal_count = sum(1 for x in semantic_data if x.get("state_desc") == "一般")
        max_severity = max((float(x.get("severity_score") or 0.0) for x in abnormal_details), default=0.0)
        level = self._resolve_status_level(abnormal, total, max_severity)
        level_text = self._status_level_text(level)
        risk_ratio = round(abnormal / total * 100.0, 1) if total > 0 else 0.0
        three_level = self._build_three_level_state_engine(
            semantic_data=semantic_data,
            abnormal_details=abnormal_details,
            baseline_profile=baseline_profile,
        )

        top_risks: List[str] = []
        for item in abnormal_details[:3]:
            name = item.get("name") or item.get("tag_id") or "未命名指标"
            state = item.get("level") or item.get("state_desc") or "异常"
            diff_percent = self._safe_number(item.get("diff_percent"))
            duration = int(self._safe_number((item.get("window") or {}).get("duration_points")) or 0)
            duration_text = f"，连续{duration}个采样点" if duration > 1 else ""
            diff_text = self._format_signed_percent(diff_percent) if diff_percent is not None else "偏差待确认"
            top_risks.append(f"{name}：{state}（偏差{diff_text}{duration_text}）")

        summary = (
            f"本次共评估 {total} 项指标，识别异常 {abnormal} 项（{risk_ratio:.1f}%），"
            f"当前运行风险等级为「{level_text}」，装置语义状态为「{three_level.get('plant_state_label', '未知')}」。"
        )

        highlights: List[str] = [
            f"状态分布：优秀/良好 {good_count} 项，一般 {normal_count} 项，异常 {abnormal} 项。"
        ]
        if top_risks:
            highlights.extend(top_risks)
        else:
            highlights.append("未发现明显异常候选，当前关键指标整体处于可控范围。")

        action_hint = self._action_hint(level)
        highlights.append(action_hint)
        for line in (three_level.get("global_semantics") or [])[:2]:
            highlights.append(line)
        baseline_references = self._build_baseline_references(abnormal_details, baseline_profile=baseline_profile)
        reference_framework = self._build_reference_framework()
        state_aggregation_rules = self._build_state_aggregation_rules()
        triggered_rules = self._build_triggered_rules(
            abnormal_count=abnormal,
            total_count=total,
            max_severity=max_severity,
            level_text=level_text,
            three_level=three_level,
        )
        verification_loop = self._build_verification_loop(abnormal_details)
        evidence_layers = self._build_overall_evidence_layers(
            abnormal_details=abnormal_details,
            three_level=three_level,
            triggered_rules=triggered_rules,
            verification_loop=verification_loop,
        )
        explainability = {
            "reference_provenance": self._build_reference_provenance(abnormal_details),
            "rule_parameter_explanations": self._build_rule_parameter_explanations(
                abnormal_count=abnormal,
                total_count=total,
                max_severity=max_severity,
                status_level=level,
                status_text=level_text,
                three_level=three_level,
                abnormal_details=abnormal_details,
            ),
            "dominant_anomaly_explanation": self._build_dominant_anomaly_explanation(
                abnormal_details=abnormal_details,
                three_level=three_level,
            ),
        }
        calculation_audit = self._build_calculation_audit(
            semantic_data=semantic_data,
            abnormal_details=abnormal_details,
            baseline_profile=baseline_profile,
            history_data=history_data,
            parsing_audit=parsing_audit,
            three_level=three_level,
            status_level=level,
            status_text=level_text,
            explainability=explainability,
        )

        return {
            "status_level": level,
            "status_text": level_text,
            "summary": summary,
            "highlights": highlights,
            "risk_points": top_risks,
            "risk_ratio": risk_ratio,
            "action_hint": action_hint,
            "total_count": total,
            "good_count": good_count,
            "normal_count": normal_count,
            "abnormal_count": abnormal,
            "three_level_state_engine": three_level,
            "plant_state": three_level.get("plant_state"),
            "plant_state_label": three_level.get("plant_state_label"),
            "optimization_priority": three_level.get("optimization_priority") or [],
            "main_contradiction": three_level.get("main_contradiction") or "",
            "subsystem_states": three_level.get("subsystem_states") or [],
            "reference_framework": reference_framework,
            "baseline_references": baseline_references,
            "state_aggregation_rules": state_aggregation_rules,
            "triggered_rules": triggered_rules,
            "evidence_layers": evidence_layers,
            "verification_loop": verification_loop,
            "explainability": explainability,
            "calculation_audit": calculation_audit,
            "explanation_boundary": "根因解释仅作为候选假设和优先核查线索，需结合压力、阀位、温度、振动和操作日志完成现场确认，不构成已确认根因。",
        }

    def build_history_profile_cache_payload(self, history_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        baseline_profile = self.build_baseline_profile(history_data or [])
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signature": self._history_signature(history_data or []),
            "baseline_profile": baseline_profile,
        }

    def write_history_profile_cache(self, history_data: List[Dict[str, Any]], output_path: Optional[str] = None) -> Dict[str, Any]:
        payload = self.build_history_profile_cache_payload(history_data or [])
        cache_path = Path(output_path or self.history_model_cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _history_lane_for_indicator(
        self,
        *,
        item: Dict[str, Any],
        rows: List[Dict[str, Any]],
        baseline_row: Dict[str, Any],
        duration_points: int = 0,
        rule_severity_score: float = 0.0,
    ) -> Dict[str, Any]:
        current_value = self._safe_number(item.get("current_value"))
        profile = self._get_indicator_profile(str(item.get("tag_id") or ""), str(item.get("name") or "")) or {}
        objective = str((baseline_row or {}).get("objective") or profile.get("objective") or "range")
        low = self._safe_number(((profile.get("industry_range") or {}).get("min")))
        high = self._safe_number(((profile.get("industry_range") or {}).get("max")))
        baseline_value = self._safe_number((baseline_row or {}).get("baseline_value"))
        standby_context = item.get("standby_context") or {}
        if isinstance(standby_context, dict) and standby_context.get("is_standby_suppressed"):
            return {
                "selected_regime": (baseline_row or {}).get("selected_regime") or "global",
                "regime_sample_count": int(self._safe_number((baseline_row or {}).get("regime_sample_count")) or 0),
                "global_sample_count": int(self._safe_number((baseline_row or {}).get("global_sample_count")) or 0),
                "historical_baseline": baseline_value,
                "optimal_reference": self._safe_number((baseline_row or {}).get("optimal_reference")),
                "percentile_rank": None,
                "robust_z_score": 0.0,
                "z_component": 0.0,
                "directed_tail_score": 0.0,
                "persistence_points": 0,
                "persistence_score": 0.0,
                "statistical_anomaly_score": 0.0,
                "statistical_state": "normal",
                "statistical_direction": "normal",
                "agreement_flag": "agree",
                "hybrid_severity_score": 0.0,
                "standby_context": standby_context,
            }
        history_values = [self._safe_number(row.get("value")) for row in rows if self._safe_number(row.get("value")) is not None]
        percentile_rank = self._percentile_rank(current_value, history_values)
        robust_z_score = self._robust_z_score(current_value, baseline_row or {})
        z_component = min(abs(robust_z_score) / max(float(self.history_model_params.get("robust_z_clip", 3.0)), 1e-6), 1.0)
        directed_tail_score = self._directed_tail_score(
            current_value=current_value,
            objective=objective,
            baseline_row=baseline_row or {},
            low=low,
            high=high,
        )
        run_length = self._series_run_length(
            history_values,
            objective=objective,
            baseline_value=baseline_value,
            low=low,
            high=high,
        )
        persistence_points = max(int(duration_points or 0), int(run_length or 0))
        persistence_cap = max(int(self.history_model_params.get("persistence_cap_points", 12)), 1)
        persistence_score = min(persistence_points / persistence_cap, 1.0)
        anomaly_score = round(0.5 * z_component + 0.3 * directed_tail_score + 0.2 * persistence_score, 4)
        statistical_state = self._statistical_state(anomaly_score)
        statistical_direction = self._statistical_direction(
            objective=objective,
            current_value=current_value,
            baseline_row=baseline_row or {},
            low=low,
            high=high,
        )
        agreement_flag = self._agreement_flag(
            rule_state=str(item.get("state_desc") or item.get("level") or "Unknown"),
            objective=objective,
            current_value=current_value,
            low=low,
            high=high,
            statistical_state=statistical_state,
            statistical_direction=statistical_direction,
        )
        fusion_weight = float(self.history_model_params.get("fusion_weight", 0.25))
        hybrid_severity_score = round(
            max(float(rule_severity_score or 0.0), float(rule_severity_score or 0.0) + fusion_weight * anomaly_score),
            4,
        )
        return {
            "selected_regime": (baseline_row or {}).get("selected_regime") or "global",
            "regime_sample_count": int(self._safe_number((baseline_row or {}).get("regime_sample_count")) or 0),
            "global_sample_count": int(self._safe_number((baseline_row or {}).get("global_sample_count")) or 0),
            "historical_baseline": baseline_value,
            "optimal_reference": self._safe_number((baseline_row or {}).get("optimal_reference")),
            "percentile_rank": round(percentile_rank, 4) if percentile_rank is not None else None,
            "robust_z_score": round(robust_z_score, 4),
            "z_component": round(z_component, 4),
            "directed_tail_score": round(directed_tail_score, 4),
            "persistence_points": persistence_points,
            "persistence_score": round(persistence_score, 4),
            "statistical_anomaly_score": anomaly_score,
            "statistical_state": statistical_state,
            "statistical_direction": statistical_direction,
            "agreement_flag": agreement_flag,
            "hybrid_severity_score": hybrid_severity_score,
        }

    def _build_history_lane_map(
        self,
        *,
        semantic_data: List[Dict[str, Any]],
        history_data: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]],
        abnormal_details: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        rows_by_tag = self._history_rows_by_tag(history_data or [])
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        abnormal_by_tag = {str(item.get("tag_id") or ""): item for item in (abnormal_details or []) if item.get("tag_id")}
        history_lane_map: Dict[str, Dict[str, Any]] = {}
        for item in semantic_data or []:
            tag = str(item.get("tag_id") or "")
            detail = abnormal_by_tag.get(tag) or {}
            duration_points = int(self._safe_number(((detail.get("window") or {}).get("duration_points"))) or 0)
            history_lane_map[tag] = self._history_lane_for_indicator(
                item=item,
                rows=rows_by_tag.get(tag, []),
                baseline_row=baseline_map.get(tag) or {},
                duration_points=duration_points,
                rule_severity_score=float(detail.get("severity_score") or 0.0),
            )
        return history_lane_map

    def build_baseline_profile(self, history_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        history_signature = self._history_signature(history_data or [])
        cached_profile = self._load_history_profile_cache(history_signature)
        if cached_profile:
            return cached_profile

        rows_by_tag = self._history_rows_by_tag(history_data or [])
        values_by_time = self._history_values_by_time(history_data or [])
        anchor_tag = str(self.history_model_config.get("anchor_tag") or "")
        anchor_values = [
            self._safe_number(row.get("value"))
            for row in rows_by_tag.get(anchor_tag, [])
            if self._safe_number(row.get("value")) is not None
        ]
        quantiles = self.history_model_config.get("regime_quantiles") or {}
        regime_cut_points = {
            "low_max": self._percentile(anchor_values, float(quantiles.get("low_max", 0.33))) if anchor_values else None,
            "high_min": self._percentile(anchor_values, float(quantiles.get("high_min", 0.67))) if anchor_values else None,
        }
        latest_timestamp = history_signature.get("max_timestamp")
        anchor_latest_value = self._safe_number((values_by_time.get(str(latest_timestamp or "")) or {}).get(anchor_tag))
        selected_regime = self._regime_for_anchor_value(anchor_latest_value, regime_cut_points)
        min_samples_per_regime = int(self.history_model_params.get("min_samples_per_regime", 40))
        min_samples_global = int(self.history_model_params.get("min_samples_global", 90))

        per_tag: Dict[str, Dict[str, Any]] = {}
        exclusion_summary: Dict[str, Dict[str, int]] = {}
        any_global_fallback = False
        for tag, rows in rows_by_tag.items():
            profile = self._get_indicator_profile(tag, "") or {}
            objective = str(profile.get("objective") or "range")
            global_rows: List[Dict[str, Any]] = []
            regime_rows: Dict[str, List[Dict[str, Any]]] = {"low": [], "nominal": [], "high": []}
            excluded: Dict[str, int] = {}
            for row in rows:
                timestamp = str(row.get("timestamp") or "")
                value = self._safe_number(row.get("value"))
                active, reason = self._is_active_profile_row(tag=tag, timestamp=timestamp, value=value, values_by_time=values_by_time)
                if not active:
                    if reason:
                        excluded[reason] = excluded.get(reason, 0) + 1
                    continue
                regime_name = self._regime_for_anchor_value(
                    self._safe_number((values_by_time.get(timestamp) or {}).get(anchor_tag)),
                    regime_cut_points,
                )
                row_payload = {"timestamp": timestamp, "value": value, "regime": regime_name}
                global_rows.append(row_payload)
                if regime_name in regime_rows:
                    regime_rows[regime_name].append(row_payload)
            exclusion_summary[tag] = excluded
            global_values = [row["value"] for row in global_rows if row.get("value") is not None]
            if not global_values:
                continue

            global_profile = {
                **self._stats_from_values(global_values),
                "active_sample_count": len(global_values),
                "coverage_start": global_rows[0]["timestamp"] if global_rows else None,
                "coverage_end": global_rows[-1]["timestamp"] if global_rows else None,
            }
            regime_profiles: Dict[str, Dict[str, Any]] = {}
            for regime_name, regime_specific_rows in regime_rows.items():
                regime_values = [row["value"] for row in regime_specific_rows if row.get("value") is not None]
                regime_profiles[regime_name] = {
                    **self._stats_from_values(regime_values),
                    "active_sample_count": len(regime_values),
                    "coverage_start": regime_specific_rows[0]["timestamp"] if regime_specific_rows else None,
                    "coverage_end": regime_specific_rows[-1]["timestamp"] if regime_specific_rows else None,
                }

            selected_profile = regime_profiles.get(selected_regime) or {}
            use_global_fallback = (
                selected_regime == "global"
                or int(selected_profile.get("active_sample_count") or 0) < min_samples_per_regime
                or int(global_profile.get("active_sample_count") or 0) < min_samples_global
            )
            chosen_profile = global_profile if use_global_fallback else selected_profile
            any_global_fallback = any_global_fallback or use_global_fallback
            baseline_value = self._safe_number(chosen_profile.get("median"))
            if baseline_value is None:
                baseline_value = global_values[-1]
            target = self._safe_number(((profile.get("industry_range") or {}).get("target")))
            if objective == "maximize":
                optimal_reference = self._safe_number(chosen_profile.get("p90"))
            elif objective == "minimize":
                optimal_reference = self._safe_number(chosen_profile.get("p10"))
            else:
                optimal_reference = target if target is not None else baseline_value
            if optimal_reference is None:
                optimal_reference = baseline_value

            per_tag[tag] = {
                "objective": objective,
                "count": len(global_values),
                "min": self._safe_number(chosen_profile.get("min")),
                "max": self._safe_number(chosen_profile.get("max")),
                "mean": self._safe_number(chosen_profile.get("mean")),
                "std": self._safe_number(chosen_profile.get("std")),
                "p10": self._safe_number(chosen_profile.get("p10")),
                "median": self._safe_number(chosen_profile.get("median")),
                "p90": self._safe_number(chosen_profile.get("p90")),
                "mad": self._safe_number(chosen_profile.get("mad")),
                "iqr": self._safe_number(chosen_profile.get("iqr")),
                "baseline_value": baseline_value,
                "optimal_reference": optimal_reference,
                "selected_regime": selected_regime,
                "selected_profile_source": "global_fallback" if use_global_fallback else "regime_profile",
                "regime_sample_count": int(selected_profile.get("active_sample_count") or 0),
                "global_sample_count": int(global_profile.get("active_sample_count") or 0),
                "active_sample_count": int(chosen_profile.get("active_sample_count") or 0),
                "coverage_start": chosen_profile.get("coverage_start"),
                "coverage_end": chosen_profile.get("coverage_end"),
                "regime_profiles": regime_profiles,
                "excluded_samples": excluded,
                "baseline_source": {
                    "type": "regime_aware_historical_median",
                    "label": "工况分层历史中位数",
                    "scope": "同装置同工况历史样本",
                },
                "optimal_source": {
                    "type": "objective_percentile_reference",
                    "label": "工况分层优态分位参考",
                    "scope": "同装置同工况历史样本",
                },
            }

        metadata = {
            "profile_source": "runtime",
            "cache_path": str(self.history_model_cache_path),
            "signature": history_signature,
            "anchor_tag": anchor_tag,
            "anchor_present": bool(anchor_values),
            "anchor_latest_value": anchor_latest_value,
            "regime_cut_points": regime_cut_points,
            "selected_regime": selected_regime,
            "global_fallback_used": any_global_fallback,
            "hybrid_aggregation_enabled": bool(self.history_model_params.get("hybrid_aggregation_enabled", False)),
            "key_indicator_tags": list(self.history_model_config.get("key_indicator_tags") or []),
            "exclusion_summary": exclusion_summary,
        }

        return {
            "method": "regime_aware_historical_profile",
            "method_label": "工况分层历史基线 + 目标方向优态参考",
            "source_label": "历史画像 / 同装置同工况样本",
            "rules": [
                "baseline_value 默认取当前工况档位的历史中位数；当前档位样本不足时自动回退到全局历史样本。",
                "optimal_reference 依目标方向取当前工况档位的 p90 / p10；range 指标优先使用目标 target。",
            ],
            "tag_count": len(per_tag),
            "per_tag": per_tag,
            "history_model_metadata": metadata,
        }

    def extract_features(self, history_data: List[Dict], baseline_profile: Optional[Dict[str, Any]] = None) -> Dict:
        baseline_profile = baseline_profile or self.build_baseline_profile(history_data or [])
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        rows_by_tag = self._history_rows_by_tag(history_data or [])
        values_by_time = self._history_values_by_time(history_data or [])
        short_window = int(self.history_model_params.get("trend_short_window", 7))
        long_window = int(self.history_model_params.get("trend_long_window", 30))
        per_tag: Dict[str, Dict[str, Any]] = {}
        for tag, rows in rows_by_tag.items():
            filtered_values: List[float] = []
            for row in rows:
                value = self._safe_number(row.get("value"))
                active, _ = self._is_active_profile_row(
                    tag=tag,
                    timestamp=str(row.get("timestamp") or ""),
                    value=value,
                    values_by_time=values_by_time,
                )
                if active and value is not None:
                    filtered_values.append(value)
            values = filtered_values or [self._safe_number(row.get("value")) for row in rows if self._safe_number(row.get("value")) is not None]
            if not values:
                continue
            stats = self._stats_from_values(values)
            slope_7 = self._window_slope(values, short_window)
            slope_30 = self._window_slope(values, long_window)
            ewma_value = self._ewma_last(values, short_window)
            rolling_values = values[-min(short_window, len(values)):]
            rolling_mean = sum(rolling_values) / len(rolling_values)
            rolling_std = math.sqrt(sum((value - rolling_mean) ** 2 for value in rolling_values) / max(len(rolling_values), 1))
            baseline_row = baseline_map.get(tag) or {}
            profile = self._get_indicator_profile(tag, "") or {}
            per_tag[tag] = {
                "mean": self._safe_number(stats.get("mean")),
                "std": self._safe_number(stats.get("std")),
                "trend": self._trend_from_slopes(slope_7, slope_30, self._safe_number(stats.get("std"))),
                "current": values[-1],
                "min": self._safe_number(stats.get("min")),
                "max": self._safe_number(stats.get("max")),
                "median": self._safe_number(stats.get("median")),
                "p10": self._safe_number(stats.get("p10")),
                "p90": self._safe_number(stats.get("p90")),
                "count": len(values),
                "slope_7": round(slope_7, 6),
                "slope_30": round(slope_30, 6),
                "ewma_deviation": round(values[-1] - ewma_value, 6),
                "rolling_std": round(rolling_std, 6),
                "rolling_range": round(max(rolling_values) - min(rolling_values), 6),
                "run_length": self._series_run_length(
                    values,
                    objective=str(baseline_row.get("objective") or profile.get("objective") or "range"),
                    baseline_value=self._safe_number(baseline_row.get("baseline_value")),
                    low=self._safe_number(((profile.get("industry_range") or {}).get("min"))),
                    high=self._safe_number(((profile.get("industry_range") or {}).get("max"))),
                ),
                "change_point_index": self._detect_change_point(values, max(3, min(short_window, max(3, len(values) // 3)))),
                "selected_regime": baseline_row.get("selected_regime"),
            }
        return {
            "per_tag": per_tag,
            "history_model_metadata": dict((baseline_profile or {}).get("history_model_metadata") or {}),
        }

    def build_abnormal_details(
        self,
        history_data: List[Dict],
        latest_semantic_data: List[Dict],
        baseline_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        baseline_profile = baseline_profile or self.build_baseline_profile(history_data or [])
        features = self.extract_features(history_data or [], baseline_profile=baseline_profile)
        feature_map = self._feature_map(features)
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        grouped = self._history_rows_by_tag(history_data or [])
        values_by_time = self._history_values_by_time(history_data or [])
        out: List[Dict[str, Any]] = []
        for item in latest_semantic_data or []:
            if not self._is_abnormal_state(item.get("state_desc", "")):
                continue
            tag = str(item.get("tag_id") or "")
            rows = grouped.get(tag, [])
            if not rows:
                continue
            latest_ts = str(rows[-1].get("timestamp", ""))
            duration = 1
            for row in reversed(rows[:-1]):
                row_timestamp = str(row.get("timestamp", ""))
                snap = self._build_semantic_snapshot_item(row, values_by_time.get(row_timestamp) or {})
                if self._is_abnormal_state(snap.get("state_desc", "")):
                    duration += 1
                else:
                    break
            diff = item.get("diff", 0.0)
            diff_percent = self._compute_diff_percent(item.get("current_value"), diff)
            profile = self._get_indicator_profile(tag, item.get("name", "")) or {}
            objective = str((baseline_map.get(tag) or {}).get("objective") or profile.get("objective") or "range")
            baseline_value = self._safe_number((baseline_map.get(tag) or {}).get("baseline_value"))
            optimal_reference = self._safe_number((baseline_map.get(tag) or {}).get("optimal_reference"))
            if baseline_value is None:
                baseline_value = (self._safe_number(item.get("current_value")) or 0.0) - (self._safe_number(diff) or 0.0)
            current_value = self._safe_number(item.get("current_value"))
            optimization_direction = self._resolve_optimization_direction(objective, current_value, baseline_value)
            target_reference = self._safe_number(item.get("reference_value"))
            severity_breakdown = self._calculate_severity_components(str(item.get("state_desc") or ""), diff_percent, duration)
            statistical_lane = self._history_lane_for_indicator(
                item=item,
                rows=rows,
                baseline_row=baseline_map.get(tag) or {},
                duration_points=duration,
                rule_severity_score=float(severity_breakdown.get("severity_score") or 0.0),
            )
            grade_basis = self._grade_basis_metadata(target_reference is not None)

            detail = {
                "tag_id": tag,
                "name": item.get("name"),
                "value": item.get("current_value"),
                "current_value": item.get("current_value"),
                "baseline_value": baseline_value,
                "gap_to_baseline": round(current_value - baseline_value, 6) if current_value is not None and baseline_value is not None else None,
                "optimization_direction": optimization_direction,
                "objective": objective,
                "diff": diff,
                "diff_ratio": item.get("diff_ratio"),
                "diff_percent": diff_percent,
                "target_reference": target_reference,
                "target_diff_percent": diff_percent,
                "history_baseline": baseline_value,
                "history_diff_percent": self._relative_diff_percent(current_value, baseline_value),
                "history_percentile_rank": statistical_lane.get("percentile_rank"),
                "optimal_reference": optimal_reference,
                "optimal_diff_percent": self._relative_diff_percent(current_value, optimal_reference),
                "gap_to_optimal": round(current_value - optimal_reference, 6) if current_value is not None and optimal_reference is not None else None,
                "final_grade_basis": grade_basis.get("basis"),
                "final_grade_basis_label": grade_basis.get("basis_label"),
                "final_grade_basis_reason": grade_basis.get("basis_reason"),
                "level": item.get("state_desc"),
                "rule_state": item.get("state_desc"),
                "window": {"start": str(rows[-duration].get("timestamp", latest_ts)), "end": latest_ts, "duration_points": duration, "is_ongoing": True},
                "snapshot_timestamp": latest_ts,
                "trend": (feature_map.get(tag) or {}).get("trend", "stable"),
                "membership_degree": item.get("membership_degree"),
                "ai_reason": "",
                "assessment_reason": item.get("assessment_reason", ""),
                "comparison_summary": item.get("comparison_summary", ""),
                "standby_context": item.get("standby_context") or {},
                "reference_label": item.get("reference_label"),
                "reference_value": item.get("reference_value"),
                "reference_source_type": item.get("reference_source_type"),
                "reference_source_label": item.get("reference_source_label"),
                "reference_scope": item.get("reference_scope"),
                "comparison_method": item.get("comparison_method"),
                "reference_basis_kind": item.get("reference_basis_kind"),
                "reference_basis_text": item.get("reference_basis_text"),
                "applicable_scope": item.get("applicable_scope"),
                "applicable_conditions": item.get("applicable_conditions"),
                "reference_owner": item.get("reference_owner"),
                "last_reviewed_at": item.get("last_reviewed_at"),
                "validation_status": item.get("validation_status"),
                "state_rule_trace": item.get("state_rule_trace") or {},
                "selected_regime": statistical_lane.get("selected_regime"),
                "regime_sample_count": statistical_lane.get("regime_sample_count"),
                "global_sample_count": statistical_lane.get("global_sample_count"),
                "robust_z_score": statistical_lane.get("robust_z_score"),
                "directed_tail_score": statistical_lane.get("directed_tail_score"),
                "statistical_persistence_points": statistical_lane.get("persistence_points"),
                "statistical_persistence_score": statistical_lane.get("persistence_score"),
                "statistical_anomaly_score": statistical_lane.get("statistical_anomaly_score"),
                "statistical_state": statistical_lane.get("statistical_state"),
                "agreement_flag": statistical_lane.get("agreement_flag"),
                "hybrid_severity_score": statistical_lane.get("hybrid_severity_score"),
            }
            detail["rule_reason"] = self._build_rule_reason(detail, len(rows))
            detail["severity_breakdown"] = severity_breakdown
            detail["severity_score"] = float(severity_breakdown.get("severity_score") or 0.0)
            detail["reference_context"] = {
                "source_type": detail.get("reference_source_type"),
                "source_label": detail.get("reference_source_label"),
                "scope": detail.get("reference_scope"),
                "comparison_method": detail.get("comparison_method"),
                "reference_value": detail.get("reference_value"),
                "history_baseline": detail.get("history_baseline"),
                "optimal_reference": detail.get("optimal_reference"),
                "final_grade_basis": detail.get("final_grade_basis"),
                "final_grade_basis_label": detail.get("final_grade_basis_label"),
                "reference_basis_kind": detail.get("reference_basis_kind"),
                "reference_basis_text": detail.get("reference_basis_text"),
                "applicable_scope": detail.get("applicable_scope"),
                "applicable_conditions": detail.get("applicable_conditions"),
                "reference_owner": detail.get("reference_owner"),
                "last_reviewed_at": detail.get("last_reviewed_at"),
                "validation_status": detail.get("validation_status"),
            }
            detail["rule_trace"] = self._build_indicator_rule_trace(detail)
            detail["evidence_layers"] = self._build_indicator_evidence_layers(detail)
            out.append(detail)
        return sorted(out, key=lambda x: (-x.get("severity_score", 0), -abs(x.get("diff_percent") or 0), x.get("name") or ""))

    def _build_calculation_audit(
        self,
        *,
        semantic_data: List[Dict[str, Any]],
        abnormal_details: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]] = None,
        history_data: Optional[List[Dict[str, Any]]] = None,
        parsing_audit: Optional[Dict[str, Any]] = None,
        three_level: Optional[Dict[str, Any]] = None,
        status_level: str = "",
        status_text: str = "",
        explainability: Optional[Dict[str, Any]] = None,
        history_lane_map: Optional[Dict[str, Dict[str, Any]]] = None,
        risk_upgrade_applied: bool = False,
    ) -> Dict[str, Any]:
        semantic_data = semantic_data or []
        abnormal_details = abnormal_details or []
        baseline_profile = baseline_profile or {}
        baseline_map = ((baseline_profile or {}).get("per_tag") or {}) if isinstance(baseline_profile, dict) else {}
        abnormal_by_tag = {str(item.get("tag_id") or ""): item for item in abnormal_details if item.get("tag_id")}
        features = self.extract_features(history_data or [], baseline_profile=baseline_profile) if history_data else {}
        feature_map = self._feature_map(features)
        three_level = three_level or {}
        explainability = explainability or {}
        history_lane_map = history_lane_map or self._build_history_lane_map(
            semantic_data=semantic_data,
            history_data=history_data or [],
            baseline_profile=baseline_profile,
            abnormal_details=abnormal_details,
        )

        indicators: List[Dict[str, Any]] = []
        for item in semantic_data:
            tag = str(item.get("tag_id") or "")
            detail = abnormal_by_tag.get(tag) or {}
            baseline_row = baseline_map.get(tag) or {}
            lane = history_lane_map.get(tag) or {}
            current_value = self._safe_number(item.get("current_value"))
            target_reference = self._safe_number(detail.get("target_reference") if detail.get("target_reference") is not None else item.get("reference_value"))
            history_baseline = self._safe_number(detail.get("history_baseline") if detail.get("history_baseline") is not None else baseline_row.get("baseline_value"))
            optimal_reference = self._safe_number(detail.get("optimal_reference") if detail.get("optimal_reference") is not None else baseline_row.get("optimal_reference"))
            diff_percent = self._safe_number(detail.get("diff_percent"))
            if diff_percent is None:
                diff_percent = self._relative_diff_percent(current_value, target_reference)
            history_diff_percent = self._safe_number(detail.get("history_diff_percent"))
            if history_diff_percent is None:
                history_diff_percent = self._relative_diff_percent(current_value, history_baseline)
            optimal_diff_percent = self._safe_number(detail.get("optimal_diff_percent"))
            if optimal_diff_percent is None:
                optimal_diff_percent = self._relative_diff_percent(current_value, optimal_reference)
            severity_breakdown = detail.get("severity_breakdown") or {
                "level_score": 0.0,
                "diff_component": 0.0,
                "duration_component": 0.0,
                "duration_component_raw": 0.0,
                "duration_cap": float(self.severity_config["duration_cap"]),
                "duration_cap_applied": False,
                "severity_score": 0.0,
                "base_score_fallback": float(self.severity_config["base_score"]),
            }
            grade_basis = detail or self._grade_basis_metadata(target_reference is not None)
            indicators.append(
                {
                    "tag_id": tag,
                    "name": item.get("name"),
                    "objective": baseline_row.get("objective") or detail.get("objective"),
                    "objective_label": self._objective_label(str(baseline_row.get("objective") or detail.get("objective") or "range")),
                    "state_label": item.get("state_desc"),
                    "rule_state": item.get("state_desc"),
                    "current_value": current_value,
                    "target_reference": target_reference,
                    "history_baseline": history_baseline,
                    "historical_baseline": lane.get("historical_baseline", history_baseline),
                    "optimal_reference": optimal_reference,
                    "selected_regime": lane.get("selected_regime") or baseline_row.get("selected_regime"),
                    "regime_sample_count": lane.get("regime_sample_count") or baseline_row.get("regime_sample_count"),
                    "global_sample_count": lane.get("global_sample_count") or baseline_row.get("global_sample_count"),
                    "final_grade_basis": grade_basis.get("final_grade_basis") or grade_basis.get("basis"),
                    "final_grade_basis_label": grade_basis.get("final_grade_basis_label") or grade_basis.get("basis_label"),
                    "final_grade_basis_reason": grade_basis.get("final_grade_basis_reason") or grade_basis.get("basis_reason"),
                    "diff_ratio": self._safe_number(detail.get("diff_ratio") if detail.get("diff_ratio") is not None else item.get("diff_ratio")),
                    "diff_percent": diff_percent,
                    "history_diff_percent": history_diff_percent,
                    "optimal_diff_percent": optimal_diff_percent,
                    "history_percentile_rank": lane.get("percentile_rank"),
                    "percentile_rank": lane.get("percentile_rank"),
                    "trend": detail.get("trend") or (feature_map.get(tag) or {}).get("trend") or "stable",
                    "duration_points": int(self._safe_number((detail.get("window") or {}).get("duration_points")) or 0),
                    "statistical_persistence_points": lane.get("persistence_points", 0),
                    "severity_score": round(float(detail.get("severity_score") or 0.0), 4),
                    "severity_breakdown": severity_breakdown,
                    "state_rule_trace": detail.get("state_rule_trace") or item.get("state_rule_trace") or {},
                    "comparison_method": detail.get("comparison_method") or item.get("comparison_method"),
                    "reference_label": detail.get("reference_source_label") or item.get("reference_source_label") or item.get("reference_label"),
                    "standby_context": detail.get("standby_context") or item.get("standby_context") or lane.get("standby_context") or {},
                    "robust_z_score": lane.get("robust_z_score"),
                    "directed_tail_score": lane.get("directed_tail_score"),
                    "statistical_anomaly_score": lane.get("statistical_anomaly_score", 0.0),
                    "statistical_state": lane.get("statistical_state", "normal"),
                    "agreement_flag": lane.get("agreement_flag", "agree"),
                    "hybrid_severity_score": lane.get("hybrid_severity_score", round(float(detail.get("severity_score") or 0.0), 4)),
                }
            )

        subsystem_params = self._rule_parameters("subsystem_state")
        constrained = subsystem_params.get("constrained") or {}
        suboptimal = subsystem_params.get("suboptimal") or {}
        subsystems: List[Dict[str, Any]] = []
        for item in (three_level.get("subsystem_states") or []):
            abnormal_ratio = float(item.get("abnormal_ratio") or 0.0)
            avg_severity = float(item.get("avg_severity") or 0.0)
            triggered_by: List[str] = []
            if abnormal_ratio >= float(constrained.get("abnormal_ratio_gte")):
                triggered_by.append(f"abnormal_ratio>={float(constrained.get('abnormal_ratio_gte')):.2f}")
            if avg_severity >= float(constrained.get("avg_severity_gte")):
                triggered_by.append(f"avg_severity>={float(constrained.get('avg_severity_gte')):.2f}")
            if not triggered_by:
                if abnormal_ratio >= float(suboptimal.get("abnormal_ratio_gte")):
                    triggered_by.append(f"abnormal_ratio>={float(suboptimal.get('abnormal_ratio_gte')):.2f}")
                if avg_severity >= float(suboptimal.get("avg_severity_gte")):
                    triggered_by.append(f"avg_severity>={float(suboptimal.get('avg_severity_gte')):.2f}")
            members = item.get("members") or []
            member_tags = [str(member.get("tag_id") or "") for member in members if isinstance(member, dict)]
            member_lanes = [history_lane_map.get(tag) or {} for tag in member_tags]
            hybrid_scores = [float(lane.get("hybrid_severity_score") or 0.0) for lane in member_lanes]
            history_warning_count = sum(1 for lane in member_lanes if lane.get("statistical_state") in {"warning", "high"})
            conflict_indicator_count = sum(1 for lane in member_lanes if lane.get("agreement_flag") != "agree")
            subsystems.append(
                {
                    "name": item.get("name"),
                    "state": str(item.get("state") or "stable"),
                    "abnormal_count": int(item.get("abnormal_count") or 0),
                    "total_count": int(item.get("total_count") or 0),
                    "abnormal_ratio": round(abnormal_ratio, 4),
                    "avg_severity": round(avg_severity, 4),
                    "hybrid_avg_severity": round(sum(hybrid_scores) / len(hybrid_scores), 4) if hybrid_scores else 0.0,
                    "history_warning_count": history_warning_count,
                    "conflict_indicator_count": conflict_indicator_count,
                    "members": [member.get("name") for member in members if isinstance(member, dict) and member.get("name")],
                    "thresholds": {"constrained": constrained, "suboptimal": suboptimal},
                    "triggered_by": triggered_by,
                    "rule_lane": {"abnormal_ratio": round(abnormal_ratio, 4), "avg_severity": round(avg_severity, 4), "state": str(item.get("state") or "stable")},
                    "history_lane": {
                        "history_warning_count": history_warning_count,
                        "conflict_indicator_count": conflict_indicator_count,
                        "hybrid_avg_severity": round(sum(hybrid_scores) / len(hybrid_scores), 4) if hybrid_scores else 0.0,
                    },
                }
            )

        total_count = len(semantic_data)
        abnormal_count = len(abnormal_details)
        abnormal_ratio = abnormal_count / max(total_count, 1)
        max_severity = max((float(item.get("severity_score") or 0.0) for item in abnormal_details), default=0.0)
        hybrid_max_severity = max((float((history_lane_map.get(str(item.get("tag_id") or "")) or {}).get("hybrid_severity_score") or 0.0) for item in semantic_data), default=0.0)
        avg_optimal_gap = float((three_level or {}).get("avg_optimal_gap") or 0.0)
        risk_params = self._rule_parameters("risk_level")
        plant_params = self._rule_parameters("plant_state")
        dominant_explanation = (explainability.get("dominant_anomaly_explanation") or {}) if isinstance(explainability, dict) else {}
        plant_state = str(three_level.get("plant_state") or "unknown")
        history_warning_count = sum(1 for lane in history_lane_map.values() if lane.get("statistical_state") in {"warning", "high"})
        conflict_indicator_count = sum(1 for lane in history_lane_map.values() if lane.get("agreement_flag") != "agree")
        return {
            "data_intake": parsing_audit or {},
            "history_model_metadata": dict((baseline_profile or {}).get("history_model_metadata") or {}),
            "indicators": indicators,
            "subsystems": subsystems,
            "plant": {
                "abnormal_count": abnormal_count,
                "total_count": total_count,
                "abnormal_ratio": round(abnormal_ratio, 4),
                "max_severity": round(max_severity, 4),
                "hybrid_max_severity": round(hybrid_max_severity, 4),
                "avg_optimal_gap": round(avg_optimal_gap, 4),
                "risk_level": status_level,
                "risk_level_label": status_text,
                "risk_branch": status_level if status_level in {"critical", "warning", "attention", "stable"} else "attention",
                "risk_thresholds": risk_params,
                "plant_state": plant_state,
                "plant_state_label": three_level.get("plant_state_label"),
                "plant_state_branch": plant_state if plant_state in {"abnormal_unstable", "risk_rising", "optimizable", "optimal", "stable"} else "unknown",
                "plant_state_thresholds": plant_params,
                "main_contradiction": three_level.get("main_contradiction"),
                "history_warning_count": history_warning_count,
                "conflict_indicator_count": conflict_indicator_count,
                "risk_upgrade_applied": bool(risk_upgrade_applied),
                "rule_lane": {"abnormal_ratio": round(abnormal_ratio, 4), "max_severity": round(max_severity, 4), "risk_level": status_level},
                "history_lane": {"history_warning_count": history_warning_count, "conflict_indicator_count": conflict_indicator_count, "hybrid_max_severity": round(hybrid_max_severity, 4)},
                "dominant_anomaly": {
                    "indicator_name": (abnormal_details[0].get("name") if abnormal_details else None),
                    "candidate_label": dominant_explanation.get("candidate_label"),
                    "rank_explanation": dominant_explanation.get("rank_explanation"),
                    "temporal_precedence_explanation": dominant_explanation.get("temporal_precedence_explanation"),
                    "boundary": dominant_explanation.get("exclusion_boundary_explanation"),
                },
            },
        }

    def build_overall_operating_summary(
        self,
        semantic_data: List[Dict],
        abnormal_details: List[Dict],
        baseline_profile: Optional[Dict[str, Any]] = None,
        history_data: Optional[List[Dict[str, Any]]] = None,
        parsing_audit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        semantic_data = semantic_data or []
        abnormal_details = abnormal_details or []
        history_data = history_data or []
        baseline_profile = baseline_profile or self.build_baseline_profile(history_data)
        total = len(semantic_data)
        abnormal = len(abnormal_details)
        good_count = sum(1 for item in semantic_data if item.get("state_desc") in {"优秀", "良好", "待机备用"})
        normal_count = sum(1 for item in semantic_data if item.get("state_desc") == "一般")
        max_severity = max((float(item.get("severity_score") or 0.0) for item in abnormal_details), default=0.0)
        level = self._resolve_status_level(abnormal, total, max_severity)
        three_level = self._build_three_level_state_engine(
            semantic_data=semantic_data,
            abnormal_details=abnormal_details,
            baseline_profile=baseline_profile,
        )
        history_lane_map = self._build_history_lane_map(
            semantic_data=semantic_data,
            history_data=history_data,
            baseline_profile=baseline_profile,
            abnormal_details=abnormal_details,
        )
        history_metadata = dict((baseline_profile or {}).get("history_model_metadata") or {})
        hybrid_enabled = bool(history_metadata.get("hybrid_aggregation_enabled"))
        key_indicator_tags = set(history_metadata.get("key_indicator_tags") or [item.get("tag_id") for item in semantic_data if item.get("tag_id")])
        risk_upgrade_applied = False
        if hybrid_enabled:
            high_history_indicator = any(
                tag in key_indicator_tags
                and (lane.get("statistical_state") == "high")
                and int(lane.get("persistence_points") or 0) >= 6
                for tag, lane in history_lane_map.items()
            )
            if high_history_indicator and level != "critical":
                level = self._upgrade_status_level(level)
                risk_upgrade_applied = True
        level_text = self._status_level_text(level)
        risk_ratio = round(abnormal / total * 100.0, 1) if total > 0 else 0.0

        top_risks: List[str] = []
        for item in abnormal_details[:3]:
            name = item.get("name") or item.get("tag_id") or "未知指标"
            state = item.get("level") or item.get("state_desc") or "异常"
            diff_percent = self._safe_number(item.get("diff_percent"))
            duration = int(self._safe_number((item.get("window") or {}).get("duration_points")) or 0)
            duration_text = f"，持续 {duration} 个点" if duration > 1 else ""
            diff_text = self._format_signed_percent(diff_percent) if diff_percent is not None else "N/A"
            top_risks.append(f"{name}：{state}，偏差 {diff_text}{duration_text}")

        history_warning_count = sum(1 for lane in history_lane_map.values() if lane.get("statistical_state") in {"warning", "high"})
        conflict_indicator_count = sum(1 for lane in history_lane_map.values() if lane.get("agreement_flag") != "agree")
        summary = (
            f"本次共分析 {total} 个指标，识别异常 {abnormal} 个，异常占比 {risk_ratio:.1f}%。"
            f"规则车道判定风险等级为 {level_text}，装置状态为 {three_level.get('plant_state_label', '稳定')}。"
        )
        highlights: List[str] = [
            f"状态分布：较优/可接受 {good_count} 个，正常 {normal_count} 个，异常 {abnormal} 个。",
            f"历史统计车道：warning/high={history_warning_count}，规则/历史不一致={conflict_indicator_count}。",
        ]
        if risk_upgrade_applied:
            highlights.append("已启用历史增强风险升级：关键指标出现高统计异常且持续时间满足阈值，风险等级上调一档。")
        if top_risks:
            highlights.extend(top_risks)
        else:
            history_only = [
                item.get("name") or item.get("tag_id")
                for item in semantic_data
                if (history_lane_map.get(str(item.get("tag_id") or "")) or {}).get("agreement_flag") == "history_only"
            ]
            if history_only:
                highlights.append(f"规则侧暂未形成显式异常，但历史统计已提示关注：{history_only[:3]}。")
            else:
                highlights.append("当前规则车道和历史统计车道均未发现需要立即升级处置的新增异常。")
        highlights.extend(self._standby_highlights(semantic_data))
        action_hint = self._action_hint(level)
        highlights.append(action_hint)
        for line in (three_level.get("global_semantics") or [])[:2]:
            highlights.append(line)

        baseline_references = self._build_baseline_references(abnormal_details, baseline_profile=baseline_profile)
        reference_framework = self._build_reference_framework()
        state_aggregation_rules = self._build_state_aggregation_rules()
        triggered_rules = self._build_triggered_rules(
            abnormal_count=abnormal,
            total_count=total,
            max_severity=max_severity,
            level_text=level_text,
            three_level=three_level,
        )
        if risk_upgrade_applied:
            triggered_rules.append("历史统计升级规则：关键指标 statistical_state=high 且持续点数>=6，风险等级上调一档。")
        verification_loop = self._build_verification_loop(abnormal_details)
        evidence_layers = self._build_overall_evidence_layers(
            abnormal_details=abnormal_details,
            three_level=three_level,
            triggered_rules=triggered_rules,
            verification_loop=verification_loop,
        )
        explainability = {
            "reference_provenance": self._build_reference_provenance(abnormal_details),
            "rule_parameter_explanations": self._build_rule_parameter_explanations(
                abnormal_count=abnormal,
                total_count=total,
                max_severity=max_severity,
                status_level=level,
                status_text=level_text,
                three_level=three_level,
                abnormal_details=abnormal_details,
            ),
            "dominant_anomaly_explanation": self._build_dominant_anomaly_explanation(
                abnormal_details=abnormal_details,
                three_level=three_level,
            ),
            "history_model_metadata": history_metadata,
        }
        calculation_audit = self._build_calculation_audit(
            semantic_data=semantic_data,
            abnormal_details=abnormal_details,
            baseline_profile=baseline_profile,
            history_data=history_data,
            parsing_audit=parsing_audit,
            three_level=three_level,
            status_level=level,
            status_text=level_text,
            explainability=explainability,
            history_lane_map=history_lane_map,
            risk_upgrade_applied=risk_upgrade_applied,
        )
        return {
            "status_level": level,
            "status_text": level_text,
            "summary": summary,
            "highlights": highlights,
            "risk_points": top_risks,
            "risk_ratio": risk_ratio,
            "action_hint": action_hint,
            "total_count": total,
            "good_count": good_count,
            "normal_count": normal_count,
            "abnormal_count": abnormal,
            "three_level_state_engine": three_level,
            "plant_state": three_level.get("plant_state"),
            "plant_state_label": three_level.get("plant_state_label"),
            "optimization_priority": three_level.get("optimization_priority") or [],
            "main_contradiction": three_level.get("main_contradiction") or "",
            "subsystem_states": three_level.get("subsystem_states") or [],
            "reference_framework": reference_framework,
            "baseline_references": baseline_references,
            "state_aggregation_rules": state_aggregation_rules,
            "triggered_rules": triggered_rules,
            "evidence_layers": evidence_layers,
            "verification_loop": verification_loop,
            "explainability": explainability,
            "calculation_audit": calculation_audit,
            "history_model_metadata": history_metadata,
            "risk_upgrade_applied": risk_upgrade_applied,
            "explanation_boundary": "知识层仅用于补充候选解释、候选假设和动作边界，不能替代规则判级与历史统计证据。",
        }

    def apply_ai_assistance(self, semantic_data: List[Dict[str, Any]], abnormal_details: List[Dict[str, Any]], overall_judgement: Dict[str, Any], ask_model: Callable[[str, str, float], str], task_note: str = "") -> Dict[str, Any]:
        if not callable(ask_model):
            return {"used": False, "reason": "ask_model is not callable."}
        prompts = build_semantic_ai_review_prompts(semantic_data=semantic_data or [], abnormal_details=abnormal_details or [], overall_judgement=overall_judgement or {}, task_note=task_note or "")
        raw_text = ask_model(prompts["system_prompt"], prompts["user_prompt"], 0.1)
        payload = extract_json_object(raw_text)
        if not isinstance(payload, dict):
            return {"used": False, "reason": "AI did not return valid JSON.", "raw_response": raw_text}
        reviews = payload.get("state_reviews") if isinstance(payload.get("state_reviews"), list) else []
        review_map = {}
        for review in reviews:
            if isinstance(review, dict):
                key = self._normalize_match_key(review.get("tag_id")) or self._normalize_match_key(review.get("name"))
                if key:
                    review_map[key] = review

        abnormal_map = {}
        for detail in abnormal_details or []:
            key = self._normalize_match_key(detail.get("tag_id")) or self._normalize_match_key(detail.get("name"))
            if key:
                abnormal_map[key] = detail

        reviews_applied = 0
        for item in semantic_data:
            key = self._normalize_match_key(item.get("tag_id")) or self._normalize_match_key(item.get("name"))
            review = review_map.get(key)
            if review:
                item["ai_state_desc"] = repair_llm_text(review.get("suggested_state"))
                item["ai_state_reason"] = repair_llm_text(review.get("reason"))
                item["ai_confidence"] = review.get("confidence")
                reason_text = str(repair_llm_text(review.get("reason") or "")).strip()
                if reason_text and key in abnormal_map:
                    abnormal_map[key]["ai_reason"] = reason_text
                reviews_applied += 1

        summary_refinement = str(repair_llm_text(payload.get("summary_refinement") or "")).strip()
        if summary_refinement and isinstance(overall_judgement, dict):
            base_summary = str(overall_judgement.get("summary") or "").strip()
            if base_summary:
                overall_judgement["summary"] = f"{base_summary} | AI复核：{summary_refinement}"
            else:
                overall_judgement["summary"] = f"AI复核：{summary_refinement}"

        highlights_refinement = payload.get("highlights_refinement")
        if isinstance(highlights_refinement, list) and isinstance(overall_judgement, dict):
            merged_highlights = list(overall_judgement.get("highlights") or [])
            merged_highlights.extend(
                [str(repair_llm_text(item)).strip() for item in highlights_refinement if str(repair_llm_text(item)).strip()]
            )
            overall_judgement["highlights"] = merged_highlights

        return {
            "used": True,
            "reviews_applied": reviews_applied,
            "summary_refinement": summary_refinement,
            "risk_focus": (
                [repair_llm_text(item) for item in payload.get("risk_focus", [])]
                if isinstance(payload.get("risk_focus"), list)
                else []
            ),
            "raw_response": raw_text,
        }

    def calculate_core_indicators(self, semantic_data: List[Dict]) -> CoreIndicatorsModel:
        extraction, stability, energy = {}, {}, {}
        for item in semantic_data or []:
            tag = item.get("tag_id", "unknown")
            name = str(item.get("name", ""))
            payload = {"value": item.get("current_value"), "membership": item.get("membership_degree", 0.0), "state": item.get("state_desc", "Unknown")}
            low = name.lower()
            if "extract" in low or "提取" in name:
                extraction[tag] = payload
            elif "stable" in low or "稳定" in name:
                stability[tag] = payload
            elif "energy" in low or "能耗" in name or "电" in name:
                energy[tag] = payload
        return CoreIndicatorsModel(extraction_rate=extraction, stability=stability, energy_consumption=energy)

    def _get_metric_design_value(self, metric_code: str) -> Optional[Dict]:
        return {
            "Pump_Loss_kW": {"design_value": 50.0, "min_value": 0.0, "max_value": 100.0},
            "ExpanderCold_kW": {"design_value": 1000.0, "min_value": 900.0, "max_value": 1100.0},
            "TotalColdLoss_kW": {"design_value": 200.0, "min_value": 0.0, "max_value": 300.0},
            "ColdLossRatio": {"design_value": 0.2, "min_value": 0.0, "max_value": 0.4},
        }.get(metric_code)

    def process_asu_derived_metrics(self, derived_data: List[ASUDerivedResultModel]) -> List[Dict]:
        out: List[Dict[str, Any]] = []
        for item in derived_data or []:
            metric_info = self._get_metric_design_value(item.metric_code)
            if metric_info:
                design = metric_info.get("design_value", item.value)
                min_value = metric_info.get("min_value", item.value * 0.95)
                max_value = metric_info.get("max_value", item.value * 1.05)
                membership = self.calculate_membership(item.value, design, min_value, max_value)
                state = self.get_semantic_state(membership)
                out.append({"name": item.metric_code, "current_value": item.value, "state_desc": state, "diff": item.value - design, "membership_degree": membership, "quality_flags": item.quality_flags})
            else:
                out.append({"name": item.metric_code, "current_value": item.value, "state_desc": "Unknown", "diff": 0.0, "membership_degree": 0.0, "quality_flags": item.quality_flags})
        return out
