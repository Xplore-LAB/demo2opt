from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_CARD_LIMIT = 3
DEFAULT_OVERVIEW_SERIES_LIMIT = 180
DATA_CURVE_CATEGORY_META: Tuple[Dict[str, Any], ...] = (
    {
        "key": "cooling_capacity",
        "title": "制冷量",
        "description": "查看膨胀机、冷量供给与制冷能力相关指标的整体走势。",
        "keywords": ("制冷量", "冷量", "膨胀机", "膨胀量", "expander"),
    },
    {
        "key": "loss_energy",
        "title": "冷损（能耗）",
        "description": "查看主换、冷箱、泵耗与单耗等冷损和能耗相关指标。",
        "keywords": ("冷损", "冷耗", "主换", "主换热", "冷箱", "单耗", "能耗", "电耗", "气耗", "汽耗", "蒸汽", "水耗", "泵", "压缩机"),
    },
    {
        "key": "extraction",
        "title": "提取",
        "description": "查看提取率、回收率、纯度与产品产量相关指标的历史曲线。",
        "keywords": ("提取", "收率", "回收", "纯度", "提纯", "产量", "液氧产量", "液氩产量", "液氮产量", "氧提取", "氩提取", "氮提取"),
    },
    {
        "key": "load",
        "title": "负荷",
        "description": "查看负荷、处理量、吞吐与关键流量水平。",
        "keywords": ("负荷", "处理量", "进气量", "流量", "空压", "增压机", "吞吐"),
    },
    {
        "key": "other",
        "title": "其他",
        "description": "未命中上述四类的剩余指标。",
        "keywords": (),
    },
)


@dataclass
class _SeriesPoint:
    timestamp: str
    value: float
    unit: str
    name: str = ""


