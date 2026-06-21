import json
import re
from typing import Any, Dict, Optional


_MOJIBAKE_SEGMENT_RE = re.compile(r"[脙脜脝脟脠脡脢脣脤脥脦脧脨脩脪脫脭脮脰脴脵脷脹脺脻脼脽脿谩芒茫盲氓忙莽猫茅锚毛矛铆卯茂冒帽貌贸么玫枚酶霉煤没眉媒镁每]{4,}")
_HEX_ESCAPE_RE = re.compile(r"(?:\\x[0-9A-Fa-f]{2}|[ -~\x80-\xff]){8,}")


def _noise_score(text: str) -> int:
    return len(re.findall(r"\\x[0-9A-Fa-f]{2}", text)) + len(_MOJIBAKE_SEGMENT_RE.findall(text))


def _cjk_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def _decode_whole_latin1_if_better(text: str) -> str:
    try:
        repaired = text.encode("latin1", errors="strict").decode("utf-8", errors="strict")
    except Exception:
        return text
    if repaired == text:
        return text
    if _cjk_count(repaired) > _cjk_count(text):
        return repaired
    return repaired if _noise_score(repaired) < _noise_score(text) else text


def _decode_hex_escape_segments(text: str) -> str:
    if "\\x" not in text:
        return text

    def repl(match: re.Match[str]) -> str:
        segment = match.group(0)
        raw = bytearray()
        index = 0
        while index < len(segment):
            if (
                index + 3 < len(segment)
                and segment[index] == "\\"
                and segment[index + 1] == "x"
                and all(c in "0123456789abcdefABCDEF" for c in segment[index + 2 : index + 4])
            ):
                raw.append(int(segment[index + 2 : index + 4], 16))
                index += 4
                continue
            char = segment[index]
            if ord(char) > 255:
                return segment
            raw.append(ord(char))
            index += 1
        for encoding in ("utf-8", "gb18030", "gbk"):
            try:
                return raw.decode(encoding)
            except Exception:
                continue
        return segment

    return _HEX_ESCAPE_RE.sub(repl, text)


def _decode_latin1_segments(text: str) -> str:
    return _MOJIBAKE_SEGMENT_RE.sub(lambda match: _decode_whole_latin1_if_better(match.group(0)), text)


def _next_non_whitespace_char(text: str, start: int) -> str:
    index = start
    while index < len(text):
        if not text[index].isspace():
            return text[index]
        index += 1
    return ""


def _sanitize_json_like_text(text: str) -> str:
    """Best-effort repair for JSON-like text with unescaped quotes/control chars inside strings."""
    if not text:
        return text

    output = []
    in_string = False
    escaped = False

    for index, ch in enumerate(text):
        if in_string:
            if escaped:
                output.append(ch)
                escaped = False
                continue
            if ch == "\\":
                output.append(ch)
                escaped = True
                continue
            if ch == '"':
                next_char = _next_non_whitespace_char(text, index + 1)
                if next_char in {",", "}", "]", ":"} or next_char == "":
                    in_string = False
                    output.append(ch)
                else:
                    output.append('\\"')
                continue
            if ch == "\n":
                output.append("\\n")
                continue
            if ch == "\r":
                output.append("\\r")
                continue
            if ch == "\t":
                output.append("\\t")
                continue
            if ord(ch) < 0x20:
                output.append(f"\\u{ord(ch):04x}")
                continue
            output.append(ch)
            continue

        if ch == '"':
            in_string = True
        output.append(ch)

    return "".join(output)


def repair_llm_text(value: Any) -> Any:
    """Best-effort repair for mojibake-like text returned by model APIs."""
    if not isinstance(value, str):
        return value
    repaired = _decode_whole_latin1_if_better(value)
    repaired = _decode_hex_escape_segments(repaired)
    repaired = _decode_whole_latin1_if_better(repaired)
    repaired = _decode_latin1_segments(repaired)
    return repaired


def extract_json_object(payload: Any) -> Optional[Dict[str, Any]]:
    """Best-effort parse for JSON object from model outputs."""
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        return None

    text = payload.strip()
    if not text:
        return None

    candidates = [text]

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.append(brace.group().strip())

    for candidate in candidates:
        candidate = str(repair_llm_text(candidate)).strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            sanitized = _sanitize_json_like_text(candidate)
            try:
                parsed = json.loads(sanitized)
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
    return None
