from src.services.data_semantics import DataSemanticsService


def test_three_level_state_engine_outputs_subsystem_and_plant_state():
    service = DataSemanticsService()
    semantic_data = [
        {"tag_id": "cold_loss_1", "name": "主换冷损", "current_value": 88.0, "state_desc": "偏高", "membership_degree": 0.3},
        {"tag_id": "energy_1", "name": "压缩机电耗", "current_value": 102.0, "state_desc": "偏高", "membership_degree": 0.25},
        {"tag_id": "purity_1", "name": "氧纯度", "current_value": 99.5, "state_desc": "良好", "membership_degree": 0.9},
    ]
    abnormal_details = [
        {
            "tag_id": "cold_loss_1",
            "name": "主换冷损",
            "level": "偏高",
            "trend": "increasing",
            "diff_percent": 12.5,
            "severity_score": 0.92,
            "optimization_direction": "decrease",
        },
        {
            "tag_id": "energy_1",
            "name": "压缩机电耗",
            "level": "偏高",
            "trend": "stable",
            "diff_percent": 8.0,
            "severity_score": 0.85,
            "optimization_direction": "decrease",
        },
    ]
    baseline_profile = {
        "per_tag": {
            "cold_loss_1": {"optimal_reference": 70.0},
            "energy_1": {"optimal_reference": 95.0},
            "purity_1": {"optimal_reference": 99.8},
        }
    }

    summary = service.build_overall_operating_summary(
        semantic_data=semantic_data,
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
    )

    assert summary["plant_state"] in {"optimizable", "risk_rising", "abnormal_unstable", "stable", "optimal"}
    assert isinstance(summary["subsystem_states"], list) and summary["subsystem_states"]
    assert isinstance(summary["optimization_priority"], list)
    assert isinstance(summary["three_level_state_engine"], dict)


def test_overall_summary_exposes_audit_layers_and_rule_transparency():
    service = DataSemanticsService()
    semantic_data = [
        {"tag_id": "cold_loss_1", "name": "主换冷损", "current_value": 92.0, "state_desc": "偏高", "membership_degree": 0.2},
        {"tag_id": "exp_b_1", "name": "膨胀机B制冷量", "current_value": 70.0, "state_desc": "严重偏低", "membership_degree": 0.05},
    ]
    abnormal_details = [
        {
            "tag_id": "exp_b_1",
            "name": "膨胀机B制冷量",
            "level": "严重偏低",
            "current_value": 70.0,
            "baseline_value": 360.0,
            "diff_percent": -80.6,
            "severity_score": 1.18,
            "trend": "decreasing",
            "window": {"duration_points": 116},
            "objective": "maximize",
            "optimization_direction": "increase",
            "reference_label": "industry_benchmark",
            "reference_value": 360.0,
            "reference_source_type": "indicator_profile",
            "reference_source_label": "配置参考值",
            "reference_scope": "当前装置指标配置",
            "comparison_method": "latest_snapshot_vs_fixed_reference",
            "evidence_layers": {
                "facts": ["膨胀机B制冷量当前值为 70，对比配置参考值 360，偏差 -80.6%。"],
                "rules": ["单指标规则判定：膨胀机B制冷量为严重偏低。"],
                "actions": ["核查膨胀机入口/出口温压、导叶或阀位。"],
            },
        }
    ]
    baseline_profile = {
        "method": "historical_percentile_plus_objective_profile",
        "method_label": "同装置历史分位基线 + 指标目标方向",
        "tag_count": 2,
        "per_tag": {
            "exp_b_1": {"baseline_value": 280.0, "optimal_reference": 360.0},
            "cold_loss_1": {"baseline_value": 70.0, "optimal_reference": 65.0},
        },
    }

    summary = service.build_overall_operating_summary(
        semantic_data=semantic_data,
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
    )

    assert summary["baseline_references"]
    assert any(item["indicator"] == "膨胀机B制冷量" for item in summary["baseline_references"])
    assert summary["reference_framework"]
    assert any(rule["stage"] == "装置状态" for rule in summary["state_aggregation_rules"])
    assert summary["triggered_rules"]
    assert summary["evidence_layers"]["facts"]
    assert summary["evidence_layers"]["rules"]
    assert summary["verification_loop"]["check_first"]
    assert "候选假设" in summary["explanation_boundary"]
    assert summary["explainability"]["reference_provenance"]
    assert summary["explainability"]["rule_parameter_explanations"]
    assert summary["explainability"]["dominant_anomaly_explanation"]["candidate_label"]