class TimeComparisonVisualizationService:
    def __init__(self, card_limit: int = DEFAULT_CARD_LIMIT):
        self.card_limit = max(1, int(card_limit or DEFAULT_CARD_LIMIT))
        self.overview_series_limit = DEFAULT_OVERVIEW_SERIES_LIMIT

    def build_visualization_context(
        self,
        *,
        standardized_data: List[Dict[str, Any]],
        latest_timestamp: Optional[str],
        abnormal_details: List[Dict[str, Any]],
        baseline_profile: Optional[Dict[str, Any]] = None,
        asset_dir: Optional[Path] = None,
        asset_prefix: str = "",
    ) -> Dict[str, Any]:
        if not standardized_data:
            return {"generated_at": datetime.now().isoformat(), "data_curve_overview": {}, "overview_card": {}, "top_indicator_cards": []}

        series_by_tag = self._build_series_by_tag(standardized_data)
        if not series_by_tag:
            return {"generated_at": datetime.now().isoformat(), "data_curve_overview": {}, "overview_card": {}, "top_indicator_cards": []}

        cards: List[Dict[str, Any]] = []
        ranked_details = sorted(
            list(abnormal_details or []),
            key=lambda item: (
                -float(item.get("severity_score") or 0.0),
                -abs(float(item.get("diff_percent") or 0.0)),
                str(item.get("name") or item.get("tag_id") or ""),
            ),
        )
        for index, detail in enumerate(ranked_details[: self.card_limit], start=1):
            card = self._build_indicator_card(
                rank=index,
                detail=detail,
                latest_timestamp=latest_timestamp,
                baseline_profile=baseline_profile or {},
                series_by_tag=series_by_tag,
                asset_dir=asset_dir,
                asset_prefix=asset_prefix,
            )
            if card:
                cards.append(card)

        return {
            "generated_at": datetime.now().isoformat(),
            "data_curve_overview": self._build_data_curve_overview(
                series_by_tag=series_by_tag,
                latest_timestamp=latest_timestamp,
                abnormal_details=abnormal_details,
                baseline_profile=baseline_profile or {},
            ),
            "overview_card": self._build_overview_card(cards),
            "top_indicator_cards": cards,
        }

    def _build_series_by_tag(self, standardized_data: Sequence[Dict[str, Any]]) -> Dict[str, List[_SeriesPoint]]:
        grouped: Dict[str, List[_SeriesPoint]] = {}
        for row in standardized_data or []:
            tag_id = str(row.get("tag_id") or "").strip()
            timestamp = str(row.get("timestamp") or "").strip()
            value = self._safe_float(row.get("value"))
            if not tag_id or not timestamp or value is None:
                continue
            grouped.setdefault(tag_id, []).append(
                _SeriesPoint(
                    timestamp=timestamp,
                    value=value,
                    unit=str(row.get("unit") or "").strip(),
                    name=str(row.get("name") or "").strip(),
                )
            )
        for tag_id, items in grouped.items():
            grouped[tag_id] = sorted(items, key=lambda item: item.timestamp)
        return grouped

    def _build_indicator_card(
        self,
        *,
        rank: int,
        detail: Dict[str, Any],
        latest_timestamp: Optional[str],
        baseline_profile: Dict[str, Any],
        series_by_tag: Dict[str, List[_SeriesPoint]],
        asset_dir: Optional[Path],
        asset_prefix: str,
    ) -> Optional[Dict[str, Any]]:
        tag_id = str(detail.get("tag_id") or "").strip()
        if not tag_id:
            return None
        series = list(series_by_tag.get(tag_id) or [])
        if not series:
            return None

        latest_idx = self._resolve_latest_index(series, latest_timestamp)
        latest_point = series[latest_idx]
        history_before = [point.value for point in series[:latest_idx]]
        history_sample = history_before or [point.value for point in series]
        if not history_sample:
            return None

        current_value = self._safe_float(detail.get("current_value"))
        if current_value is None:
            current_value = latest_point.value
        unit = latest_point.unit
        stats = self._build_history_stats(current_value=current_value, history_values=history_sample)
        references = self._build_references(detail, baseline_profile)
        comparison_deltas = {
            "vs_target": self._delta_payload(current_value, references.get("target_reference")),
            "vs_history_median": self._delta_payload(current_value, stats.get("median")),
            "vs_optimal": self._delta_payload(current_value, references.get("optimal_reference")),
        }

        duration_points = int(self._safe_float(((detail.get("window") or {}).get("duration_points"))) or 0)
        window_point_count = min(max(24, duration_points + 4), 96)
        recent_start_idx = max(0, latest_idx - window_point_count + 1)
        recent_series = series[recent_start_idx : latest_idx + 1]

        abnormal_window = detail.get("window") or {}
        abnormal_start = str(abnormal_window.get("start") or series[max(0, latest_idx - max(duration_points - 1, 0))].timestamp)
        abnormal_end = str(abnormal_window.get("end") or latest_point.timestamp)
        abnormal_start_idx = self._find_timestamp_index(series, abnormal_start, default=max(0, latest_idx - max(duration_points - 1, 0)))
        abnormal_end_idx = self._find_timestamp_index(series, abnormal_end, default=latest_idx)
        if abnormal_end_idx < abnormal_start_idx:
            abnormal_end_idx = latest_idx

        recent_timestamps = [point.timestamp for point in recent_series]
        recent_values = [point.value for point in recent_series]
        recent_abnormal_mask = [
            bool(recent_start_idx + offset >= abnormal_start_idx and recent_start_idx + offset <= abnormal_end_idx)
            for offset in range(len(recent_series))
        ]
        abnormal_start_outside_window = abnormal_start_idx < recent_start_idx
        key_points = self._build_key_points(
            values=recent_values,
            recent_start_idx=recent_start_idx,
            abnormal_start_idx=abnormal_start_idx,
        )
        chart_display = self._build_chart_display(
            values=recent_values,
            stats=stats,
            references=references,
            key_points=key_points,
        )
        summary_rows = self._build_summary_rows(
            current_value=current_value,
            unit=unit,
            comparison_deltas=comparison_deltas,
            abnormal_start=abnormal_start,
            duration_points=duration_points,
        )

        insight_text = self._build_insight_text(
            detail=detail,
            current_value=current_value,
            stats=stats,
            references=references,
            comparison_deltas=comparison_deltas,
            abnormal_start=abnormal_start,
            duration_points=duration_points,
            abnormal_start_outside_window=abnormal_start_outside_window,
        )

        card: Dict[str, Any] = {
            "rank": rank,
            "tag_id": tag_id,
            "indicator_name": str(detail.get("name") or tag_id),
            "unit": unit,
            "current_value": current_value,
            "latest_timestamp": latest_point.timestamp,
            "severity_score": self._safe_float(detail.get("severity_score")) or 0.0,
            "state_desc": str(detail.get("level") or detail.get("state_desc") or "异常"),
            "references": references,
            "history_stats": stats,
            "comparison_deltas": comparison_deltas,
            "full_timeline": {
                "series_start": series[0].timestamp,
                "series_end": series[-1].timestamp,
                "abnormal_start": abnormal_start,
                "abnormal_end": abnormal_end,
                "abnormal_start_ratio": self._ratio(abnormal_start_idx, len(series)),
                "abnormal_end_ratio": self._ratio(abnormal_end_idx, len(series)),
                "current_ratio": self._ratio(latest_idx, len(series)),
                "series_point_count": len(series),
            },
            "recent_trend": {
                "timestamps": recent_timestamps,
                "values": recent_values,
                "abnormal_mask": recent_abnormal_mask,
                "window_start": recent_timestamps[0] if recent_timestamps else "",
                "window_end": recent_timestamps[-1] if recent_timestamps else "",
                "window_point_count": len(recent_timestamps),
                "abnormal_start_outside_window": abnormal_start_outside_window,
                "reference_lines": {
                    "target_reference": references.get("target_reference"),
                    "history_baseline": references.get("history_baseline"),
                    "optimal_reference": references.get("optimal_reference"),
                    "history_p10": stats.get("p10"),
                    "history_p90": stats.get("p90"),
                },
                "key_points": key_points,
                "chart_display": chart_display,
            },
            "insight_text": insight_text,
            "summary_rows": summary_rows,
        }

        if asset_dir is not None:
            image_info = self._render_card_image(
                card=card,
                asset_dir=asset_dir,
                asset_prefix=asset_prefix,
            )
            card.update(image_info)
        return card

    def _build_history_stats(self, *, current_value: float, history_values: List[float]) -> Dict[str, Any]:
        ordered = sorted(history_values)
        return {
            "min": ordered[0],
            "p10": self._percentile(ordered, 0.10),
            "median": self._percentile(ordered, 0.50),
            "p90": self._percentile(ordered, 0.90),
            "max": ordered[-1],
            "percentile_rank": self._percentile_rank(current_value, ordered),
            "sample_count": len(ordered),
        }

    def _build_overview_card(self, cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        selected_cards = [card for card in cards if isinstance(card, dict)]
        if not selected_cards:
            return {}

        timestamps = sorted(
            {
                str(timestamp)
                for card in selected_cards
                for timestamp in ((card.get("recent_trend") or {}).get("timestamps") or [])
                if timestamp
            }
        )
        if not timestamps:
            return {}

        series_rows: List[Dict[str, Any]] = []
        all_values: List[float] = [0.0]
        abnormal_starts = [
            str((card.get("full_timeline") or {}).get("abnormal_start") or "").strip()
            for card in selected_cards
            if str((card.get("full_timeline") or {}).get("abnormal_start") or "").strip()
        ]
        abnormal_start = min(abnormal_starts) if abnormal_starts else ""

        for card in selected_cards:
            recent_trend = card.get("recent_trend") or {}
            raw_timestamps = [str(timestamp) for timestamp in (recent_trend.get("timestamps") or []) if timestamp]
            raw_values = [self._safe_float(value) for value in (recent_trend.get("values") or [])]
            if not raw_timestamps or not raw_values:
                continue

            reference_value, reference_label = self._resolve_overview_reference(card)
            value_map = {
                raw_timestamps[index]: raw_values[index]
                for index in range(min(len(raw_timestamps), len(raw_values)))
                if raw_values[index] is not None
            }
            values_percent = [self._normalize_relative_percent(value_map.get(timestamp), reference_value) for timestamp in timestamps]
            all_values.extend([value for value in values_percent if value is not None])
            current_relative = next((value for value in reversed(values_percent) if value is not None), None)
            series_rows.append(
                {
                    "tag_id": str(card.get("tag_id") or ""),
                    "indicator_name": str(card.get("indicator_name") or card.get("tag_id") or "未命名指标"),
                    "unit": str(card.get("unit") or ""),
                    "severity_score": self._safe_float(card.get("severity_score")) or 0.0,
                    "state_desc": str(card.get("state_desc") or "异常"),
                    "current_value": self._safe_float(card.get("current_value")),
                    "reference_value": reference_value,
                    "reference_label": reference_label,
                    "current_relative_percent": current_relative,
                    "values_percent": values_percent,
                }
            )

        if not series_rows:
            return {}

        return {
            "title": "运行趋势总览",
            "window_start": timestamps[0],
            "window_end": timestamps[-1],
            "latest_timestamp": timestamps[-1],
            "window_point_count": len(timestamps),
            "indicator_count": len(series_rows),
            "abnormal_start": abnormal_start,
            "y_axis_label": "相对参考偏差 (%)",
            "series": series_rows,
            "chart_display": {
                **self._build_overview_chart_display(all_values),
                "abnormal_start_index": timestamps.index(abnormal_start) if abnormal_start in timestamps else None,
                "latest_index": len(timestamps) - 1,
            },
            "insight_lines": [
                "0% 表示贴近各自参考值，负值表示低于参考，正值表示高于参考。",
                "总览图用于先看整体曲线，再下钻到单指标详细图，不直接用于根因确认。",
            ],
            "timestamps": timestamps,
        }

    def _build_data_curve_overview(
        self,
        *,
        series_by_tag: Dict[str, List[_SeriesPoint]],
        latest_timestamp: Optional[str],
        abnormal_details: Sequence[Dict[str, Any]],
        baseline_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not series_by_tag:
            return {}

        abnormal_by_tag = {
            str(item.get("tag_id") or "").strip(): item
            for item in (abnormal_details or [])
            if str(item.get("tag_id") or "").strip()
        }
        baseline_map = (baseline_profile or {}).get("per_tag") or {}
        grouped_items: Dict[str, List[Dict[str, Any]]] = {meta["key"]: [] for meta in DATA_CURVE_CATEGORY_META}

        min_timestamp = ""
        max_timestamp = ""
        for tag_id, series in series_by_tag.items():
            if not series:
                continue
            latest_idx = self._resolve_latest_index(series, latest_timestamp)
            latest_point = series[latest_idx]
            abnormal = abnormal_by_tag.get(tag_id) or {}
            indicator_name = str(latest_point.name or abnormal.get("name") or tag_id or "未命名指标")
            category_key = self._classify_data_curve_category(tag_id, indicator_name)
            baseline_row = baseline_map.get(tag_id) or {}
            reference_value, reference_label = self._resolve_data_curve_reference(
                abnormal_detail=abnormal,
                baseline_row=baseline_row,
            )
            display_series = self._downsample_series(series, self.overview_series_limit)
            timestamps = [point.timestamp for point in display_series]
            values = [point.value for point in display_series]
            if not timestamps or not values:
                continue

            min_timestamp = timestamps[0] if not min_timestamp else min(min_timestamp, timestamps[0])
            max_timestamp = timestamps[-1] if not max_timestamp else max(max_timestamp, timestamps[-1])

            abnormal_start = str(((abnormal.get("window") or {}).get("start")) or "").strip()
            chart_display = self._build_data_curve_chart_display(values=values, reference_value=reference_value)
            current_value = self._safe_float(abnormal.get("current_value"))
            if current_value is None:
                current_value = latest_point.value

            grouped_items.setdefault(category_key, []).append(
                {
                    "tag_id": tag_id,
                    "indicator_name": indicator_name,
                    "unit": latest_point.unit,
                    "state_desc": str(abnormal.get("level") or abnormal.get("state_desc") or "未见异常"),
                    "severity_score": self._safe_float(abnormal.get("severity_score")) or 0.0,
                    "current_value": current_value,
                    "reference_value": reference_value,
                    "reference_label": reference_label,
                    "current_delta_percent": self._normalize_relative_percent(current_value, reference_value),
                    "time_range_start": timestamps[0],
                    "time_range_end": timestamps[-1],
                    "point_count": len(series),
                    "display_point_count": len(display_series),
                    "abnormal_start": abnormal_start,
                    "summary": self._build_series_summary(values),
                    "chart": {
                        "timestamps": timestamps,
                        "values": values,
                        "current_index": len(values) - 1,
                        "abnormal_start_index": self._find_abnormal_start_index(display_series, abnormal_start),
                        "display": chart_display,
                    },
                }
            )

        categories: List[Dict[str, Any]] = []
        sorted_load_items = sorted(
            grouped_items.get("load") or [],
            key=lambda item: (
                -(item.get("severity_score") or 0.0),
                str(item.get("indicator_name") or ""),
            ),
        )
        for meta in DATA_CURVE_CATEGORY_META:
            items = grouped_items.get(meta["key"]) or []
            if not items:
                continue
            sorted_items = sorted(
                items,
                key=lambda item: (
                    -(item.get("severity_score") or 0.0),
                    str(item.get("indicator_name") or ""),
                ),
            )
            categories.append(
                {
                    "key": meta["key"],
                    "title": meta["title"],
                    "description": meta["description"],
                    "indicator_count": len(sorted_items),
                    "abnormal_count": sum(1 for item in sorted_items if (item.get("severity_score") or 0.0) > 0),
                    "load_context_items": list(sorted_load_items) if meta["key"] not in {"load", "other"} else [],
                    "items": sorted_items,
                }
            )

        if not categories:
            return {}

        return {
            "title": "数据曲线总览",
            "description": "先按业务主题浏览全量曲线，再展开单个指标查看完整历史趋势。",
            "time_range_start": min_timestamp,
            "time_range_end": max_timestamp,
            "latest_timestamp": latest_timestamp or max_timestamp,
            "category_count": len(categories),
            "indicator_count": sum(len(category.get("items") or []) for category in categories),
            "categories": categories,
        }

    def _classify_data_curve_category(self, tag_id: str, indicator_name: str) -> str:
        normalized_name = str(indicator_name or "").lower().replace(" ", "")
        normalized_tag = str(tag_id or "").lower().replace(" ", "")
        priority_keys = ("load", "extraction", "loss_energy", "cooling_capacity")

        def _matches(meta: Dict[str, Any], haystack: str) -> bool:
            keywords = meta.get("keywords") or ()
            return any(str(keyword).lower().replace(" ", "") in haystack for keyword in keywords)

        for key in priority_keys:
            meta = next((item for item in DATA_CURVE_CATEGORY_META if item["key"] == key), None)
            if meta and _matches(meta, normalized_name):
                return str(meta["key"])

        for key in priority_keys:
            meta = next((item for item in DATA_CURVE_CATEGORY_META if item["key"] == key), None)
            if meta and _matches(meta, normalized_tag):
                return str(meta["key"])
        return "other"

    def _resolve_data_curve_reference(
        self,
        *,
        abnormal_detail: Dict[str, Any],
        baseline_row: Dict[str, Any],
    ) -> Tuple[Optional[float], str]:
        candidates = (
            (
                abnormal_detail.get("target_reference")
                if abnormal_detail.get("target_reference") is not None
                else abnormal_detail.get("reference_value"),
                "目标参考",
            ),
            (baseline_row.get("baseline_value"), "历史基线"),
            (baseline_row.get("optimal_reference"), "优态参考"),
        )
        for value, label in candidates:
            numeric = self._safe_float(value)
            if numeric is not None and math.isfinite(numeric):
                return numeric, label
        return None, "未设参考"

    def _downsample_series(self, series: Sequence[_SeriesPoint], limit: int) -> List[_SeriesPoint]:
        if limit <= 0 or len(series) <= limit:
            return list(series)
        step = max(1, int(math.ceil(len(series) / float(limit))))
        sampled = list(series[::step])
        if sampled[-1].timestamp != series[-1].timestamp:
            sampled.append(series[-1])
        return sampled[-limit:]

    def _build_series_summary(self, values: Sequence[float]) -> Dict[str, Optional[float]]:
        numeric_values = [float(value) for value in values if value is not None and math.isfinite(float(value))]
        if not numeric_values:
            return {"min": None, "max": None, "median": None}
        ordered = sorted(numeric_values)
        return {
            "min": round(min(ordered), 6),
            "max": round(max(ordered), 6),
            "median": round(self._percentile(ordered, 0.5) or ordered[len(ordered) // 2], 6),
        }

    def _find_abnormal_start_index(self, series: Sequence[_SeriesPoint], abnormal_start: str) -> Optional[int]:
        if not abnormal_start:
            return None
        for index, point in enumerate(series):
            if point.timestamp >= abnormal_start:
                return index
        return None

    def _build_data_curve_chart_display(
        self,
        *,
        values: Sequence[float],
        reference_value: Optional[float],
    ) -> Dict[str, Any]:
        numeric_values = [float(value) for value in values if value is not None and math.isfinite(float(value))]
        if not numeric_values:
            return {
                "plot_min": 0.0,
                "plot_max": 1.0,
                "visible_reference_line": None,
                "reference_note": "",
            }

        value_min = min(numeric_values)
        value_max = max(numeric_values)
        spread = max(value_max - value_min, max(abs(value_max), abs(value_min)) * 0.12, 1.0)
        padding = max(spread * 0.18, 0.8)
        plot_min = value_min - padding
        plot_max = value_max + padding
        if value_min >= 0:
            plot_min = max(0.0, plot_min)

        visible_reference_line = None
        reference_note = ""
        reference_numeric = self._safe_float(reference_value)
        if reference_numeric is not None:
            upper_guard = plot_max + spread * 0.45
            lower_guard = plot_min - spread * 0.45
            if lower_guard <= reference_numeric <= upper_guard:
                visible_reference_line = reference_numeric
            else:
                reference_note = f"参考线 {self._format_number(reference_numeric)} 超出当前图窗，已保留在卡片摘要中"

        return {
            "plot_min": round(plot_min, 6),
            "plot_max": round(plot_max, 6),
            "visible_reference_line": visible_reference_line,
            "reference_note": reference_note,
        }

    def _build_references(self, detail: Dict[str, Any], baseline_profile: Dict[str, Any]) -> Dict[str, Optional[float]]:
        baseline_map = (baseline_profile or {}).get("per_tag") or {}
        baseline_row = baseline_map.get(detail.get("tag_id")) or {}
        history_baseline = self._safe_float(
            detail.get("history_baseline")
            if detail.get("history_baseline") is not None
            else detail.get("baseline_value")
        )
        return {
            "target_reference": self._safe_float(
                detail.get("target_reference")
                if detail.get("target_reference") is not None
                else detail.get("reference_value")
            ),
            "history_baseline": history_baseline if history_baseline is not None else self._safe_float(baseline_row.get("baseline_value")),
            "optimal_reference": self._safe_float(
                detail.get("optimal_reference")
                if detail.get("optimal_reference") is not None
                else baseline_row.get("optimal_reference")
            ),
        }

    def _build_key_points(
        self,
        *,
        values: Sequence[float],
        recent_start_idx: int,
        abnormal_start_idx: int,
    ) -> Dict[str, Optional[int]]:
        if not values:
            return {
                "abnormal_start_index": None,
                "lowest_index": None,
                "current_index": None,
            }

        lowest_index = min(range(len(values)), key=lambda index: values[index])
        abnormal_start_index = abnormal_start_idx - recent_start_idx
        if abnormal_start_index < 0 or abnormal_start_index >= len(values):
            abnormal_start_index = None
        return {
            "abnormal_start_index": abnormal_start_index,
            "lowest_index": lowest_index,
            "current_index": len(values) - 1,
        }

    def _build_chart_display(
        self,
        *,
        values: Sequence[float],
        stats: Dict[str, Any],
        references: Dict[str, Optional[float]],
        key_points: Dict[str, Optional[int]],
    ) -> Dict[str, Any]:
        focus_values: List[float] = [float(value) for value in values if value is not None]
        for candidate in (stats.get("median"), references.get("history_baseline")):
            numeric = self._safe_float(candidate)
            if numeric is not None:
                focus_values.append(numeric)

        if not focus_values:
            focus_values = [0.0, 1.0]

        focus_min = min(focus_values)
        focus_max = max(focus_values)
        spread = max(focus_max - focus_min, abs(focus_max) * 0.15, 1.0)
        padding = max(spread * 0.18, 0.8)
        plot_min = focus_min - padding
        plot_max = focus_max + padding
        if focus_min >= 0:
            plot_min = max(0.0, plot_min)

        visible_reference_lines: Dict[str, Optional[float]] = {
            "history_p10": None,
            "history_p90": None,
            "history_baseline": self._safe_float(references.get("history_baseline")),
            "target_reference": None,
            "optimal_reference": None,
        }
        reference_notes: List[str] = []
        history_p10 = self._safe_float(stats.get("p10"))
        history_p90 = self._safe_float(stats.get("p90"))
        if history_p10 is not None and history_p90 is not None and plot_min <= history_p10 <= plot_max and plot_min <= history_p90 <= plot_max:
            visible_reference_lines["history_p10"] = history_p10
            visible_reference_lines["history_p90"] = history_p90
        elif history_p10 is not None or history_p90 is not None:
            reference_notes.append("历史区间跨度较大，主图改为仅显示历史中位")

        target_reference = self._safe_float(references.get("target_reference"))
        if target_reference is not None:
            if plot_min <= target_reference <= plot_max:
                visible_reference_lines["target_reference"] = target_reference
            else:
                direction = "高于" if target_reference > plot_max else "低于"
                reference_notes.append(f"目标参考 {self._format_number(target_reference)} {direction}当前图窗")

        optimal_reference = self._safe_float(references.get("optimal_reference"))
        if optimal_reference is not None:
            direction = "高于" if optimal_reference > plot_max else "低于" if optimal_reference < plot_min else "接近"
            if direction == "接近":
                reference_notes.append(f"优态参考 {self._format_number(optimal_reference)} 已保留在指标卡，不再压缩主图")
            else:
                reference_notes.append(f"优态参考 {self._format_number(optimal_reference)} {direction}当前图窗，仅保留在指标卡")

        return {
            "plot_min": round(plot_min, 6),
            "plot_max": round(plot_max, 6),
            "visible_reference_lines": visible_reference_lines,
            "reference_notes": reference_notes,
            "key_points": key_points,
        }

    def _build_summary_rows(
        self,
        *,
        current_value: float,
        unit: str,
        comparison_deltas: Dict[str, Dict[str, Optional[float]]],
        abnormal_start: str,
        duration_points: int,
    ) -> List[Dict[str, str]]:
        return [
            {"label": "当前值", "value": f"{self._format_number(current_value)}{f' {unit}' if unit else ''}"},
            {"label": "相对目标", "value": self._format_percent((comparison_deltas.get("vs_target") or {}).get("percent"))},
            {"label": "异常起点", "value": self._compact_timestamp(abnormal_start)},
            {"label": "持续时长", "value": f"{duration_points} 个采样点" if duration_points > 0 else "当前窗口内未识别"},
        ]

    def _delta_payload(self, current: Optional[float], reference: Optional[float]) -> Dict[str, Optional[float]]:
        if current is None or reference is None:
            return {"value": None, "percent": None}
        delta = current - reference
        percent = None
        if abs(reference) > 1e-6:
            percent = delta / abs(reference) * 100.0
        return {"value": round(delta, 6), "percent": round(percent, 4) if percent is not None else None}

    def _build_insight_text(
        self,
        *,
        detail: Dict[str, Any],
        current_value: float,
        stats: Dict[str, Any],
        references: Dict[str, Optional[float]],
        comparison_deltas: Dict[str, Dict[str, Optional[float]]],
        abnormal_start: str,
        duration_points: int,
        abnormal_start_outside_window: bool,
    ) -> str:
        indicator_name = str(detail.get("name") or detail.get("tag_id") or "未命名指标")
        percentile_rank = stats.get("percentile_rank")
        history_delta = comparison_deltas.get("vs_history_median") or {}
        target_delta = comparison_deltas.get("vs_target") or {}
        parts = [
            f"{indicator_name} 当前值 {self._format_number(current_value)}，历史百分位 {self._format_percentile(percentile_rank)}。",
        ]
        if stats.get("median") is not None and history_delta.get("percent") is not None:
            parts.append(
                f"相对历史中位 {self._format_number(stats.get('median'))} 偏差 {self._format_percent(history_delta.get('percent'))}。"
            )
        if references.get("target_reference") is not None and target_delta.get("percent") is not None:
            parts.append(
                f"相对目标参考 {self._format_number(references.get('target_reference'))} 偏差 {self._format_percent(target_delta.get('percent'))}。"
            )
        if duration_points > 0:
            parts.append(f"异常窗口起于 {abnormal_start}，已持续 {duration_points} 个采样点。")
        if abnormal_start_outside_window:
            parts.append("异常开始早于当前图窗。")
        return "".join(parts)

    def _render_card_image(self, *, card: Dict[str, Any], asset_dir: Path, asset_prefix: str) -> Dict[str, Any]:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.font_manager import FontProperties
            from matplotlib.patches import Patch
        except Exception:
            return {
                "image_path": "",
                "image_relative_path": "",
                "image_status": "matplotlib_unavailable",
            }

        asset_dir.mkdir(parents=True, exist_ok=True)
        safe_tag = self._slugify(card.get("tag_id") or card.get("indicator_name") or f"card-{card.get('rank')}")
        filename = f"{int(card.get('rank') or 0):02d}_{safe_tag}_comparison.png"
        image_path = asset_dir / filename
        font_prop = self._resolve_plot_font(FontProperties)

        fig = plt.figure(figsize=(10.8, 5.6), dpi=150)
        grid = fig.add_gridspec(3, 1, height_ratios=[0.9, 3.2, 1.15], hspace=0.22)
        ax_timeline = fig.add_subplot(grid[0, 0])
        ax_trend = fig.add_subplot(grid[1, 0])
        ax_summary = fig.add_subplot(grid[2, 0])

        fig.patch.set_facecolor("#f8fafc")
        card_title = str(card.get("indicator_name") or card.get("tag_id") or "指标")
        fig.suptitle(card_title, fontsize=13, fontproperties=font_prop, y=0.98)

        full_timeline = card.get("full_timeline") or {}
        start_ratio = float(full_timeline.get("abnormal_start_ratio") or 0.0)
        end_ratio = float(full_timeline.get("abnormal_end_ratio") or 0.0)
        current_ratio = float(full_timeline.get("current_ratio") or 0.0)

        ax_timeline.hlines(0.5, 0.0, 1.0, color="#cbd5e1", linewidth=8, capstyle="round")
        if end_ratio >= start_ratio:
            ax_timeline.hlines(0.5, start_ratio, end_ratio, color="#ef4444", linewidth=8, capstyle="round")
        ax_timeline.scatter([current_ratio], [0.5], s=42, color="#0f172a", zorder=3)
        ax_timeline.set_xlim(-0.02, 1.02)
        ax_timeline.set_ylim(0, 1)
        ax_timeline.set_yticks([])
        ax_timeline.set_xticks([0.0, current_ratio, 1.0])
        ax_timeline.set_xticklabels(
            [
                self._compact_timestamp(full_timeline.get("series_start")),
                "当前",
                self._compact_timestamp(full_timeline.get("series_end")),
            ],
            fontproperties=font_prop,
            fontsize=8,
        )
        for spine in ax_timeline.spines.values():
            spine.set_visible(False)
        ax_timeline.set_title("全程位置条", loc="left", fontsize=10, fontproperties=font_prop, pad=4)
        ax_timeline.text(
            0.99,
            0.08,
            self._short_timeline_note(card),
            ha="right",
            va="bottom",
            fontsize=8,
            color="#475569",
            fontproperties=font_prop,
            transform=ax_timeline.transAxes,
        )

        recent_trend = card.get("recent_trend") or {}
        values = [self._safe_float(value) or 0.0 for value in (recent_trend.get("values") or [])]
        labels = list(recent_trend.get("timestamps") or [])
        x_values = list(range(len(values)))
        ref_lines = recent_trend.get("reference_lines") or {}
        chart_display = (recent_trend.get("chart_display") or {}) if isinstance(recent_trend, dict) else {}
        visible_reference_lines = (chart_display.get("visible_reference_lines") or {}) if isinstance(chart_display, dict) else {}
        key_points = (recent_trend.get("key_points") or {}) if isinstance(recent_trend, dict) else {}
        p10 = self._safe_float(visible_reference_lines.get("history_p10"))
        p90 = self._safe_float(visible_reference_lines.get("history_p90"))
        abnormal_start_index = self._safe_int(key_points.get("abnormal_start_index"))
        current_index = self._safe_int(key_points.get("current_index"))
        lowest_index = self._safe_int(key_points.get("lowest_index"))
        if abnormal_start_index is not None and current_index is not None and x_values:
            ax_trend.axvspan(
                max(-0.5, abnormal_start_index - 0.5),
                min(len(x_values) - 0.5, current_index + 0.5),
                color="#fee2e2",
                alpha=0.55,
                zorder=0,
            )
        if p10 is not None and p90 is not None and x_values:
            ax_trend.fill_between(x_values, [p10] * len(x_values), [p90] * len(x_values), color="#dbeafe", alpha=0.45, zorder=1)
            ax_trend.plot(x_values, [p10] * len(x_values), color="#93c5fd", linewidth=1.0, linestyle="--", alpha=0.9, label="_nolegend_")
            ax_trend.plot(x_values, [p90] * len(x_values), color="#93c5fd", linewidth=1.0, linestyle="--", alpha=0.9, label="_nolegend_")
            band_proxy = Patch(facecolor="#dbeafe", edgecolor="#93c5fd", alpha=0.45, label="历史区间")
        else:
            band_proxy = None
        if x_values:
            trend_line, = ax_trend.plot(
                x_values,
                values,
                color="#2563eb",
                linewidth=2.4,
                marker=None,
                zorder=3,
                label="当前趋势",
            )
            if abnormal_start_index is not None and 0 <= abnormal_start_index < len(values):
                ax_trend.scatter(
                    [abnormal_start_index],
                    [values[abnormal_start_index]],
                    s=40,
                    color="#dc2626",
                    edgecolors="#ffffff",
                    linewidths=0.8,
                    zorder=4,
                )
            if lowest_index is not None and 0 <= lowest_index < len(values):
                ax_trend.scatter(
                    [lowest_index],
                    [values[lowest_index]],
                    s=48,
                    color="#b91c1c",
                    edgecolors="#ffffff",
                    linewidths=0.8,
                    zorder=5,
                )
            if current_index is not None and 0 <= current_index < len(values):
                ax_trend.scatter(
                    [current_index],
                    [values[current_index]],
                    s=54,
                    color="#111827",
                    edgecolors="#ffffff",
                    linewidths=0.9,
                    zorder=6,
                )
        else:
            trend_line = None

        history_baseline_line = self._draw_reference_line(
            ax_trend,
            visible_reference_lines.get("history_baseline"),
            "#0f766e",
            "历史中位",
        )
        target_reference_line = self._draw_reference_line(
            ax_trend,
            visible_reference_lines.get("target_reference"),
            "#dc2626",
            "目标参考",
        )

        ax_trend.set_title("近窗趋势图", loc="left", fontsize=10, fontproperties=font_prop, pad=4)
        ax_trend.set_ylabel(str(card.get("unit") or ""), fontproperties=font_prop, fontsize=8)
        ax_trend.grid(axis="y", linestyle="--", alpha=0.25)
        plot_min = self._safe_float(chart_display.get("plot_min"))
        plot_max = self._safe_float(chart_display.get("plot_max"))
        if plot_min is not None and plot_max is not None and plot_max > plot_min:
            ax_trend.set_ylim(plot_min, plot_max)
        if x_values:
            tick_indexes = sorted(set([0, len(x_values) // 2, len(x_values) - 1]))
            ax_trend.set_xticks(tick_indexes)
            ax_trend.set_xticklabels(
                [self._compact_timestamp(labels[index]) for index in tick_indexes],
                rotation=0,
                fontsize=8,
                fontproperties=font_prop,
            )
        legend_handles: List[Any] = []
        legend_labels: List[str] = []
        if trend_line is not None:
            legend_handles.append(trend_line)
            legend_labels.append("当前趋势")
        if band_proxy is not None:
            legend_handles.append(band_proxy)
            legend_labels.append("历史区间")
        if history_baseline_line is not None:
            legend_handles.append(history_baseline_line)
            legend_labels.append("历史中位")
        if target_reference_line is not None:
            legend_handles.append(target_reference_line)
            legend_labels.append("目标参考")
        legend = ax_trend.legend(legend_handles, legend_labels, loc="upper left", fontsize=8, frameon=False, ncol=max(1, min(4, len(legend_labels))))
        if legend and font_prop:
            for text in legend.get_texts():
                text.set_fontproperties(font_prop)

        ax_summary.axis("off")
        summary_rows = list(card.get("summary_rows") or [])
        for idx, row in enumerate(summary_rows[:4]):
            x_pos = 0.02 if idx % 2 == 0 else 0.52
            y_pos = 0.82 if idx < 2 else 0.38
            label = str((row or {}).get("label") or "")
            value = str((row or {}).get("value") or "")
            ax_summary.text(
                x_pos,
                y_pos,
                label,
                transform=ax_summary.transAxes,
                fontsize=8,
                color="#64748b",
                fontproperties=font_prop,
                ha="left",
                va="bottom",
            )
            ax_summary.text(
                x_pos,
                y_pos - 0.16,
                value,
                transform=ax_summary.transAxes,
                fontsize=10,
                color="#0f172a",
                fontproperties=font_prop,
                ha="left",
                va="top",
                bbox=dict(boxstyle="round,pad=0.28", facecolor="#f8fafc", edgecolor="#e2e8f0"),
            )

        note_lines = list(chart_display.get("reference_notes") or [])
        if recent_trend.get("abnormal_start_outside_window"):
            note_lines.append("异常开始早于当前图窗")
        if note_lines:
            ax_summary.text(
                0.02,
                0.02,
                "；".join(note_lines[:2]),
                transform=ax_summary.transAxes,
                fontsize=7.8,
                color="#475569",
                fontproperties=font_prop,
                ha="left",
                va="bottom",
            )

        fig.subplots_adjust(left=0.07, right=0.98, top=0.9, bottom=0.08, hspace=0.32)
        fig.savefig(image_path, bbox_inches="tight")
        plt.close(fig)
        relative_path = str(Path(asset_prefix) / filename).replace("\\", "/") if asset_prefix else filename
        return {
            "image_path": str(image_path.resolve()).replace("\\", "/"),
            "image_relative_path": relative_path,
            "image_status": "generated",
        }

    def _draw_reference_line(self, ax: Any, value: Any, color: str, label: str) -> Optional[Any]:
        numeric = self._safe_float(value)
        if numeric is None:
            return None
        line = ax.axhline(numeric, color=color, linewidth=1.2, linestyle="--", alpha=0.85, label=label)
        return line

    def _resolve_plot_font(self, font_properties_cls: Any) -> Optional[Any]:
        candidates = [
            Path(__file__).resolve().parents[1] / "resets" / "fonts" / "仿宋_GB2312.ttf",
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simsun.ttc"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return font_properties_cls(fname=str(candidate))
        return None

    def _resolve_latest_index(self, series: Sequence[_SeriesPoint], latest_timestamp: Optional[str]) -> int:
        if not latest_timestamp:
            return len(series) - 1
        latest_value = str(latest_timestamp)
        for index in range(len(series) - 1, -1, -1):
            if series[index].timestamp == latest_value:
                return index
        return len(series) - 1

    def _find_timestamp_index(self, series: Sequence[_SeriesPoint], timestamp: str, default: int) -> int:
        if not timestamp:
            return default
        for index, point in enumerate(series):
            if point.timestamp == timestamp:
                return index
        for index, point in enumerate(series):
            if point.timestamp >= timestamp:
                return index
        return default

    def _percentile(self, ordered_values: Sequence[float], q: float) -> Optional[float]:
        values = [float(value) for value in ordered_values if value is not None]
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        pos = max(0.0, min(1.0, q)) * (len(values) - 1)
        lower = int(math.floor(pos))
        upper = int(math.ceil(pos))
        if lower == upper:
            return values[lower]
        weight = pos - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    def _percentile_rank(self, current_value: float, ordered_values: Sequence[float]) -> Optional[float]:
        values = [float(value) for value in ordered_values if value is not None]
        if not values:
            return None
        less_or_equal = sum(1 for value in values if value <= current_value)
        return round(less_or_equal / len(values) * 100.0, 2)

    def _ratio(self, index: int, total: int) -> float:
        if total <= 1:
            return 1.0
        return round(max(0.0, min(1.0, index / (total - 1))), 6)

    def _short_timeline_note(self, card: Dict[str, Any]) -> str:
        full_timeline = card.get("full_timeline") or {}
        abnormal_start = self._compact_timestamp(full_timeline.get("abnormal_start"))
        abnormal_end = self._compact_timestamp(full_timeline.get("abnormal_end"))
        return f"异常窗口：{abnormal_start} -> {abnormal_end}"

    def _compact_timestamp(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "-"
        if "T" in text:
            date_part, time_part = text.split("T", 1)
            return f"{date_part} {time_part[:5]}"
        return text[:16]

    def _slugify(self, value: Any) -> str:
        raw = str(value or "").strip().replace("\\", "_").replace("/", "_")
        cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_") or "indicator"

    def _format_number(self, value: Any) -> str:
        numeric = self._safe_float(value)
        if numeric is None:
            return "-"
        if abs(numeric) >= 100:
            return f"{numeric:.1f}"
        if abs(numeric) >= 10:
            return f"{numeric:.2f}"
        return f"{numeric:.3f}"

    def _format_percent(self, value: Any) -> str:
        numeric = self._safe_float(value)
        if numeric is None:
            return "-"
        return f"{numeric:+.1f}%"

    def _resolve_overview_reference(self, card: Dict[str, Any]) -> Tuple[Optional[float], str]:
        references = card.get("references") or {}
        history_stats = card.get("history_stats") or {}
        candidates = [
            (references.get("target_reference"), "目标参考"),
            (references.get("history_baseline"), "历史中位"),
            (history_stats.get("median"), "历史中位"),
        ]
        for value, label in candidates:
            numeric = self._safe_float(value)
            if numeric is not None and abs(numeric) > 1e-6:
                return numeric, label
        return None, "未设参考"

    def _normalize_relative_percent(self, value: Optional[float], reference_value: Optional[float]) -> Optional[float]:
        if value is None or reference_value is None or abs(reference_value) <= 1e-6:
            return None
        return round((value - reference_value) / abs(reference_value) * 100.0, 4)

    def _build_overview_chart_display(self, values: Sequence[float]) -> Dict[str, Any]:
        numeric_values = [float(value) for value in values if value is not None and math.isfinite(float(value))]
        if not numeric_values:
            return {"plot_min": -10.0, "plot_max": 10.0}
        min_value = min(numeric_values)
        max_value = max(numeric_values)
        spread = max(max_value - min_value, max(abs(min_value), abs(max_value)) * 0.2, 10.0)
        padding = max(spread * 0.14, 4.0)
        plot_min = min(min_value - padding, -2.0)
        plot_max = max(max_value + padding, 2.0)
        return {
            "plot_min": round(plot_min, 6),
            "plot_max": round(plot_max, 6),
        }

    def _format_percentile(self, value: Any) -> str:
        numeric = self._safe_float(value)
        if numeric is None:
            return "-"
        return f"{numeric:.1f}%位"

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
