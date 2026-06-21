"""LLM 响应解析器"""
from typing import Any, Dict

from src.utils.llm_json import extract_json_object


class ResponseParser:
    """LLM 响应解析器"""

    def parse(self, raw: Any) -> Dict[str, Any]:
        """解析 LLM 响应为标准格式"""
        if isinstance(raw, dict):
            if "answer" in raw and isinstance(raw["answer"], str):
                return self.parse(raw["answer"])
            return raw
        if not isinstance(raw, str):
            raise ValueError("LLM_RESPONSE_TYPE_ERROR: response is not a string/dict.")

        text = raw.strip()
        parsed = self._try_parse_json_text(text)
        if parsed is not None:
            return parsed

        preview = text.replace("\n", " ")[:240]
        raise ValueError(f"LLM_NON_JSON_RESPONSE: model returned non-JSON content. preview={preview}")

    def _try_parse_json_text(self, text: str) -> Dict[str, Any] | None:
        """尝试从文本中提取 JSON"""
        return extract_json_object(text)
