from pathlib import Path

from src.services.visualization_service import TimeComparisonVisualizationService


def test_visualization_context_uses_history_before_latest_for_percentile_and_deltas(tmp_path):
    service = TimeComparisonVisualizationService()

    standardized_data = [
        {"tag_id": "exp_b", "timestamp": "2026-03-14T09:00:00", "value": 10.0, "unit": "kW"},
        {"tag_id": "exp_b", "timestamp": "2026-03-14T10:00:00", "value": 20.0, "unit": "kW"},
        {"tag_id": "exp_b", "timestamp": "2026-03-14T11:00:00", "value": 100.0, "unit": "kW"},
    ]
    abnormal_details = [
        {
            "tag_id": "exp_b",
            "name": "膨胀机B制冷量",
            "current_value": 20.0,
            "severity_score": 1.48,
            "level": "严重偏低",
            "reference_value": 30.0,
            "window": {
                "start": "2026-03-14T10:00:00",
                "end": "2026-03-14T10:00:00",
                "duration_points": 1,
            },
        }
    ]
    baseline_profile = {
        "per_tag": {
            "exp_b": {
                "baseline_value": 12.0,
                "optimal_reference": 32.0,
            }
        }
    }

    context = service.build_visualization_context(
        standardized_data=standardized_data,
        latest_timestamp="2026-03-14T10:00:00",
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
        asset_dir=tmp_path / "assets",
        asset_prefix="assets/report_a",
    )

    data_curve_overview = context["data_curve_overview"]
    assert data_curve_overview["category_count"] == 1
    assert data_curve_overview["indicator_count"] == 1
    assert data_curve_overview["categories"][0]["title"] == "冷量/冷损"
    overview_item = data_curve_overview["categories"][0]["items"][0]
    assert overview_item["reference_label"] == "目标参考"
    assert overview_item["current_delta_percent"] == -33.3333
    assert overview_item["chart"]["display"]["visible_reference_line"] == 30.0
    overview = context["overview_card"]
    assert overview["indicator_count"] == 1
    assert overview["y_axis_label"] == "相对参考偏差 (%)"
    assert overview["series"][0]["reference_label"] == "目标参考"
    assert overview["series"][0]["current_relative_percent"] == -33.3333
    card = context["top_indicator_cards"][0]
    assert card["history_stats"]["sample_count"] == 1
    assert card["history_stats"]["median"] == 10.0
    assert card["history_stats"]["percentile_rank"] == 100.0
    assert card["comparison_deltas"]["vs_target"]["value"] == -10.0
    assert card["comparison_deltas"]["vs_history_median"]["value"] == 10.0
    assert card["comparison_deltas"]["vs_optimal"]["value"] == -12.0
    assert card["recent_trend"]["window_point_count"] == 2
    assert card["recent_trend"]["chart_display"]["visible_reference_lines"]["target_reference"] is None
    assert "目标参考" in "；".join(card["recent_trend"]["chart_display"]["reference_notes"])
    assert card["summary_rows"][0]["label"] == "当前值"
    assert card["summary_rows"][1]["label"] == "相对目标"
    assert card["image_status"] == "generated"
    assert Path(card["image_path"]).exists()
    assert card["image_relative_path"].startswith("assets/report_a/")


def test_visualization_context_clamps_window_and_computes_timeline_ratios():
    service = TimeComparisonVisualizationService()

    standardized_data = [
        {
            "tag_id": "cold_loss",
            "timestamp": f"2026-03-14T{(index // 60):02d}:{(index % 60):02d}:00",
            "value": float(index),
            "unit": "%",
        }
        for index in range(150)
    ]
    abnormal_details = [
        {
            "tag_id": "cold_loss",
            "name": "主换冷损",
            "current_value": 149.0,
            "severity_score": 1.32,
            "state_desc": "严重偏高",
            "window": {
                "start": "2026-03-14T00:30:00",
                "end": "2026-03-14T02:29:00",
                "duration_points": 120,
            },
        }
    ]

    context = service.build_visualization_context(
        standardized_data=standardized_data,
        latest_timestamp="2026-03-14T02:29:00",
        abnormal_details=abnormal_details,
        baseline_profile={},
    )

    overview = context["overview_card"]
    assert overview["indicator_count"] == 1
    assert overview["window_point_count"] == 96
    assert overview["chart_display"]["latest_index"] == 95
    card = context["top_indicator_cards"][0]
    assert card["recent_trend"]["window_point_count"] == 96
    assert card["recent_trend"]["abnormal_start_outside_window"] is True
    assert card["full_timeline"]["abnormal_start_ratio"] == round(30 / 149, 6)
    assert card["full_timeline"]["abnormal_end_ratio"] == 1.0
    assert card["full_timeline"]["current_ratio"] == 1.0
    assert card["references"]["target_reference"] is None
    assert card["references"]["optimal_reference"] is None
    assert card["recent_trend"]["key_points"]["lowest_index"] == 0
    assert card["recent_trend"]["chart_display"]["plot_max"] < 200


