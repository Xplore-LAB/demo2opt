import json
import os
import random
import time
from typing import Any, Dict, Generator, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default




def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_semantic_ai_review_prompts(
    semantic_data: List[Dict[str, Any]],
    abnormal_details: List[Dict[str, Any]],
    overall_judgement: Dict[str, Any],
    task_note: str = "",
) -> Dict[str, str]:
    snapshot = [
        {
            "tag_id": item.get("tag_id"),
            "name": item.get("name"),
            "state_desc": item.get("state_desc"),
            "current_value": item.get("current_value"),
            "diff": item.get("diff"),
            "assessment_reason": item.get("assessment_reason"),
            "comparison_summary": item.get("comparison_summary"),
        }
        for item in semantic_data[:30]
    ]
    abnormal_snapshot = [
        {
            "tag_id": item.get("tag_id"),
            "name": item.get("name"),
            "level": item.get("level"),
            "rule_reason": item.get("rule_reason"),
            "trend": item.get("trend"),
            "window": item.get("window"),
        }
        for item in abnormal_details[:20]
    ]
    task_note_block = f"\n\n【任务备注】\n{task_note.strip()}" if task_note and task_note.strip() else ""
    system_prompt = (
        "你是空分装置语义分析复核专家。"
        "你需要在不推翻规则层硬约束的前提下，补充工艺语义解释并给出复核意见。"
        "仅返回单个 JSON 对象。"
    )
    user_prompt = f"""请对“规则层语义分析”做 AI 复核，目标是提升状态判定与工况总览的专业准确性。
【规则层工况总览】{_to_json(overall_judgement)}
{task_note_block}

【规则层快照语义（样本）】{_to_json(snapshot)}

【规则层异常详情（样本）】{_to_json(abnormal_snapshot)}

输出 JSON 字段要求：
{{
  "summary_refinement": "对工况总览的补充摘要",
  "highlights_refinement": ["补充要点1", "补充要点2"],
  "state_reviews": [
    {{
      "tag_id": "可为空",
      "name": "指标名",
      "suggested_state": "建议状态",
      "reason": "复核依据",
      "confidence": "high/medium/low"
    }}
  ],
  "risk_focus": ["优先关注风险点"]
}}"""
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def build_dify_knowledge_retrieval_prompts(
    overall_judgement: Dict[str, Any],
    abnormal_details: List[Dict[str, Any]],
    task_note: str = "",
) -> Dict[str, str]:
    abnormal_snapshot = [
        {
            "name": item.get("name"),
            "tag_id": item.get("tag_id"),
            "level": item.get("level"),
            "rule_reason": item.get("rule_reason"),
            "ai_reason": item.get("ai_reason"),
            "trend": item.get("trend"),
        }
        for item in abnormal_details[:20]
    ]
    task_note_block = f"\n\n【任务备注】\n{task_note.strip()}" if task_note and task_note.strip() else ""
    system_prompt = (
        "你是空分装置知识检索助手。"
        "请基于工况摘要提炼可执行处置手段。"
        "仅返回单个 JSON 对象。"
    )
    user_prompt = f"""请根据以下工况摘要执行知识检索并提炼可执行手段。
【工况总览】{_to_json(overall_judgement)}
{task_note_block}

【异常候选（样本）】{_to_json(abnormal_snapshot)}

请输出 JSON：
{{
  "retrieval_summary": "本次检索结论",
  "recommended_measures": [
    {{
      "title": "手段标题",
      "target_issue": "针对问题",
      "steps": "操作步骤",
      "expected_effect": "预期效果",
      "safety_note": "安全注意事项",
      "priority": "high/medium/low"
    }}
  ],
  "knowledge_references": ["知识来源1", "知识来源2"],
  "risk_tips": ["风险提示1", "风险提示2"]
}}"""
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def build_decision_ai_verification_prompts(
    reasoning_result: Dict[str, Any],
    rule_decision: Dict[str, Any],
    knowledge_context: Dict[str, Any],
    overall_judgement: Dict[str, Any],
    task_note: str = "",
) -> Dict[str, str]:
    task_note_block = f"\n\n【任务备注】\n{task_note.strip()}" if task_note and task_note.strip() else ""
    system_prompt = (
        "你是空分装置决策验证专家。"
        "请在规则层结论基础上做 AI 校核与效果推演，输出可执行且可回退的建议。"
        "仅返回单个 JSON 对象。"
    )
    user_prompt = f"""请对“规则层决策建议”做 AI 验证与优化。
【工况总览】{_to_json(overall_judgement)}
{task_note_block}

【根因诊断结果】{_to_json(reasoning_result)}

【知识检索结果】{_to_json(knowledge_context)}

【规则层决策结果】{_to_json(rule_decision)}

请输出 JSON：
{{
  "actionable_steps": "最终建议步骤",
  "simulation_result": "效果推演",
  "verification_status": "Passed/Pending/Failed",
  "risk_assessment": "风险评估",
  "rollback_strategy": "回退策略",
  "confidence_score": 0.0
}}"""
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def build_reasoning_with_knowledge_prompts(
    overall_judgement: Dict[str, Any],
    knowledge_context: Dict[str, Any],
    system_state: Dict[str, Any],
    semantic_data: List[Dict[str, Any]],
    features: Dict[str, Any],
    abnormal_data: List[Dict[str, Any]],
    bottleneck_indicators: List[str],
    coupling_analysis: str,
    task_note: str = "",
) -> Dict[str, str]:
    task_note_block = f"\n\n【任务备注】\n{task_note.strip()}" if task_note and task_note.strip() else ""
    payload = {
        "overall_judgement": overall_judgement or {},
        "knowledge_context": knowledge_context or {},
        "system_state": system_state or {},
        "semantic_data": (semantic_data or [])[:40],
        "features": features or {},
        "abnormal_data": (abnormal_data or [])[:20],
        "bottleneck_indicators": bottleneck_indicators or [],
        "coupling_analysis": coupling_analysis or "",
        "task_note": task_note or "",
    }

    system_prompt = (
        "你是空分装置运行分析专家。"
        "你必须输出单个 JSON 对象，不要输出 Markdown、代码块或额外说明。"
        "除字段名外，所有自然语言内容必须使用中文。"
    )
    user_prompt = f"""请根据以下输入完成根因诊断，并返回严格 JSON。
{task_note_block}

【输入数据】
{_to_json(payload)}

输出 JSON 必须包含字段：
- thought_process
- root_cause
- operation_suggestion
- safety_warning
- bottleneck_indicators
- coupling_analysis
- missing_data_request
- indicator_diagnoses
- knowledge_references

字段要求：
1. root_cause / operation_suggestion / safety_warning 必须为非空字符串。
2. root_cause 字段只能描述“主导异常、疑似根因链起点、待核查假设”，不得写成“已确认根因”“根因已锁定”或类似表述。
3. indicator_diagnoses 必须是数组，每项至少包含 name 与 ai_reason。
4. missing_data_request 可为 null 或对象。
5. 仅输出 JSON 对象本身。"""
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}
class SimpleLLMClient:
    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model_name: str = None,
        knowledge_manager=None,
        timeout_sec: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_sec: Optional[float] = None,
    ):
        self.api_url = api_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
        self.knowledge_manager = knowledge_manager
        self.timeout_sec = timeout_sec if timeout_sec is not None else _int_env("LLM_TIMEOUT_SEC", 120)
        self.max_retries = max_retries if max_retries is not None else _int_env("LLM_RETRY_MAX", 3)
        self.retry_backoff_sec = retry_backoff_sec if retry_backoff_sec is not None else _float_env("LLM_RETRY_BACKOFF_SEC", 0.5)
        self.retry_jitter_sec = _float_env("LLM_RETRY_JITTER_SEC", 0.2)
        self.retry_multiplier = _float_env("LLM_RETRY_MULTIPLIER", 2.0)
        if self.api_url.endswith("/"):
            self.api_url = self.api_url[:-1]
        if not any(self.api_url.endswith(suffix) for suffix in ["/chat/completions", "/messages", "/generate"]):
            self.api_url = f"{self.api_url}/v1/messages" if "claude" in self.model_name.lower() else f"{self.api_url}/chat/completions"

    def _build_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _build_payload(
        self,
        query: str,
        system_prompt: str,
        temperature: float,
        stream: bool = False,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        if "/messages" in self.api_url:
            payload = {
                "model": self.model_name,
                "system": system_prompt,
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 4096,
                "temperature": temperature,
            }
        else:
            payload = {
                "model": self.model_name,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                "temperature": temperature,
            }
            if response_format:
                payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
        return payload

    def _build_error_response(self, code: str, message: str, retriable: bool) -> Dict:
        return {"ok": False, "answer": "", "error": {"code": code, "message": message, "retriable": retriable}}

    def _retry_delay(self, attempt: int) -> float:
        return self.retry_backoff_sec * (self.retry_multiplier ** max(attempt, 0)) + random.uniform(0.0, self.retry_jitter_sec)

    def _is_retriable_request_error(self, exc: requests.exceptions.RequestException) -> bool:
        response = getattr(exc, "response", None)
        if response is None:
            return True
        return response.status_code in {408, 409, 429, 500, 502, 503, 504}

    def _parse_standard_response(self, result: Dict) -> Dict:
        if "/messages" in self.api_url:
            if "content" in result and result["content"]:
                return {"answer": result["content"][0].get("text", "")}
            if "error" in result:
                return {"error": str(result["error"]), "answer": ""}
            return {"error": "Unknown Claude response format", "answer": ""}
        if "choices" in result and result["choices"]:
            return {"answer": result["choices"][0].get("message", {}).get("content", "")}
        return {"error": "No choices in response", "answer": ""}

    def _extract_stream_text_chunk(self, payload: Dict) -> str:
        if not isinstance(payload, dict):
            return ""

        # OpenAI-compatible chunk format
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            text = item.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                    return "".join(parts)

        # Anthropic-style event chunks
        delta = payload.get("delta")
        if isinstance(delta, dict):
            text = delta.get("text")
            if isinstance(text, str):
                return text
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return delta["text"]
        block = payload.get("content_block")
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            return block["text"]

        return ""

    def _parse_streaming_response(self, response: requests.Response) -> Dict:
        chunks: List[str] = []
        last_payload: Optional[Dict] = None
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if not payload_text or payload_text == "[DONE]":
                break
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            last_payload = payload
            text = self._extract_stream_text_chunk(payload)
            if text:
                chunks.append(text)

        if chunks:
            return {"answer": "".join(chunks)}
        if isinstance(last_payload, dict):
            return self._parse_standard_response(last_payload)
        return {"error": "Empty streaming response", "answer": ""}

    def _request_chat_once(
        self,
        query: str,
        system_prompt: str,
        temperature: float,
        stream: bool,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        response = requests.post(
            self.api_url,
            headers=self._build_headers(),
            json=self._build_payload(query, system_prompt, temperature, stream=stream, response_format=response_format),
            stream=stream,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        response_headers = getattr(response, "headers", {}) or {}
        content_type = (response_headers.get("content-type") or "").lower()
        if stream and "text/event-stream" in content_type:
            parsed = self._parse_streaming_response(response)
        else:
            parsed = self._parse_standard_response(response.json())
        if parsed.get("error"):
            return self._build_error_response("LLM_RESPONSE_INVALID", str(parsed.get("error")), retriable=False)
        return {"ok": True, "answer": parsed.get("answer", ""), "error": None}

    def chat(
        self,
        query: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: float = 0.7,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        max_attempts = max(self.max_retries + 1, 1)
        for attempt in range(max_attempts):
            try:
                return self._request_chat_once(query, system_prompt, temperature, stream=True, response_format=response_format)
            except requests.exceptions.Timeout as exc:
                if attempt < (max_attempts - 1):
                    time.sleep(self._retry_delay(attempt))
                    continue
                return self._build_error_response("LLM_TIMEOUT", str(exc), retriable=False)
            except requests.exceptions.RequestException as exc:
                if getattr(exc, "response", None) is None:
                    try:
                        return self._request_chat_once(query, system_prompt, temperature, stream=False, response_format=response_format)
                    except requests.exceptions.Timeout as fallback_exc:
                        if attempt < (max_attempts - 1):
                            time.sleep(self._retry_delay(attempt))
                            continue
                        return self._build_error_response("LLM_TIMEOUT", str(fallback_exc), retriable=False)
                    except requests.exceptions.RequestException as fallback_exc:
                        exc = fallback_exc
                if self._is_retriable_request_error(exc) and attempt < (max_attempts - 1):
                    time.sleep(self._retry_delay(attempt))
                    continue
                return self._build_error_response("LLM_REQUEST_ERROR", str(exc), retriable=False)
            except Exception as exc:  # pragma: no cover
                return self._build_error_response("LLM_UNKNOWN_ERROR", str(exc), retriable=False)

    def analyze_with_knowledge(
        self,
        abnormal_data: List[Dict],
        enable_cot: bool = True,
        conversation_id: str = "",
        bottleneck_indicators: List[str] = None,
        coupling_analysis: str = None,
        semantic_data: List[Dict] = None,
        features: Dict = None,
        system_state: Dict = None,
        task_note: str = "",
        knowledge_context: Optional[Dict] = None,
        overall_judgement: Optional[Dict] = None,
    ):
        _ = conversation_id
        prompts = build_reasoning_with_knowledge_prompts(
            overall_judgement=overall_judgement or {},
            knowledge_context=knowledge_context or {},
            system_state=system_state or {},
            semantic_data=semantic_data or [],
            features=features or {},
            abnormal_data=abnormal_data or [],
            bottleneck_indicators=bottleneck_indicators or [],
            coupling_analysis=coupling_analysis or "",
            task_note=task_note or "",
        )
        result = self.chat(
            prompts["user_prompt"],
            system_prompt=prompts["system_prompt"],
            temperature=0.2 if enable_cot else 0.0,
        )
        if not result.get("ok", True):
            return result
        return result.get("answer", "{}")

class DifyAPIClient:
    def __init__(self, api_url: str = None, api_key: str = None, user: str = "abc-123", timeout_sec: Optional[int] = None):
        self.api_url = api_url or os.getenv("DIFY_API_URL", "http://localhost/v1/chat-messages")
        self.api_key = api_key or os.getenv("DIFY_API_KEY", "")
        self.user = user
        self.timeout_sec = timeout_sec if timeout_sec is not None else _int_env("LLM_TIMEOUT_SEC", 120)

    def chat(
        self,
        query: str,
        inputs: Optional[Dict] = None,
        response_mode: str = "blocking",
        conversation_id: str = "",
        user: Optional[str] = None,
        files: Optional[List[Dict]] = None,
        timeout: Optional[int] = None,
    ) -> Dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": response_mode,
            "conversation_id": conversation_id,
            "user": user or self.user,
            "files": files or [],
        }
        try:
            mode = str(response_mode or "blocking").strip().lower()
            if mode == "streaming":
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    stream=True,
                    timeout=timeout or self.timeout_sec,
                )
                response.raise_for_status()
                chunks: List[str] = []
                last_event = ""
                seen_terminal = False
                event_trace: List[str] = []
                try:
                    for raw_line in response.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip() if isinstance(raw_line, str) else str(raw_line).strip()
                        if not line:
                            continue
                        if line.startswith("event:"):
                            last_event = line[6:].strip()
                            if last_event:
                                event_trace.append(last_event)
                                event_trace = event_trace[-20:]
                            continue
                        if not line.startswith("data:"):
                            continue
                        payload_text = line[5:].strip()
                        if not payload_text or payload_text == "[DONE]":
                            seen_terminal = True
                            break
                        try:
                            payload = json.loads(payload_text)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        event_name = str(payload.get("event") or last_event or "").strip()
                        if event_name:
                            last_event = event_name
                            event_trace.append(event_name)
                            event_trace = event_trace[-20:]
                        piece = self._extract_stream_answer_piece(payload)
                        if piece:
                            chunks.append(piece)
                        if event_name == "workflow_finished":
                            data_payload = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                            workflow_status = str(data_payload.get("status") or "").strip().lower()
                            workflow_error = str(data_payload.get("error") or "").strip()
                            if workflow_status == "failed" or workflow_error:
                                return {
                                    "ok": False,
                                    "answer": "".join(chunks),
                                    "error": {
                                        "code": "DIFY_WORKFLOW_FAILED",
                                        "message": (workflow_error or "Workflow finished with failed status.")[:500],
                                        "status_code": response.status_code,
                                        "retriable": False,
                                        "event_trace": event_trace,
                                    },
                                }
                            seen_terminal = True
                            break
                        if event_name == "message_end":
                            seen_terminal = True
                            break
                        if event_name == "error":
                            detail = (
                                str(payload.get("message") or "")
                                or str((payload.get("data") or {}).get("error") or "")
                                or payload_text
                            )
                            return {
                                "ok": False,
                                "answer": "",
                                "error": {
                                    "code": "DIFY_STREAM_ERROR",
                                    "message": detail[:500],
                                    "status_code": response.status_code,
                                    "retriable": False,
                                },
                            }
                except requests.exceptions.RequestException as exc:
                    return {
                        "ok": False,
                        "answer": "".join(chunks),
                        "error": {
                            "code": "DIFY_STREAM_INTERRUPTED",
                            "message": f"{str(exc)} | last_event={last_event or 'unknown'}",
                            "status_code": response.status_code,
                            "retriable": True,
                            "event_trace": event_trace,
                        },
                    }

                if chunks:
                    return {"ok": True, "answer": "".join(chunks), "error": None}

                return {
                    "ok": False,
                    "answer": "",
                    "error": {
                        "code": "DIFY_STREAM_INCOMPLETE",
                        "message": f"Streaming response ended without answer chunks. last_event={last_event or 'unknown'}",
                        "status_code": response.status_code,
                        "retriable": not seen_terminal,
                        "event_trace": event_trace,
                    },
                }

            response = requests.post(self.api_url, headers=headers, json=data, timeout=timeout or self.timeout_sec)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                text_preview = (response.text or "").strip()
                if len(text_preview) > 500:
                    text_preview = text_preview[:500]
                return {
                    "ok": False,
                    "answer": "",
                    "error": {
                        "code": "DIFY_RESPONSE_INVALID",
                        "message": f"Dify returned non-JSON response: {text_preview}",
                        "status_code": response.status_code,
                        "retriable": False,
                    },
                }
            payload["ok"] = True
            payload["error"] = None
            payload.setdefault("answer", payload.get("answer", ""))
            return payload
        except requests.exceptions.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            detail = ""
            response_obj = getattr(exc, "response", None)
            if response_obj is not None:
                try:
                    detail_payload = response_obj.json()
                    if isinstance(detail_payload, dict):
                        detail = (
                            str(detail_payload.get("message") or detail_payload.get("error") or detail_payload.get("detail") or "")
                            or json.dumps(detail_payload, ensure_ascii=False)
                        )
                    else:
                        detail = str(detail_payload)
                except Exception:
                    detail = (response_obj.text or "").strip()
            detail = detail[:500] if detail else ""
            message = f"{str(exc)} | status_code={status_code}"
            if detail:
                message = f"{message} | response={detail}"
            retriable = status_code in {408, 409, 429, 500, 502, 503, 504}
            return {
                "ok": False,
                "answer": "",
                "error": {
                    "code": "DIFY_REQUEST_ERROR",
                    "message": message,
                    "status_code": status_code,
                    "retriable": retriable,
                },
            }
        except requests.exceptions.Timeout as exc:
            return {
                "ok": False,
                "answer": "",
                "error": {
                    "code": "DIFY_REQUEST_ERROR",
                    "message": str(exc),
                    "status_code": None,
                    "retriable": True,
                },
            }
        except requests.exceptions.RequestException as exc:
            return {
                "ok": False,
                "answer": "",
                "error": {
                    "code": "DIFY_REQUEST_ERROR",
                    "message": str(exc),
                    "status_code": None,
                    "retriable": True,
                },
            }

    @staticmethod
    def _extract_stream_answer_piece(payload: Dict) -> str:
        if not isinstance(payload, dict):
            return ""
        if isinstance(payload.get("answer"), str):
            return payload["answer"]
        data = payload.get("data")
        if isinstance(data, dict):
            if isinstance(data.get("answer"), str):
                return data["answer"]
            if isinstance(data.get("text"), str):
                return data["text"]
            outputs = data.get("outputs")
            if isinstance(outputs, dict):
                for key in ("answer", "text", "result"):
                    value = outputs.get(key)
                    if isinstance(value, str):
                        return value
        return ""

    def chat_stream(
        self,
        query: str,
        inputs: Optional[Dict] = None,
        conversation_id: str = "",
        user: Optional[str] = None,
        files: Optional[List[Dict]] = None,
    ) -> Generator[str, None, None]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": user or self.user,
            "files": files or [],
        }
        try:
            response = requests.post(self.api_url, headers=headers, json=data, stream=True, timeout=self.timeout_sec)
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8", errors="ignore")
                if not decoded.startswith("data: "):
                    continue
                payload = decoded[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if "answer" in chunk:
                    yield chunk["answer"]
        except requests.exceptions.RequestException as exc:
            yield f"error: {exc}"

    def analyze_with_knowledge(
        self,
        abnormal_data: List[Dict],
        enable_cot: bool = True,
        conversation_id: str = "",
        bottleneck_indicators: List[str] = None,
        coupling_analysis: str = None,
        semantic_data: List[Dict] = None,
        features: Dict = None,
        system_state: Dict = None,
        task_note: str = "",
        knowledge_context: Optional[Dict] = None,
        overall_judgement: Optional[Dict] = None,
    ):
        _ = enable_cot
        prompts = build_reasoning_with_knowledge_prompts(
            overall_judgement=overall_judgement or {},
            knowledge_context=knowledge_context or {},
            system_state=system_state or {},
            semantic_data=semantic_data or [],
            features=features or {},
            abnormal_data=abnormal_data or [],
            bottleneck_indicators=bottleneck_indicators or [],
            coupling_analysis=coupling_analysis or "",
            task_note=task_note or "",
        )
        query = f"{prompts['system_prompt']}\n\n{prompts['user_prompt']}"
        response = self.chat(
            query=query,
            inputs={"stage": "reasoning", "output_format": "json"},
            response_mode="blocking",
            conversation_id=conversation_id,
        )
        if response.get("ok", True) and "answer" in response:
            return response["answer"]
        if response.get("error"):
            return response
        return {
            "ok": False,
            "answer": "",
            "error": {
                "code": "DIFY_EMPTY_RESPONSE",
                "message": "Dify returned no answer.",
                "retriable": False,
            },
        }