def test_rule_registry_drives_status_and_explanation_from_single_source():
    service = DataSemanticsService()
    service.rule_registry["rules"]["risk_level"]["parameters"]["critical"]["abnormal_ratio_gte"] = 0.60

    summary = service.build_overall_operating_summary(
        semantic_data=[
            {"tag_id": "exp_b_1", "name": "膨胀机B制冷量", "current_value": 70.0, "state_desc": "严重偏低", "membership_degree": 0.05},
            {"tag_id": "purity_1", "name": "氧纯度", "current_value": 99.5, "state_desc": "良好", "membership_degree": 0.9},
        ],
        abnormal_details=[
            {
                "tag_id": "exp_b_1",
                "name": "膨胀机B制冷量",
                "level": "严重偏低",
                "current_value": 70.0,
                "baseline_value": 360.0,
                "diff_percent": -80.6,
                "severity_score": 0.98,
                "trend": "decreasing",
                "window": {"duration_points": 116},
                "objective": "maximize",
                "optimization_direction": "increase",
            }
        ],
        baseline_profile={"per_tag": {"exp_b_1": {"optimal_reference": 360.0}}},
    )

    rule_explanation = summary["explainability"]["rule_parameter_explanations"][0]
    assert summary["status_level"] == "warning"
    assert rule_explanation["matched_branch"] == "warning"
    assert rule_explanation["thresholds"]["critical"]["abnormal_ratio_gte"] == 0.60
    assert "0.60" in rule_explanation["text"]


def test_reference_provenance_uses_fallback_when_metadata_missing():
    service = DataSemanticsService()

    summary = service.build_overall_operating_summary(
        semantic_data=[
            {"tag_id": "exp_b_1", "name": "膨胀机B制冷量", "current_value": 70.0, "state_desc": "严重偏低", "membership_degree": 0.05},
            {"tag_id": "purity_1", "name": "氧纯度", "current_value": 99.5, "state_desc": "良好", "membership_degree": 0.9},
        ],
        abnormal_details=[
            {
                "tag_id": "exp_b_1",
                "name": "膨胀机B制冷量",
                "level": "严重偏低",
                "current_value": 70.0,
                "reference_value": 360.0,
                "diff_percent": -80.6,
                "severity_score": 1.18,
                "trend": "decreasing",
                "window": {"duration_points": 116},
            }
        ],
        baseline_profile={"per_tag": {"exp_b_1": {"optimal_reference": 360.0}}},
    )

    provenance = summary["explainability"]["reference_provenance"][0]
    assert provenance["validation_status"] == "traceable_unvalidated"
    assert "统计标定" in provenance["text"]


def test_dominant_anomaly_explanation_degrades_for_near_tie_same_subsystem():
    service = DataSemanticsService()

    summary = service.build_overall_operating_summary(
        semantic_data=[
            {"tag_id": "expander_a_1", "name": "膨胀机A制冷量", "current_value": 82.0, "state_desc": "严重偏低", "membership_degree": 0.08},
            {"tag_id": "expander_b_1", "name": "膨胀机B制冷量", "current_value": 80.0, "state_desc": "严重偏低", "membership_degree": 0.06},
            {"tag_id": "purity_1", "name": "氧纯度", "current_value": 99.5, "state_desc": "良好", "membership_degree": 0.9},
        ],
        abnormal_details=[
            {
                "tag_id": "expander_a_1",
                "name": "膨胀机A制冷量",
                "level": "严重偏低",
                "diff_percent": -77.0,
                "severity_score": 1.20,
                "trend": "decreasing",
                "window": {"start": "t1", "end": "t10", "duration_points": 120},
            },
            {
                "tag_id": "expander_b_1",
                "name": "膨胀机B制冷量",
                "level": "严重偏低",
                "diff_percent": -76.2,
                "severity_score": 1.17,
                "trend": "decreasing",
                "window": {"start": "t3", "end": "t9", "duration_points": 112},
            },
        ],
        baseline_profile={"per_tag": {"expander_a_1": {"optimal_reference": 360.0}, "expander_b_1": {"optimal_reference": 360.0}}},
    )

    explanation = summary["explainability"]["dominant_anomaly_explanation"]
    assert explanation["classification"] == "co_primary"
    assert "并列主导异常" in explanation["candidate_label"]
    assert "当前未形成稳定时间先后证据" in explanation["temporal_precedence_explanation"]
    assert "不等于已确认根因" in explanation["exclusion_boundary_explanation"]