def test_visualization_context_builds_grouped_curve_overview_for_all_tags():
    service = TimeComparisonVisualizationService()

    standardized_data = [
        {"tag_id": "energy_1", "name": "压缩机电耗", "timestamp": "2026-03-14T09:00:00", "value": 98.0, "unit": "kWh"},
        {"tag_id": "energy_1", "name": "压缩机电耗", "timestamp": "2026-03-14T10:00:00", "value": 101.0, "unit": "kWh"},
        {"tag_id": "yield_1", "name": "氧提取率", "timestamp": "2026-03-14T09:00:00", "value": 97.8, "unit": "%"},
        {"tag_id": "yield_1", "name": "氧提取率", "timestamp": "2026-03-14T10:00:00", "value": 98.1, "unit": "%"},
        {"tag_id": "tower_1", "name": "上塔压力", "timestamp": "2026-03-14T09:00:00", "value": 0.53, "unit": "MPa"},
        {"tag_id": "tower_1", "name": "上塔压力", "timestamp": "2026-03-14T10:00:00", "value": 0.55, "unit": "MPa"},
    ]
    abnormal_details = [
        {
            "tag_id": "energy_1",
            "name": "压缩机电耗",
            "current_value": 101.0,
            "severity_score": 0.92,
            "state_desc": "偏高",
            "reference_value": 94.0,
            "window": {
                "start": "2026-03-14T10:00:00",
                "end": "2026-03-14T10:00:00",
                "duration_points": 1,
            },
        }
    ]
    baseline_profile = {
        "per_tag": {
            "energy_1": {"baseline_value": 96.0},
            "yield_1": {"baseline_value": 97.6},
            "tower_1": {"baseline_value": 0.52},
        }
    }

    context = service.build_visualization_context(
        standardized_data=standardized_data,
        latest_timestamp="2026-03-14T10:00:00",
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
    )

    groups = {item["key"]: item for item in context["data_curve_overview"]["categories"]}
    assert groups["energy"]["indicator_count"] == 1
    assert groups["yield"]["indicator_count"] == 1
    assert groups["stability"]["indicator_count"] == 1
    energy_item = groups["energy"]["items"][0]
    assert energy_item["indicator_name"] == "压缩机电耗"
    assert energy_item["chart"]["display"]["plot_max"] > energy_item["current_value"]
    assert energy_item["chart"]["current_index"] == 1


def test_visualization_context_keeps_curve_overview_without_abnormal_details():
    service = TimeComparisonVisualizationService()

    context = service.build_visualization_context(
        standardized_data=[
            {"tag_id": "yield_1", "name": "氧提取率", "timestamp": "2026-03-14T09:00:00", "value": 97.9, "unit": "%"},
            {"tag_id": "yield_1", "name": "氧提取率", "timestamp": "2026-03-14T10:00:00", "value": 98.0, "unit": "%"},
        ],
        latest_timestamp="2026-03-14T10:00:00",
        abnormal_details=[],
        baseline_profile={"per_tag": {"yield_1": {"baseline_value": 97.8}}},
    )

    assert context["top_indicator_cards"] == []
    assert context["overview_card"] == {}
    assert context["data_curve_overview"]["indicator_count"] == 1
    assert context["data_curve_overview"]["categories"][0]["key"] == "yield"
