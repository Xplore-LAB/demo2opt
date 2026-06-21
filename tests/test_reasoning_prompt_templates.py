import json

from src.prompts.templates import DifyAPIClient, SimpleLLMClient, build_reasoning_with_knowledge_prompts


def test_build_reasoning_with_knowledge_prompts_contains_required_schema_fields():
    prompts = build_reasoning_with_knowledge_prompts(
        overall_judgement={"summary": "主换冷损偏高"},
        knowledge_context={"retrieval_summary": "命中数据集"},
        system_state={},
        semantic_data=[{"name": "主换冷损"}],
        features={},
        abnormal_data=[{"name": "主换冷损", "level": "偏高"}],
        bottleneck_indicators=["主换冷损"],
        coupling_analysis="负荷波动与冷损耦合",
        task_note="请给出可执行建议",
    )

    assert "system_prompt" in prompts
    assert "user_prompt" in prompts
    assert "root_cause" in prompts["user_prompt"]
    assert "operation_suggestion" in prompts["user_prompt"]
    assert "safety_warning" in prompts["user_prompt"]


def test_simple_llm_client_analyze_with_knowledge_uses_template_builder(monkeypatch):
    monkeypatch.setattr(
        "src.prompts.templates.build_reasoning_with_knowledge_prompts",
        lambda **kwargs: {"system_prompt": "SYS_PROMPT", "user_prompt": "USER_PROMPT"},
    )

    captured = {}

    client = SimpleLLMClient(
        api_url="https://api.openai.com/v1/chat/completions",
        api_key="k",
        model_name="gpt-4o-mini",
    )

    def fake_chat(query, system_prompt="", temperature=0.0):
        captured["query"] = query
        captured["system_prompt"] = system_prompt
        captured["temperature"] = temperature
        return {"ok": True, "answer": json.dumps({"root_cause": "x"}, ensure_ascii=False)}

    client.chat = fake_chat
    answer = client.analyze_with_knowledge(abnormal_data=[{"name": "x"}], enable_cot=True)

    assert captured["query"] == "USER_PROMPT"
    assert captured["system_prompt"] == "SYS_PROMPT"
    assert captured["temperature"] == 0.2
    assert isinstance(answer, str)


def test_dify_client_analyze_with_knowledge_uses_template_builder(monkeypatch):
    monkeypatch.setattr(
        "src.prompts.templates.build_reasoning_with_knowledge_prompts",
        lambda **kwargs: {"system_prompt": "SYS_PROMPT", "user_prompt": "USER_PROMPT"},
    )

    captured = {}
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="k")

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "answer": "{}"}

    client.chat = fake_chat
    answer = client.analyze_with_knowledge(abnormal_data=[{"name": "x"}], enable_cot=False)

    assert "SYS_PROMPT" in captured["query"]
    assert "USER_PROMPT" in captured["query"]
    assert captured["inputs"] == {"stage": "reasoning", "output_format": "json"}
    assert answer == "{}"