def test_abnormal_details_distinguish_target_history_and_optimal_references():
    service = DataSemanticsService()
    history_data = [
        {"tag_id": "main_heat", "name": "主换冷损", "value": 118.0, "timestamp": "2026-03-10T00:00:00"},
        {"tag_id": "main_heat", "name": "主换冷损", "value": 114.0, "timestamp": "2026-03-11T00:00:00"},
        {"tag_id": "main_heat", "name": "主换冷损", "value": 92.55, "timestamp": "2026-03-12T00:00:00"},
    ]
    latest_semantic_data = [
        {
            "tag_id": "main_heat",
            "name": "主换冷损",
            "current_value": 92.55,
            "state_desc": "严重偏高",
            "diff": 22.55,
            "membership_degree": 0.0,
            "reference_label": "industry_benchmark",
            "reference_value": 70.0,
            "reference_source_label": "配置参考值",
            "reference_scope": "当前装置指标配置",
            "comparison_method": "latest_snapshot_vs_fixed_reference",
        }
    ]
    baseline_profile = {
        "method_label": "同装置历史分位基线 + 指标目标方向",
        "per_tag": {
            "main_heat": {
                "baseline_value": 114.03,
                "optimal_reference": 70.0,
            }
        },
    }

    abnormal_details = service.build_abnormal_details(
        history_data=history_data,
        latest_semantic_data=latest_semantic_data,
        baseline_profile=baseline_profile,
    )

    detail = abnormal_details[0]
    assert detail["target_reference"] == 70.0
    assert detail["history_baseline"] == 114.03
    assert detail["optimal_reference"] == 70.0
    assert detail["final_grade_basis"] == "target_reference"
    assert detail["target_diff_percent"] > 0
    assert detail["history_diff_percent"] < 0
    assert any("历史常态不等同于目标工况或优态工况" in item for item in detail["evidence_layers"]["facts"])


def test_severity_components_expose_level_diff_and_duration_terms():
    service = DataSemanticsService()

    components = service._calculate_severity_components("严重偏低", -80.6, 116)

    assert components["level_score"] == 1.0
    assert components["diff_component"] == 0.2821
    assert components["duration_component"] == 0.2
    assert components["duration_cap_applied"] is True
    assert components["severity_score"] == 1.4821


def test_overall_summary_exposes_calculation_audit_layers():
    service = DataSemanticsService()
    parsing_audit = {
        "layout_detected": "wide_table",
        "data_start_row": 1,
        "design_ref_row": None,
        "dropped_rows": [{"row_index": 0, "reason": "descriptor_row"}],
        "first_included_timestamp": "2025-01-01 00:00:00",
        "last_included_timestamp": "2025-12-01 00:00:00",
        "record_count_before_gate": 3685,
        "record_count_after_gate": 3685,
        "timepoint_count_before_gate": 335,
        "timepoint_count_after_gate": 335,
        "sensor_count": 11,
        "count_change_reason": "纳入首个真实时间点。",
    }
    history_data = [
        {"tag_id": "exp_b_1", "name": "膨胀机B制冷量", "value": 120.0, "timestamp": "2025-11-29T00:00:00"},
        {"tag_id": "exp_b_1", "name": "膨胀机B制冷量", "value": 100.0, "timestamp": "2025-11-30T00:00:00"},
        {"tag_id": "cold_loss_1", "name": "主换冷损", "value": 108.0, "timestamp": "2025-11-29T00:00:00"},
        {"tag_id": "cold_loss_1", "name": "主换冷损", "value": 112.0, "timestamp": "2025-11-30T00:00:00"},
    ]
    semantic_data = [
        {
            "tag_id": "exp_b_1",
            "name": "膨胀机B制冷量",
            "current_value": 69.91,
            "state_desc": "严重偏低",
            "membership_degree": 0.05,
            "reference_value": 360.0,
            "reference_source_label": "配置参考值",
            "comparison_method": "latest_snapshot_vs_fixed_reference",
        },
        {
            "tag_id": "cold_loss_1",
            "name": "主换冷损",
            "current_value": 92.55,
            "state_desc": "一般",
            "membership_degree": 0.6,
            "reference_value": 70.0,
            "reference_source_label": "配置参考值",
            "comparison_method": "latest_snapshot_vs_fixed_reference",
        },
    ]
    severity = service._calculate_severity_components("严重偏低", -80.6, 116)
    abnormal_details = [
        {
            "tag_id": "exp_b_1",
            "name": "膨胀机B制冷量",
            "level": "严重偏低",
            "current_value": 69.91,
            "target_reference": 360.0,
            "history_baseline": 110.0,
            "optimal_reference": 384.93,
            "diff_ratio": -0.806,
            "diff_percent": -80.6,
            "history_diff_percent": -36.4,
            "optimal_diff_percent": -81.8,
            "history_percentile_rank": 5.0,
            "severity_score": severity["severity_score"],
            "severity_breakdown": severity,
            "trend": "decreasing",
            "window": {"duration_points": 116, "start": "2025-08-08T00:00:00", "end": "2025-12-01T00:00:00"},
            "objective": "maximize",
            "optimization_direction": "increase",
            "final_grade_basis": "target_reference",
            "final_grade_basis_label": "目标参考值",
            "final_grade_basis_reason": "最终异常判级按目标参考值执行。",
            "comparison_method": "latest_snapshot_vs_fixed_reference",
            "reference_source_label": "配置参考值",
            "state_rule_trace": {
                "objective": "maximize",
                "reference_value": 360.0,
                "diff_ratio": -0.806,
                "matched_interval": "diff_ratio < -0.50",
                "state": "严重偏低",
            },
        }
    ]
    baseline_profile = {
        "history_model_metadata": {
            "profile_source": "runtime",
            "selected_regime": "low",
            "anchor_tag": "HY_2030_1#ZB_1_Energy_AirCompress_8",
            "global_fallback_used": False,
        },
        "per_tag": {
            "exp_b_1": {
                "baseline_value": 110.0,
                "optimal_reference": 384.93,
                "objective": "maximize",
                "selected_regime": "low",
                "regime_sample_count": 80,
                "global_sample_count": 335,
                "median": 110.0,
                "p10": 90.0,
                "p90": 384.93,
                "mad": 8.0,
                "iqr": 24.0,
            },
            "cold_loss_1": {
                "baseline_value": 110.0,
                "optimal_reference": 65.89,
                "objective": "minimize",
                "selected_regime": "low",
                "regime_sample_count": 80,
                "global_sample_count": 335,
                "median": 110.0,
                "p10": 70.0,
                "p90": 120.0,
                "mad": 5.0,
                "iqr": 12.0,
            },
        }
    }

    summary = service.build_overall_operating_summary(
        semantic_data=semantic_data,
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
        history_data=history_data,
        parsing_audit=parsing_audit,
    )

    audit = summary["calculation_audit"]
    assert audit["data_intake"]["first_included_timestamp"] == "2025-01-01 00:00:00"
    assert audit["history_model_metadata"]["selected_regime"] == "low"
    assert audit["plant"]["abnormal_ratio"] == 0.5
    assert audit["plant"]["max_severity"] == 1.4821
    assert audit["subsystems"]
    assert any("膨胀机B制冷量" in member for subsystem in audit["subsystems"] for member in subsystem["members"])

    expander = next(item for item in audit["indicators"] if item["tag_id"] == "exp_b_1")
    assert expander["target_reference"] == 360.0
    assert expander["history_baseline"] == 110.0
    assert expander["optimal_reference"] == 384.93
    assert expander["selected_regime"] == "low"
    assert expander["statistical_state"] in {"warning", "high"}
    assert expander["agreement_flag"] in {"agree", "rule_only", "history_only", "conflict"}
    assert expander["hybrid_severity_score"] >= expander["severity_score"]
    assert expander["final_grade_basis_label"] == "目标参考值"
    assert expander["state_rule_trace"]["matched_interval"] == "diff_ratio < -0.50"
    assert expander["severity_breakdown"]["level_score"] == 1.0
    assert expander["severity_breakdown"]["diff_component"] == 0.2821
    assert expander["severity_breakdown"]["duration_component"] == 0.2


