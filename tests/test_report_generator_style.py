from pathlib import Path

import base64

from src.utils import report_generator


def _mock_fonts(monkeypatch, tmp_path):
    expected = report_generator.ResolvedReportFonts(
        title_font="GovTitleFont",
        body_font="GovBodyFont",
        title_path=str(tmp_path / "title.ttf"),
        body_path=str(tmp_path / "body.ttf"),
        source="项目字体",
        fallback_reason="",
    )
    monkeypatch.setattr(report_generator, "resolve_report_fonts", lambda: expected)
    return expected


def _to_latin1_mojibake(text: str) -> str:
    return text.encode("utf-8").decode("latin1")


def test_resolve_report_fonts_prefers_project_fonts(monkeypatch, tmp_path):
    title_font = tmp_path / "方正小标宋简体.ttf"
    body_font = tmp_path / "仿宋_GB2312.ttf"
    title_font.write_bytes(b"font")
    body_font.write_bytes(b"font")

    monkeypatch.setattr(
        report_generator,
        "_resolve_font_candidates",
        lambda _project_root: {"title": [title_font], "body": [body_font]},
    )
    monkeypatch.setattr(report_generator, "_register_font", lambda _alias, _path: True)

    resolved = report_generator.resolve_report_fonts()

    assert resolved.title_font == "GovTitleFont"
    assert resolved.body_font == "GovBodyFont"
    assert resolved.title_path == str(title_font)
    assert resolved.body_path == str(body_font)
    assert resolved.source == "项目字体"
    assert resolved.fallback_reason == ""


def test_resolve_report_fonts_fallback_to_builtin(monkeypatch, tmp_path):
    missing_font = tmp_path / "missing.ttf"

    monkeypatch.setattr(
        report_generator,
        "_resolve_font_candidates",
        lambda _project_root: {"title": [missing_font], "body": [missing_font]},
    )
    monkeypatch.setattr(report_generator, "_register_font", lambda _alias, _path: False)

    resolved = report_generator.resolve_report_fonts()

    assert resolved.title_font == "Helvetica"
    assert resolved.body_font == "Helvetica"
    assert resolved.source == "内置回退"
    assert "回退" in resolved.fallback_reason


def test_report_generator_uses_resolved_fonts(monkeypatch, tmp_path):
    expected = report_generator.ResolvedReportFonts(
        title_font="GovTitleFont",
        body_font="GovBodyFont",
        title_path=str(tmp_path / "title.ttf"),
        body_path=str(tmp_path / "body.ttf"),
        source="项目字体",
        fallback_reason="",
    )
    monkeypatch.setattr(report_generator, "resolve_report_fonts", lambda: expected)

    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    assert generator.fonts.title_font == "GovTitleFont"
    assert generator.fonts.body_font == "GovBodyFont"
    assert Path(generator.output_dir).exists()


