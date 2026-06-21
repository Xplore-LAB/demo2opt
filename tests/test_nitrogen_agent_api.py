import pytest

from src.api.rest import server


@pytest.fixture()
def client():
    return server.app.test_client()


def test_nitrogen_agent_analyze_brief_returns_quick_sentence(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "_load_llm_configs",
        lambda: [{"name": "demo", "base_url": "https://example.com", "api_key": "key", "model": "mock-model"}],
    )

    def fail_if_called(_context):
        raise AssertionError("brief 模式不应触发完整 LLM 调用")

    monkeypatch.setattr(server, "_call_agent_llm", fail_if_called)

    response = client.post(
        "/api/nitrogen-agent/analyze",
        json={
            "event_id": "E-1",
            "start_ms": 1710000000000,
            "end_ms": 1710003600000,
            "level": "high",
            "trigger_tags": ["AI705", "AI701"],
            "detail_level": "brief",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["analysis_mode"] == "brief_rule"
    assert body["data"]["decision_source"] == "rule_engine"
    assert body["data"]["explanation_source"] == "rule_engine"
    assert body["data"]["llm_trace"]["status"] == "brief_ready"
    assert "初判为重度氮塞" in body["data"]["llm_sentence"]


def test_nitrogen_agent_analyze_full_returns_llm_enhanced_result(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "_load_llm_configs",
        lambda: [{"name": "demo", "base_url": "https://example.com", "api_key": "key", "model": "mock-model"}],
    )
    monkeypatch.setattr(
        server,
        "_call_agent_llm",
        lambda _context: (
            {
                "conclusion": "高风险疑似氮塞",
                "summary": "模型补充：建议优先复核粗氩系统。",
                "top_event_judgement": {"node": "T0", "title": "T0 疑似氮塞顶事件", "status": "已触发", "logic": "主触发 + 多测点联动", "items": []},
                "basis": [{"tag": "AI705", "value": "偏高", "basis": "持续异常"}],
                "evidence_nodes": [{"evidence": "AI705 连续异常", "node": "T0", "status": "强触发", "explanation": "主触发成立"}],
                "fault_tree_path": ["T0 疑似氮塞：已触发"],
                "branch_ranking": [{"rank": 1, "branch": "粗氩系统自身异常", "status": "优先排查", "reason": "主触发命中", "next_step": "复核阻力"}],
                "key_missing_data": [{"data": "粗氩塔阻力", "node": "A3", "purpose": "确认塔阻力异常"}],
                "cause_branches": [{"branch": "粗氩系统", "cause": "粗氩侧组分异常", "support_level": "优先"}],
                "material_balance_review": "物料平衡暂不支持仅由负荷扰动解释。",
                "fault_tree_steps": [{"title": "先看粗氩系统", "focus": "A 分支", "checks": ["AI705"], "reason": "主触发命中", "action": "补充阻力"}],
                "action_advice": ["补充粗氩塔阻力。"],
                "review_tags": ["AI705"],
                "missing_information": ["粗氩塔阻力"],
                "manual_review_required": True,
                "_model_name": "mock-model",
                "_model_config_name": "demo",
            },
            "",
            {"attempts": [{"config": "demo", "model": "mock-model", "message": "ok"}]},
        ),
    )

    response = client.post(
        "/api/nitrogen-agent/analyze",
        json={
            "event_id": "E-2",
            "start_ms": 1710000000000,
            "end_ms": 1710003600000,
            "level": "high",
            "trigger_tags": ["AI705", "AI701"],
            "detail_level": "full",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["analysis_mode"] == "llm_enhanced"
    assert body["data"]["decision_source"] == "rule_engine"
    assert body["data"]["decision_label"] == "规则主判定"
    assert body["data"]["explanation_source"] == "llm"
    assert body["data"]["explanation_label"] == "智能补充说明"
    assert body["data"]["llm_trace"]["status"] == "succeeded"
    assert body["data"]["llm_trace"]["model"] == "mock-model"
    assert body["data"]["llm_trace"]["attempts"][0]["config"] == "demo"
    assert body["data"]["llm_sentence"] == "模型补充：建议优先复核粗氩系统。"


def test_nitrogen_agent_analyze_llm_failure_keeps_rule_fallback(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "_load_llm_configs",
        lambda: [{"name": "demo", "base_url": "https://example.com", "api_key": "key", "model": "mock-model"}],
    )
    monkeypatch.setattr(
        server,
        "_call_agent_llm",
        lambda _context: (
            None,
            "demo(mock-model): 调用失败",
            {"attempts": [{"config": "demo", "model": "mock-model", "code": "LLM_REQUEST_ERROR"}]},
        ),
    )

    response = client.post(
        "/api/nitrogen-agent/analyze",
        json={
            "event_id": "E-FAIL",
            "start_ms": 1710000000000,
            "end_ms": 1710003600000,
            "level": "medium",
            "trigger_tags": ["AI705"],
            "detail_level": "full",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["analysis_mode"] == "rule_based"
    assert body["data"]["decision_source"] == "rule_engine"
    assert body["data"]["explanation_source"] == "rule_engine"
    assert body["data"]["fallback_source"] == "backend_llm"
    assert body["data"]["llm_trace"]["status"] == "failed"
    assert body["data"]["llm_trace"]["error_code"] == "LLM_REQUEST_ERROR"
    assert body["data"]["llm_trace"]["error_reason"] == "demo(mock-model): 调用失败"
    assert body["data"]["llm_trace"]["attempts"][0]["code"] == "LLM_REQUEST_ERROR"
    assert body["data"]["analysis_fallback_reason"] == "demo(mock-model): 调用失败"
    assert "规则兜底结论" not in body["data"]["llm_sentence"]


def test_nitrogen_agent_analyze_stage_returns_trace_payload(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "_load_llm_configs",
        lambda: [{"name": "demo", "base_url": "https://example.com", "api_key": "key", "model": "mock-model"}],
    )

    def fail_if_called(_context):
        raise AssertionError("阶段模式不应触发完整 LLM 调用")

    monkeypatch.setattr(server, "_call_agent_llm", fail_if_called)

    response = client.post(
        "/api/nitrogen-agent/analyze",
        json={
            "event_id": "E-3",
            "start_ms": 1710000000000,
            "end_ms": 1710003600000,
            "level": "high",
            "trigger_tags": ["AI705", "AI701"],
            "operating_mode": {"mode": "steady_load", "label": "固定负荷/稳态窗口", "dynamic": False},
            "load_baseline": {"basis": "历史同负荷样本 18 点"},
            "material_balance": {"result": "当前负荷基准 2.10%，当前均值 2.16%，较基准 +0.03%", "conclusion": "范围内"},
            "directional_checks": [{"tag": "AI705", "directionText": "偏低风险", "basis": "基准 90.1，当前 89.2"}],
            "analysis_stage": "material_balance",
            "detail_level": "stage",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["analysis_mode"] == "stage_material_balance"
    assert body["data"]["trace_stage"] == "material_balance"
    assert body["data"]["trace_title"] == "步骤2：检查物料平衡"
    assert body["data"]["material_balance_formula_status"] == "implemented"
    assert body["data"]["material_balance_mode"] == "steady_load"
    assert body["data"]["load_baseline"]["basis"] == "历史同负荷样本 18 点"
    assert body["data"]["directional_checks"][0]["directionText"] == "偏低风险"
    assert body["data"]["llm_trace"]["status"] == "stage_ready"


def test_nitrogen_agent_analyze_preserves_ai705_shape_evidence(client, monkeypatch):
    monkeypatch.setattr(server, "_load_llm_configs", lambda: [])

    response = client.post(
        "/api/nitrogen-agent/analyze",
        json={
            "event_id": "NP-001",
            "start_ms": 1710000000000,
            "end_ms": 1710003600000,
            "level": "medium",
            "trigger_tags": ["AI705"],
            "detail_level": "brief",
            "shape_evidence": {
                "shapeText": "多谷下凹",
                "workpoint": 99.84,
                "minValue": 99.21,
                "dipDepth": 0.63,
                "recoveryRatio": 0.82,
                "basis": "按6h窗口剔除下凹点估计工作点 99.84，识别到多谷下凹。",
            },
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["basis"][0]["tag"] == "AI705"
    assert "多谷下凹" in body["data"]["basis"][0]["value"]
    assert body["data"]["shape_evidence"]["shapeText"] == "多谷下凹"
    assert body["data"]["top_event_judgement"]["items"][0]["item"] == "AI705 下凹形态"


def test_selected_nitrogen_demo_manifest_returns_e11(client):
    response = client.get("/api/nitrogen-demo-selected/manifest")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["default_case"] == "E11"
    assert any(item["event_id"] == "E11" for item in body["data"]["demo_cases"])
    assert any(row["事件编号"] == "E11" for row in body["data"]["summary"])


def test_selected_nitrogen_demo_file_serves_window_csv(client):
    response = client.get("/api/nitrogen-demo-selected/file/03_event_windows_1min/E11_window_1min_median.csv")

    assert response.status_code == 200
    assert b"timestamp" in response.data[:200]
