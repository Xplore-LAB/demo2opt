import json
import os
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.prompts.templates import SimpleLLMClient
from src.schemas.models import CoreIndicatorsModel, ReasoningResultModel
from src.utils.llm_json import extract_json_object, repair_llm_text

load_dotenv()


class ReasoningConfigurationError(ValueError):
    pass


class ReasoningExecutionError(RuntimeError):
    pass


class ReasoningEngineV2:
    COMMON_ENGLISH_PHRASES = {
        "Energy and extraction indicators may be coupled.": "能耗指标与提取率指标可能存在耦合关系。",
        "Stability metrics are low and may affect performance.": "稳定性指标偏低，可能影响系统性能。",
        "No strong coupling identified.": "未识别到显著耦合关系。",
        "No analyzable abnormal data detected.": "未检测到可分析的异常数据。",
        "Keep current operation and continue monitoring.": "建议维持当前工况并持续监测。",
        "No extra warning.": "当前无额外安全警告。",
        "Input data is empty.": "输入数据为空。",
        "Need manual review before execution.": "执行前需人工复核。",
        "Use standard procedures and interlock constraints.": "请遵循标准操作规程并严格满足联锁约束。",
    }

    def __init__(
        self,
        use_dify: Optional[bool] = None,
        use_direct_llm: Optional[bool] = None,
        dify_config: Optional[Dict] = None,
        llm_config: Optional[Dict] = None,
    ):
        if use_dify:
            raise ReasoningConfigurationError("Dify 仅用于知识检索步骤，不再作为推理模式。")
        if dify_config:
            # Keep the parameter for backward compatibility, but reasoning does not consume Dify config.
            _ = dify_config
        if use_direct_llm is False:
            raise ReasoningConfigurationError("推理流程仅支持直连 LLM，请移除 use_direct_llm=False。")
        self.client = self._build_direct_client(llm_config)

    @staticmethod
    def _extract_client_error(response: Dict[str, Any]) -> str:
        error = response.get("error")
        if isinstance(error, dict):
            return f"{error.get('code', 'LLM_ERROR')}: {error.get('message', '')}".strip(": ")
        if isinstance(error, str):
            return error
        return "LLM request failed"

    def _build_direct_client(self, llm_config: Optional[Dict]) -> SimpleLLMClient:
        api_key = llm_config.get("api_key") if llm_config else os.getenv("LLM_API_KEY")
        base_url = llm_config.get("base_url") if llm_config else os.getenv("LLM_BASE_URL")
        model_name = llm_config.get("model") if llm_config else os.getenv("LLM_MODEL_NAME")
        if not api_key:
            raise ReasoningConfigurationError("Direct LLM API key is missing.")
        if not base_url or not model_name:
            raise ReasoningConfigurationError("Direct LLM base_url/model is missing.")
        return SimpleLLMClient(api_url=base_url, api_key=api_key, model_name=model_name)

    def ask_assistant(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> str:
        _ = inputs  # 保留参数兼容，推理统一使用直连 LLM。
        response = self.client.chat(
            query=user_prompt,
            system_prompt=system_prompt or "You are an industrial process assistant.",
            temperature=temperature,
        )
        if not response.get("ok", True):
            raise ReasoningExecutionError(self._extract_client_error(response))
        return response.get("answer", "")

    def identify_bottleneck_indicators(self, core_indicators: CoreIndicatorsModel) -> List[str]:
        result = []
        for category, indicators in [
            ("extraction_rate", core_indicators.extraction_rate),
            ("stability", core_indicators.stability),
            ("energy_consumption", core_indicators.energy_consumption),
        ]:
            for tag_id, data in indicators.items():
                if (data or {}).get("membership", 1.0) < 0.8:
                    result.append(f"{category}: {tag_id}")
        return result

    def analyze_coupling_relationships(self, core_indicators: CoreIndicatorsModel) -> str:
        notes = []
        if core_indicators.energy_consumption and core_indicators.extraction_rate:
            notes.append("能耗指标与提取率指标可能存在耦合关系。")
        if core_indicators.stability:
            members = [d.get("membership", 1.0) for d in core_indicators.stability.values()]
            if members and sum(members) / len(members) < 0.8:
                notes.append("稳定性指标偏低，可能影响系统性能。")
        return "；".join(notes) if notes else "未识别到显著耦合关系。"

    def _localize_common_phrases(self, text: str) -> str:
        if not text:
            return text
        output = text
        for en, zh in self.COMMON_ENGLISH_PHRASES.items():
            output = output.replace(en, zh)
        return output

    def _normalize_text_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            joined = "\n".join(str(item).strip() for item in value if str(item).strip())
            return self._localize_common_phrases(repair_llm_text(joined))
        if isinstance(value, dict):
            try:
                return self._localize_common_phrases(repair_llm_text(json.dumps(value, ensure_ascii=False)))
            except Exception:
                return self._localize_common_phrases(repair_llm_text(str(value)))
        return self._localize_common_phrases(repair_llm_text(str(value).strip()))

    def _normalize_missing_data_request(self, value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return {"items": items} if items else None
        text = str(value).strip()
        return {"description": text} if text else None

    def _normalize_indicator_diagnoses(self, value: Any) -> List[Dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            text = str(value).strip()
            return [{"name": "未命名指标", "ai_reason": text}] if text else []

        normalized: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("tag_id") or item.get("indicator") or "未命名指标"
                reason = item.get("ai_reason") or item.get("reason") or item.get("analysis") or item.get("desc") or ""
                reason_text = self._normalize_text_value(reason)
                if reason_text:
                    normalized.append(
                        {
                            "name": self._normalize_text_value(name) or "未命名指标",
                            "ai_reason": reason_text,
                            "confidence": item.get("confidence"),
                        }
                    )
                continue
            text = self._normalize_text_value(item)
            if text:
                normalized.append({"name": "未命名指标", "ai_reason": text})
        return normalized

    def _normalize_reasoning_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        normalized = dict(payload)
        for key in ("root_cause", "operation_suggestion", "safety_warning", "thought_process", "coupling_analysis"):
            if key in normalized:
                normalized[key] = self._normalize_text_value(normalized.get(key))

        if "bottleneck_indicators" in normalized:
            raw = normalized.get("bottleneck_indicators")
            if raw is None:
                normalized["bottleneck_indicators"] = []
            elif isinstance(raw, list):
                normalized["bottleneck_indicators"] = [self._normalize_text_value(item) for item in raw if self._normalize_text_value(item)]
            else:
                text = self._normalize_text_value(raw)
                normalized["bottleneck_indicators"] = [text] if text else []

        if "missing_data_request" in normalized:
            normalized["missing_data_request"] = self._normalize_missing_data_request(normalized.get("missing_data_request"))
        if "indicator_diagnoses" in normalized:
            normalized["indicator_diagnoses"] = self._normalize_indicator_diagnoses(normalized.get("indicator_diagnoses"))

        return normalized

    def analyze(
        self,
        semantic_data: List[Dict],
        core_indicators: Optional[CoreIndicatorsModel] = None,
        enable_cot: bool = True,
        features: Optional[Dict] = None,
        system_state: Optional[Dict] = None,
        task_note: str = "",
        abnormal_items: Optional[List[Dict]] = None,
        bottleneck_indicators: Optional[List[str]] = None,
        coupling_analysis: Optional[str] = None,
        knowledge_context: Optional[Dict[str, Any]] = None,
        overall_judgement: Optional[Dict[str, Any]] = None,
    ) -> str:
        abnormal_items = abnormal_items if abnormal_items is not None else semantic_data
        if isinstance(core_indicators, dict):
            core_indicators = SimpleNamespace(
                extraction_rate=dict(core_indicators.get("extraction_rate") or {}),
                stability=dict(core_indicators.get("stability") or {}),
                energy_consumption=dict(core_indicators.get("energy_consumption") or {}),
            )
        if not abnormal_items and not features:
            payload = ReasoningResultModel(
                root_cause="未检测到可分析的异常数据。",
                operation_suggestion="建议维持当前工况并持续监测。",
                safety_warning="当前无额外安全警告。",
                thought_process="输入数据为空。",
                bottleneck_indicators=[],
                coupling_analysis="暂无可用于耦合分析的数据。",
                indicator_diagnoses=[],
            )
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            return json.dumps(data, ensure_ascii=False, indent=2)

        if bottleneck_indicators is None:
            bottleneck_indicators = self.identify_bottleneck_indicators(core_indicators) if core_indicators else []
        if coupling_analysis is None:
            coupling_analysis = self.analyze_coupling_relationships(core_indicators) if core_indicators else ""

        try:
            raw = self.client.analyze_with_knowledge(
                abnormal_items,
                enable_cot=enable_cot,
                bottleneck_indicators=bottleneck_indicators,
                coupling_analysis=coupling_analysis,
                semantic_data=semantic_data,
                features=features,
                system_state=system_state,
                task_note=task_note,
                knowledge_context=knowledge_context,
                overall_judgement=overall_judgement,
            )
            if isinstance(raw, dict) and "ok" in raw and not raw.get("ok", True):
                raise ReasoningExecutionError(self._extract_client_error(raw))
            parsed = self._normalize_reasoning_payload(self._parse_response(raw))
            parsed["raw_response"] = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            validated = ReasoningResultModel(**parsed)
            data = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
            return json.dumps(data, ensure_ascii=False, indent=2)
        except ReasoningExecutionError:
            raise
        except Exception as exc:
            raise ReasoningExecutionError(f"LLM reasoning failed: {exc}") from exc

    def _parse_response(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            if "answer" in raw and isinstance(raw["answer"], str):
                return self._parse_response(raw["answer"])
            return raw
        if not isinstance(raw, str):
            raise ReasoningExecutionError("LLM_RESPONSE_TYPE_ERROR: response is not a string/dict.")
        text = raw.strip()
        parsed = self._try_parse_json_text(text)
        if parsed is not None:
            return parsed
        preview = text.replace("\n", " ")[:240]
        raise ReasoningExecutionError(
            f"LLM_NON_JSON_RESPONSE: model returned non-JSON content. preview={preview}"
        )

    def _try_parse_json_text(self, text: str) -> Optional[Dict]:
        return extract_json_object(text)