def test_markdown_report_includes_traceability_section(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-08 23:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "data_overview": {
            "file_name": "demo.xlsx",
            "timepoint_count": 10,
            "sensor_count": 3,
            "effective_record_count": 30,
            "time_range_start": "t1",
            "time_range_end": "t2",
            "latest_timestamp": "t2",
            "latest_record_count": 3,
        },
        "analysis_steps": [{"step": 1, "title": "数据加载与范围确认", "summary": "已加载数据并确认范围。"}],
        "traceability": {
            "task_id": "task-123",
            "session_id": "ws-123",
            "mode": "统一流程",
            "data_source": "sample",
            "llm_provider": "direct",
            "llm_model": "gpt-test",
            "retrieval_provider": "dify",
            "retrieval_model": "dify-app",
            "step_traces": [
                {
                    "step": 1,
                    "title": "数据加载与范围确认",
                    "started_at": "2026-03-08T23:00:00",
                    "ended_at": "2026-03-08T23:00:01",
                    "duration_ms": 1000,
                    "input_summary": "输入文件 demo.xlsx。",
                    "processing_summary": "解析并标准化记录。",
                    "output_summary": "输出 30 条记录。",
                    "manual_verification": "确认时间范围与记录数量。",
                    "interaction_checkpoint": "init_data_range_confirm",
                    "interaction_response": "yes",
                    "llm_tasks": [
                        {
                            "task_key": "semantic_ai_review",
                            "provider": "direct",
                            "model": "gpt-test",
                            "status": "completed",
                            "duration_ms": 500,
                        }
                    ],
                }
            ],
        },
    }

    path = generator.generate_markdown_report(analysis_result, "traceability_test.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "### 全流程可追溯记录" in text
    assert "步骤 1: 数据加载与范围确认" in text
    assert "- 结果摘要: 输出 30 条记录。" in text
    assert "- 现场核验: 确认时间范围与记录数量。" in text
    assert "交互检查点: init_data_range_confirm（响应: yes）" not in text
    assert "LLM任务: semantic_ai_review" not in text
    assert "推理模型:" not in text
    assert "检索模型:" not in text


def test_stringify_repairs_latin1_mojibake(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = f"AI复核：{_to_latin1_mojibake('复核认为当前高风险')}"

    assert generator._stringify(raw) == "机理一致性复核：复核认为当前高风险"


def test_stringify_repairs_hex_escaped_utf8_in_nested_payload(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = [{"rank": 1, "cause": "1#\\xe8\\x86\\xa8\\xe8\\x83\\x80\\xe6\\x9c\\xbaB"}]
    rendered = generator._stringify(raw)

    assert "膨胀机B" in rendered
    assert "\\x" not in rendered


def test_stringify_repairs_mixed_mojibake_segments(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = "主换冷损持续偏高（+32.2%ã9ç¹）"
    rendered = generator._stringify(raw)

    assert rendered == "主换冷损持续偏高（+32.2%、9点）"


def test_stringify_collapses_repeated_cjk_noise(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    rendered = generator._stringify("装装装装装置处于高风险状态")

    assert rendered == "装置处于高风险状态"


def test_markdown_report_keeps_required_sections_with_placeholders(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 2,
    }

    path = generator.generate_markdown_report(analysis_result, "placeholder_sections.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 现场执行摘要" in text
    assert "## 附录：流程与追溯" in text
    assert "### 分析流程步骤" in text
    assert "### 全流程可追溯记录" in text
    for step in range(1, 9):
        assert f"### 步骤 {step}:" in text
    assert "- 耗时: 1 ms" in text


def test_markdown_report_unescapes_decision_newlines_and_uses_bold_subheadings(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 2,
        "decision_result": {
            "actionable_steps": "1) 先稳工况\\n2) 再优化参数",
            "risk_assessment": "存在联锁触发风险\\n需双人复核",
        },
    }

    path = generator.generate_markdown_report(analysis_result, "decision_newline.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "### **执行步骤**" in text
    assert "1) 先稳工况" in text
    assert "2) 再优化参数" in text
    assert "\\n" not in text


def test_markdown_report_rewrites_dify_step_title(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "analysis_steps": [{"step": 6, "title": "Dify 知识库检索手段", "summary": "mock"}],
    }

    path = generator.generate_markdown_report(analysis_result, "step_title_clean.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "Dify 知识库检索手段" not in text
    assert "6. **知识依据与处置参考**" in text


def test_markdown_report_splits_overall_summary_for_readability(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "overall_judgement": {
            "summary": "当前处于高风险异常失稳态。 | 专家复核：主矛盾在冷量系统单侧受限。",
            "highlights": [],
        },
        "analysis_steps": [
            {
                "step": 4,
                "title": "工况总览判断",
                "summary": "当前处于高风险异常失稳态。 | 专家复核：主矛盾在冷量系统单侧受限。",
            }
        ],
    }

    path = generator.generate_markdown_report(analysis_result, "overall_readability.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 工况复核摘要" in text
    assert "- 总体结论: 当前处于高风险异常失稳态。" in text
    assert "- 机理一致性复核: 主矛盾在冷量系统单侧受限。" in text
    assert "机理一致性复核：主矛盾在冷量系统单侧受限。" in text
    overview_block = text.split("## 附录：流程与追溯")[0]
    assert "当前处于高风险异常失稳态。 | 专家复核" not in overview_block


def test_single_line_text_normalizes_measure_punctuation(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    rendered = generator._single_line_text("1) 先核查。；2) 再调节。；3) 复核。")

    assert rendered == "1) 先核查；2) 再调节；3) 复核"
    assert "。；" not in rendered


def test_clean_business_text_fixes_incomplete_phrases(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = "优核查设备状态，时小步调整负荷。主要风险在冷量核心变量的高权重持续失。"
    cleaned = generator._clean_business_text(raw)

    assert "优先核查设备状态" in cleaned
    assert "必要时小步调整负荷" in cleaned
    assert "高权重持续失衡。" in cleaned


def test_clean_business_text_removes_confidence_and_garbled_separator(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = "1#主换￾主换冷损（置信度0.95）"
    cleaned = generator._clean_business_text(raw)

    assert cleaned == "1#主换-主换冷损"


def test_markdown_report_prefers_decision_verification_status_when_closed_loop_pending(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "analysis_steps": [{"step": 8, "title": "决策验证与报告生成", "summary": "验证状态为 通过。"}],
        "traceability": {
            "data_source": "sample",
            "step_traces": [
                {
                    "step": 8,
                    "title": "决策验证与报告生成",
                    "duration_ms": 100,
                    "output_summary": "验证状态=通过；闭环=待现场闭环；报告路径=demo.pdf / demo.md。",
                    "manual_verification": "按规程复核。",
                }
            ],
        },
        "decision_result": {
            "verification_status": "Passed",
            "actionable_steps": "1) 先稳工况",
            "closed_loop_validation": {"status": "pending", "summary": "待现场反馈。"},
        },
        "closed_loop_validation": {"status": "pending", "summary": "待现场反馈。"},
    }

    path = generator.generate_markdown_report(analysis_result, "verification_consistency.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "验证状态为 通过" in text
    assert "验证状态=通过" in text
    assert "- 验证状态: 通过" in text


def test_knowledge_references_include_reference_id_and_snippet_placeholder(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "knowledge_retrieval": {
            "retrieval_summary": "主检索：命中SOP条款。",
            "knowledge_references": ["空分装置操作规程 SOP-12"],
        },
    }

    path = generator.generate_markdown_report(analysis_result, "knowledge_reference_enriched.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 知识证据链与动作边界" in text
    assert "知识库已检索到资料，但当前未命中能直接支撑本轮判断的高相关证据。" in text
    assert "知识证据未形成硬支撑时，现场动作以在线工况、SOP 和人工复核结果为准。" in text


def test_dedupe_recommended_measures_removes_template_duplicates(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    measures = [
        {
            "title": "立即启动高风险处置流程",
            "target_issue": "膨胀机B制冷量严重偏低",
            "steps": "1) 先确认参数；2) 再执行联动检查",
        },
        {
            "title": "启动高风险处置流程",
            "target_issue": "膨胀机B制冷量严重偏低",
            "steps": "1) 先确认参数；2) 再执行联动检查",
        },
    ]

    deduped = generator._dedupe_recommended_measures(measures)

    assert len(deduped) == 1


def test_sample_data_source_is_rendered_as_field_style_label(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "traceability": {"data_source": "sample"},
    }

    path = generator.generate_markdown_report(analysis_result, "data_source_label.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "- **数据来源**: 生产现场数据（示例）" in text
    assert "- 数据来源: 生产现场数据（示例）" in text


def test_trace_output_mojibake_is_replaced_with_operator_placeholder(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    raw = "根因诊断：���������"
    text = generator._stringify_trace_output(raw, "未记录（模板占位）")

    assert text == "该步骤采用结构化结论呈现，详见下方“诊断结论/执行建议”章节。"


def test_markdown_report_adds_knowledge_evidence_and_conclusion_layers(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 2,
        "knowledge_retrieval": {
            "retrieval_summary": "主检索：命中SOP-01；校核检索：命中案例A-2024。",
            "knowledge_references": [
                {"source": "SOP-01", "page": "4.2", "content": "冷量异常处置先稳负荷后调优。"},
                "历史案例 A-2024（膨胀机B制冷量不足）",
            ],
            "recommended_measures": [
                {
                    "title": "稳定冷量",
                    "target_issue": "膨胀机B制冷量不足",
                    "steps": "单变量小步调整",
                    "expected_effect": "降低冷量缺口",
                    "safety_note": "保持联锁边界",
                }
            ],
        },
        "reasoning_result": {"operation_suggestion": "核查轴温、振动与联锁动作记录。"},
    }

    path = generator.generate_markdown_report(analysis_result, "evidence_layers.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 知识证据链与动作边界" in text
    assert "### **证据如何支撑当前判断**" in text
    assert "### **证据如何约束执行动作**" in text
    assert "SOP-01" in text
    assert "判断：" in text
    assert "动作约束：" in text
    assert "用于对照历史相似工况" not in text
    assert "## 结论分层（已确认/待核查）" in text
    assert "### **待现场核查项**" in text
    assert "设备振动趋势（含报警记录）" in text


def test_markdown_report_adds_transparency_layers(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-12 00:00:00",
        "status": "abnormal",
        "abnormal_count": 2,
        "overall_judgement": {
            "summary": "当前装置处于异常失稳态。",
            "reference_framework": [
                {
                    "name": "目标参考值",
                    "priority": 1,
                    "purpose": "用于判断是否偏离设计/操作目标，并作为最终异常判级依据。",
                    "drives_grading": True,
                }
            ],
            "baseline_references": [
                {
                    "indicator": "膨胀机B制冷量",
                    "target_reference_label": "配置参考值",
                    "reference_source_label": "配置参考值",
                    "reference_value": 360.0,
                    "history_baseline": 106.94,
                    "optimal_reference": 360.0,
                    "final_grade_basis_label": "目标参考值",
                    "reference_scope": "当前装置指标配置",
                    "comparison_method": "latest_snapshot_vs_fixed_reference",
                }
            ],
            "explainability": {
                "reference_provenance": [
                    {
                        "indicator_name": "膨胀机B制冷量",
                        "reference_value": 360.0,
                        "reference_basis_kind": "operation_target",
                        "reference_basis_kind_label": "运行目标值",
                        "reference_basis_text": "该值来自当前机组额定冷量操作目标，用于判断是否偏离目标工况。",
                        "applicable_scope": "1#空分装置冷量系统",
                        "applicable_conditions": "额定负荷、常规产品结构、非开停车模式",
                        "validation_status": "traceable_unvalidated",
                        "validation_status_label": "来源可追溯，尚未形成独立统计标定报告",
                        "comparison_basis": "latest_snapshot_vs_fixed_reference",
                        "final_grading_basis": "目标参考值",
                    }
                ],
                "rule_parameter_explanations": [
                    {
                        "title": "当前命中的风险等级规则",
                        "rule_name": "risk_level_thresholds",
                        "rule_version": "v1",
                        "current_inputs": {"abnormal_ratio": 0.333, "max_severity": 1.18},
                        "thresholds": {"critical": {"abnormal_ratio_gte": 0.45, "max_severity_gte": 1.05}},
                        "matched_branch": "critical",
                        "output": {"status_level": "critical", "status_text": "高风险"},
                        "origin_statement": "当前工程规则 / 初始标定，来源可追溯，尚未形成独立统计标定报告。",
                    }
                ],
                "dominant_anomaly_explanation": {
                    "candidate_label": "优先核查对象 / 疑似根因链起点",
                    "rank_explanation": "膨胀机B制冷量在本轮异常中 severity_score=1.180 排名第一，因此被列为优先核查对象。",
                    "duration_explanation": "膨胀机B制冷量已连续 116 个采样点保持异常状态，持续性满足优先核查条件。",
                    "subsystem_impact_explanation": "冷量系统当前聚合状态为 constrained，异常数=2/3，说明该异常已进入子系统聚合判断。",
                    "coupling_consistency_explanation": "主换冷损与其处于同一主导矛盾链路，当前耦合方向一致。",
                    "temporal_precedence_explanation": "当前未形成稳定时间先后证据，仅按严重度与持续性作为优先核查依据。",
                    "exclusion_boundary_explanation": "本项为优先核查对象 / 疑似根因链起点，不等于已确认根因。当前仍需排除测点异常、整体负荷或上游供气变化、主换或下游设备先发异常。",
                },
            },
            "evidence_layers": {
                "facts": [
                    "膨胀机B制冷量当前值为 69.91。",
                    "相对配置参考值 360 的偏差为 -80.6%。",
                    "相对历史运行基线 106.94 的偏差为 -34.6%。",
                ],
                "rules": ["风险等级触发：异常占比 33.3%、最大严重度 1.18，当前判为“高风险”。"],
                "actions": ["先确认膨胀机B测点、量纲与最新采样时刻是否有效。"],
            },
            "state_aggregation_rules": [
                {
                    "stage": "装置状态",
                    "rule_id": "plant_abnormal_ratio_and_max_severity",
                    "description": "abnormal_ratio>=0.45 或 max_severity>=1.05 判为 abnormal_unstable。",
                }
            ],
            "triggered_rules": ["装置状态触发：当前装置判为“异常失稳态”，主导矛盾为“冷量系统存在主导偏离：膨胀机B制冷量。”。"],
            "verification_loop": {
                "check_first": ["优先核查膨胀机B对应设备、测点和关键操作条件。"],
                "observe": ["观察膨胀机B制冷量是否按预期向回升方向改善，并连续保持至少 2 个观察窗口。"],
                "success_criteria": ["膨胀机B制冷量偏差收敛且持续点数不再扩展。"],
                "rollback_triggers": ["若膨胀机B制冷量未改善或继续恶化，立即停止当前调整并回退。"],
            },
            "explanation_boundary": "根因解释仅作为候选假设，需结合压力、阀位、温度、振动和操作日志完成现场确认。",
        },
        "reasoning_result": {
            "root_cause": "可能存在膨胀机B入口受阻；需结合振动趋势进一步确认。",
        },
        "decision_result": {
            "actionable_steps": "1) 先核查膨胀机B；2) 再稳负荷",
            "rollback_strategy": "若主换冷损继续恶化则回退。",
        },
    }

    path = generator.generate_markdown_report(analysis_result, "transparency_layers.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 证据分层与规则透明度" in text
    assert "### **基线与阈值来源**" in text
    assert "### **事实层**" in text
    assert "### **规则层**" in text
    assert "### **解释层**" in text
    assert "### **行动层**" in text
    assert "### **状态聚合规则**" in text
    assert "目标参考值（优先级 1）" in text
    assert "来源性质=运行目标值" in text
    assert "最终判级依据=目标参考值" in text
    assert "risk_level_thresholds@v1" in text
    assert "主导异常判读：优先核查对象 / 疑似根因链起点" in text
    assert "待核查假设：可能存在膨胀机B入口受阻" in text
    assert "根因解释仅作为候选假设" in text


def test_knowledge_support_maps_reference_to_action_boundary(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "knowledge_retrieval": {
            "knowledge_references": [
                {"source": "《深冷技术》2006年第05期", "content": "每月切换膨胀机时清扫机前过滤器，避免细小颗粒进入膨胀机。"},
                {"source": "《深冷技术》1995年第03期", "content": "液体产量比例与膨胀机效率、主换热器冷热端温差存在耦合关系，建议控制在3%以下。"},
                {"source": "《深冷技术》2001年第05期", "content": "可暂时从液氧罐向装置反送液氧，使主冷液氧液面达到正常值。"},
                {"source": "弱相关资料", "content": "对原标准做了编辑性修改，粗实线为改造后新增部分。"},
            ]
        }
    }

    support = generator._build_knowledge_support_view(analysis_result)

    assert any("过滤器堵塞" in item or "过滤器" in item for item in support["judgement_support"] + support["evidence_refs"])
    assert any("液体产量比例压至3%以下" in item for item in support["action_constraints"] + support["evidence_refs"])
    assert any("主冷液位必须优先守住" in item for item in support["action_constraints"] + support["evidence_refs"])
    assert any(item.startswith("判断：") and "动作约束：" in item for item in support["triads"])
    assert all("编辑性修改" not in item for item in support["judgement_support"] + support["evidence_refs"] + support["triads"])


def test_markdown_report_renders_knowledge_triads(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-12 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "knowledge_retrieval": {
            "knowledge_references": [
                {"source": "SOP-01", "page": "4.2", "content": "冷量异常处置先稳负荷后调优。"}
            ]
        },
        "reasoning_result": {"root_cause": "冷量系统受限。"},
    }

    path = generator.generate_markdown_report(analysis_result, "knowledge_triads.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "### **判断 / 依据 / 动作约束**" in text
    assert "判断：" in text
    assert "依据：" in text
    assert "动作约束：" in text


def test_markdown_report_preserves_upstream_root_cause_wording(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-12 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "reasoning_result": {
            "root_cause": "膨胀机B制冷量严重不足为优先核查对象，仍待现场确认。",
        },
        "overall_judgement": {
            "explanation_boundary": "根因解释仅作为候选假设，需结合压力、阀位、温度、振动和操作日志完成现场确认。",
        },
    }

    path = generator.generate_markdown_report(analysis_result, "softened_root_cause.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "膨胀机B制冷量严重不足为优先核查对象，仍待现场确认。" in text
    assert "当前主导异常" not in text


def test_markdown_report_frontloads_execution_summary_and_defers_trace_sections(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-10 00:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "overall_judgement": {"summary": "当前装置处于异常失稳态。"},
        "reasoning_result": {"root_cause": "主换冷损偏高与膨胀机B制冷量不足叠加。"},
        "decision_result": {"actionable_steps": "1) 立即稳负荷；2) 核查膨胀机B"},
        "analysis_steps": [{"step": 1, "title": "数据加载与范围确认", "summary": "已完成。"}],
        "traceability": {"data_source": "sample"},
    }

    path = generator.generate_markdown_report(analysis_result, "frontload_summary.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 现场执行摘要" in text
    assert "- **当前状态**:" in text
    assert text.index("## 现场执行摘要") < text.index("## 任务概览")
    assert text.index("## 附录：流程与追溯") > text.index("## 决策验证与执行建议")
    assert text.index("### 全流程可追溯记录") > text.index("### 分析流程步骤")


def test_markdown_report_adds_device_overview_and_dimension_sections(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-12 00:00:00",
        "status": "abnormal",
        "abnormal_count": 2,
        "semantic_data": [
            {"tag_id": "ext_1", "name": "氧提取率", "current_value": 97.2, "state_desc": "良好"},
            {"tag_id": "ext_2", "name": "氩提取率", "current_value": 73.4, "state_desc": "良好"},
            {"tag_id": "energy_1", "name": "空压机负荷", "current_value": 89.0, "state_desc": "一般"},
        ],
        "core_indicators": {
            "extraction_rate": {
                "ext_1": {"value": 97.2, "membership": 0.9, "state": "良好"},
                "ext_2": {"value": 73.4, "membership": 0.9, "state": "良好"},
            },
            "stability": {},
            "energy_consumption": {
                "energy_1": {"value": 89.0, "membership": 0.7, "state": "一般"},
            },
        },
        "overall_judgement": {
            "summary": "当前装置处于异常失稳态。",
            "status_text": "高风险",
            "plant_state_label": "异常失稳态",
            "total_count": 3,
            "abnormal_count": 2,
            "main_contradiction": "冷量系统存在主导偏离：膨胀机B制冷量。",
            "subsystem_states": [
                {"name": "冷量系统", "state": "constrained"},
                {"name": "分离系统", "state": "stable"},
            ],
            "three_level_state_engine": {"avg_optimal_gap": 0.182},
        },
        "baseline_profile": {"tag_count": 3},
        "abnormal_details": [
            {"name": "膨胀机B制冷量", "level": "严重偏低", "diff_percent": -80.6},
            {"name": "主换冷损", "level": "严重偏高", "diff_percent": 32.2},
        ],
    }

    path = generator.generate_markdown_report(analysis_result, "device_overview.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 装置总评" in text
    assert "## 分项状态判断" in text
    assert "- **总体判断**:" in text
    assert "- **当前与历史**:" in text
    assert "- **提取率**:" in text
    assert "- **单耗/能耗**:" in text
    assert "- **稳定性**:" not in text
    assert text.index("## 装置总评") < text.index("## 现场执行摘要")


def test_pending_checks_skip_missing_data_metadata_fields(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    confirmed, pending = generator._build_conclusion_layers(
        {
            "overall_judgement": {"summary": "当前冷量系统存在风险。"},
            "reasoning_result": {
                "missing_data_request": {
                    "needed": True,
                    "purpose": "用于区分设备能力衰减与设定偏差。",
                    "items": "膨胀机B振动趋势\n主换压降曲线",
                }
            },
        }
    )

    assert confirmed
    assert "膨胀机B振动趋势" in pending
    assert "主换压降曲线" in pending
    assert all(not item.startswith("needed") for item in pending)
    assert all(not item.startswith("purpose") for item in pending)


def test_execution_summary_prefers_structured_abnormal_overview(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    items = dict(
        generator._execution_summary_items(
            {
                "status": "abnormal",
                "abnormal_count": 2,
                "overall_judgement": {
                    "summary": "当前装置处于异常失稳态。",
                    "status_text": "高风险",
                    "plant_state_label": "异常失稳态",
                },
                "abnormal_details": [
                    {"name": "膨胀机B制冷量", "level": "严重偏低", "diff_percent": -80.6, "optimization_direction": "increase"},
                    {"name": "主换冷损", "level": "严重偏高", "diff_percent": 32.2, "optimization_direction": "decrease"},
                ],
                "core_indicators": {
                    "extraction_rate": {"ext_1": {"value": 97.2, "membership": 0.9, "state": "良好"}},
                    "stability": {},
                    "energy_consumption": {},
                },
                "reasoning_result": {
                    "root_cause": "长段文本不应直接主导首页摘要。",
                    "operation_suggestion": "1) 先做很长很长的动作说明；2) 再继续写很多细节。",
                },
                "decision_result": {
                    "actionable_steps": "1) 先做很长很长的动作说明；2) 再继续写很多细节。",
                    "rollback_strategy": "若异常继续恶化则回退。",
                },
            }
        )
    )

    assert items["当前状态"] == "高风险 / 异常失稳态（异常2项）"
    assert items["主问题"] == "膨胀机B制冷量严重偏低；主换冷损严重偏高。"
    assert items["立即动作"] == "先核膨胀机B入口温压，再查导叶/旁通/振动；同步盯主换冷损。"
    assert "连续保持至少 2 个观察窗口" in items["验收门槛"]
    assert "立即回退至上一稳定工况" in items["回退条件"]


def test_conclusion_pending_items_splits_missing_data_request(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    confirmed, pending = generator._build_conclusion_layers(
        {
            "overall_judgement": {"summary": "当前冷量系统存在风险。"},
            "reasoning_result": {
                "missing_data_request": {
                    "items": "膨胀机B振动趋势\n主换压降曲线",
                }
            }
        }
    )

    assert confirmed
    assert any(item == "膨胀机B振动趋势" for item in pending)
    assert any(item == "主换压降曲线" for item in pending)
    assert all(not item.startswith("items：") for item in pending)


def test_markdown_report_includes_visualization_section_and_image_reference(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-14 09:30:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "visualization_context": {
            "top_indicator_cards": [
                {
                    "rank": 1,
                    "indicator_name": "膨胀机B制冷量",
                    "tag_id": "exp_b",
                    "unit": "kW",
                    "current_value": 68.5,
                    "history_stats": {"median": 102.0, "percentile_rank": 4.2},
                    "references": {"target_reference": 360.0, "optimal_reference": 360.0},
                    "comparison_deltas": {
                        "vs_history_median": {"percent": -32.8},
                        "vs_target": {"percent": -81.0},
                        "vs_optimal": {"percent": -81.0},
                    },
                    "full_timeline": {
                        "series_start": "2026-03-14T00:00:00",
                        "series_end": "2026-03-14T09:30:00",
                        "abnormal_start": "2026-03-14T08:00:00",
                        "abnormal_end": "2026-03-14T09:30:00",
                    },
                    "recent_trend": {"window_point_count": 24},
                    "insight_text": "当前值明显低于历史中位和目标参考。",
                    "image_relative_path": "assets/analysis_report_demo/01_exp_b_comparison.png",
                }
            ]
        },
    }

    path = generator.generate_markdown_report(analysis_result, "visualization_section.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 时间对比可视化" in text
    assert "当前值=68.50 kW" in text
    assert "历史中位=102.00 kW" in text
    assert "![膨胀机B制冷量](assets/analysis_report_demo/01_exp_b_comparison.png)" in text


def test_pdf_rich_text_highlights_key_terms_and_numbers(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    rendered = generator._pdf_rich_text("当前状态：高风险；偏差：-80.6%；立即动作：先查膨胀机B。")

    assert "<b>当前状态</b>" in rendered
    assert "<b>高风险</b>" in rendered
    assert "<b>-80.6%</b>" in rendered
    assert "<b>立即动作</b>" in rendered
    assert "<b>先查</b>" in rendered


def test_pdf_report_includes_visualization_section_with_image(monkeypatch, tmp_path):
    monkeypatch.setattr(
        report_generator,
        "resolve_report_fonts",
        lambda: report_generator.ResolvedReportFonts(
            title_font="Helvetica",
            body_font="Helvetica",
            title_path="",
            body_path="",
            source="内置回退",
            fallback_reason="",
        ),
    )
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2NVxQAAAAASUVORK5CYII=")
    image_path = tmp_path / "comparison.png"
    image_path.write_bytes(png_bytes)

    analysis_result = {
        "timestamp": "2026-03-14 09:40:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "visualization_context": {
            "top_indicator_cards": [
                {
                    "rank": 1,
                    "indicator_name": "主换冷损",
                    "tag_id": "cold_loss",
                    "unit": "%",
                    "current_value": 114.0,
                    "history_stats": {"median": 72.0, "percentile_rank": 97.0},
                    "references": {"target_reference": 70.0, "optimal_reference": 65.0},
                    "comparison_deltas": {
                        "vs_history_median": {"percent": 58.3},
                        "vs_target": {"percent": 62.9},
                        "vs_optimal": {"percent": 75.4},
                    },
                    "full_timeline": {
                        "series_start": "2026-03-14T00:00:00",
                        "series_end": "2026-03-14T09:40:00",
                        "abnormal_start": "2026-03-14T08:30:00",
                        "abnormal_end": "2026-03-14T09:40:00",
                    },
                    "recent_trend": {"window_point_count": 24},
                    "insight_text": "当前值显著高于历史常态带。",
                    "image_path": str(image_path),
                }
            ]
        },
    }

    path = generator.generate_pdf_report(analysis_result, "visualization_section.pdf")

    assert path.endswith(".pdf")
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_markdown_report_includes_calculation_audit_section(monkeypatch, tmp_path):
    _mock_fonts(monkeypatch, tmp_path)
    generator = report_generator.ReportGenerator(output_dir=str(tmp_path / "out"))

    analysis_result = {
        "timestamp": "2026-03-16 10:00:00",
        "status": "abnormal",
        "abnormal_count": 1,
        "calculation_audit": {
            "history_model_metadata": {
                "profile_source": "runtime",
                "selected_regime": "low",
                "anchor_tag": "HY_2030_1#ZB_1_Energy_AirCompress_8",
                "global_fallback_used": False,
                "regime_cut_points": {"low_max": 91.2, "high_min": 96.4},
            },
            "data_intake": {
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
                "count_change_reason": "纳入首个真实时间点。",
            },
            "indicators": [
                {
                    "name": "膨胀机B制冷量",
                    "current_value": 69.91,
                    "target_reference": 360.0,
                    "history_baseline": 106.94,
                    "optimal_reference": 384.93,
                    "selected_regime": "low",
                    "statistical_state": "high",
                    "statistical_anomaly_score": 0.91,
                    "agreement_flag": "agree",
                    "hybrid_severity_score": 1.7096,
                    "final_grade_basis_label": "目标参考值",
                    "state_label": "严重偏低",
                    "severity_score": 1.4821,
                }
            ],
            "subsystems": [
                {
                    "name": "冷量系统",
                    "members": ["膨胀机B制冷量", "主换冷损"],
                    "abnormal_count": 1,
                    "total_count": 2,
                    "abnormal_ratio": 0.5,
                    "avg_severity": 1.4821,
                    "state": "constrained",
                    "triggered_by": ["avg_severity>=1.00"],
                }
            ],
            "plant": {
                "abnormal_ratio": 0.5,
                "max_severity": 1.4821,
                "avg_optimal_gap": 0.18,
                "risk_level_label": "高风险",
                "risk_branch": "critical",
                "plant_state_label": "异常失稳态",
                "plant_state_branch": "abnormal_unstable",
                "dominant_anomaly": {
                    "indicator_name": "膨胀机B制冷量",
                    "candidate_label": "优先核查对象 / 疑似根因链起点",
                    "temporal_precedence_explanation": "较其他异常领先 107 个点。",
                    "boundary": "不等于已确认根因。",
                },
                "main_contradiction": "冷量系统存在主导偏离。",
            },
        },
    }

    path = generator.generate_markdown_report(analysis_result, "calculation_audit.md")
    text = Path(path).read_text(encoding="utf-8")

    assert "## 中间计算审计" in text
    assert "### **数据接入口径**" in text
    assert "### **单指标审计表**" in text
    assert "### **历史统计判断**" in text
    assert "### **子系统与装置聚合输入**" in text
    assert "2025-01-01 00:00:00" in text
    assert "膨胀机B制冷量" in text
    assert "工况档位=低负荷" in text
    assert "1.482" in text