def test_standby_expander_is_suppressed_when_pair_is_main_running():
    service = DataSemanticsService()
    history_data = [
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_2", "name": "膨胀机A制冷量", "value": 392.0, "timestamp": "2025-12-01T00:00:00"},
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_6", "name": "膨胀机B制冷量", "value": 72.0, "timestamp": "2025-12-01T00:00:00"},
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_2", "name": "膨胀机A制冷量", "value": 396.0, "timestamp": "2025-12-02T00:00:00"},
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_6", "name": "膨胀机B制冷量", "value": 68.0, "timestamp": "2025-12-02T00:00:00"},
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_2", "name": "膨胀机A制冷量", "value": 398.0, "timestamp": "2025-12-03T00:00:00"},
        {"tag_id": "HY_2030_1#ZB_1_Cooling_Expander_6", "name": "膨胀机B制冷量", "value": 70.0, "timestamp": "2025-12-03T00:00:00"},
    ]
    latest_rows = [row for row in history_data if row["timestamp"] == "2025-12-03T00:00:00"]

    semantic_data = service.process(latest_rows)
    expander_b = next(item for item in semantic_data if item["tag_id"] == "HY_2030_1#ZB_1_Cooling_Expander_6")

    assert expander_b["state_desc"] == "待机备用"
    assert expander_b["assessment_reason"] == "standby-guard"
    assert "一备一用" in expander_b["comparison_summary"]

    baseline_profile = service.build_baseline_profile(history_data)
    abnormal_details = service.build_abnormal_details(
        history_data=history_data,
        latest_semantic_data=semantic_data,
        baseline_profile=baseline_profile,
    )

    assert all(item["tag_id"] != "HY_2030_1#ZB_1_Cooling_Expander_6" for item in abnormal_details)

    summary = service.build_overall_operating_summary(
        semantic_data=semantic_data,
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
        history_data=history_data,
    )

    assert summary["abnormal_count"] == 0
    assert summary["good_count"] >= 1
    assert any("主运行机" in line or "一备一用" in line for line in summary["highlights"])
