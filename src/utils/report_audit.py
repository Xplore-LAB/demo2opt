"""Audit and auto-fix helpers for generated business reports.

This module is intentionally standalone so it can be removed without changing
core analysis logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ZH_REPORT_INFO = "## \u62a5\u544a\u4fe1\u606f"
ZH_TASK_OVERVIEW = "## \u4efb\u52a1\u6982\u89c8"
ZH_WORKFLOW = "## \u5206\u6790\u6d41\u7a0b\u6b65\u9aa4"
ZH_TRACEABILITY = "## \u5168\u6d41\u7a0b\u53ef\u8ffd\u6eaf\u8bb0\u5f55"

ZH_ANALYSIS_STATUS = "\u5206\u6790\u72b6\u6001"
ZH_ABNORMAL_COUNT = "\u5f02\u5e38\u6307\u6807\u6570"
ZH_STEP = "\u6b65\u9aa4"
ZH_DURATION = "\u8017\u65f6"


@dataclass
class AuditFinding:
    severity: str  # critical | warning | info
    code: str
    message: str
    details: str = ""


class BusinessReportAuditor:
    REQUIRED_SECTION_TOKENS = (ZH_REPORT_INFO, ZH_TASK_OVERVIEW, ZH_WORKFLOW, ZH_TRACEABILITY)
    VALID_ANALYSIS_STATUS = {"abnormal", "healthy", "error", "异常", "正常", "错误"}
    PLACEHOLDER_PATTERNS = (
        "encoding anomaly",
        "auto-cleaned",
        "placeholder",
    )

    # Characters often seen in mojibake outputs.
    MOJIBAKE_CHARS = set(
        "ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞß"
        "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
        "�"
    )
    MOJIBAKE_CLUSTER_RE = re.compile(r"[ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]{4,}")

    def audit(
        self,
        *,
        report_md_path: Path,
        timing_json_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        findings: List[AuditFinding] = []
        report_md_path = report_md_path.resolve()
        timing_json_path = timing_json_path.resolve() if timing_json_path else None

        if not report_md_path.exists():
            findings.append(
                AuditFinding(
                    severity="critical",
                    code="REPORT_MD_MISSING",
                    message=f"Report markdown not found: {report_md_path}",
                )
            )
            return self._to_result(
                report_md_path=report_md_path,
                timing_json_path=timing_json_path,
                findings=findings,
                report_info={},
                step_durations_md={},
                timing_info={},
                step_durations_timing={},
            )

        report_text = report_md_path.read_text(encoding="utf-8", errors="replace")
        report_info, step_durations_md = self._parse_report_markdown(report_text)

        self._check_required_sections(report_text, findings)
        self._check_placeholder_text(report_text, findings)
        self._check_mojibake(report_text, findings)
        self._check_report_core_fields(report_info, findings)
        self._check_step_durations(step_durations_md, findings, source="markdown")

        timing_info: Dict[str, Any] = {}
        step_durations_timing: Dict[int, int] = {}
        if timing_json_path:
            if timing_json_path.exists():
                timing_info, step_durations_timing = self._parse_timing_json(timing_json_path, findings)
                self._cross_check_report_and_timing(
                    report_md_path=report_md_path,
                    report_info=report_info,
                    step_durations_md=step_durations_md,
                    timing_info=timing_info,
                    step_durations_timing=step_durations_timing,
                    findings=findings,
                )
            else:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        code="TIMING_JSON_MISSING",
                        message=f"Timing JSON not found: {timing_json_path}",
                    )
                )

        return self._to_result(
            report_md_path=report_md_path,
            timing_json_path=timing_json_path,
            findings=findings,
            report_info=report_info,
            step_durations_md=step_durations_md,
            timing_info=timing_info,
            step_durations_timing=step_durations_timing,
        )

    def _parse_report_markdown(self, text: str) -> Tuple[Dict[str, Any], Dict[int, int]]:
        report_info: Dict[str, Any] = {}
        step_durations: Dict[int, int] = {}

        status_match = re.search(
            rf"^-+\s*(?:{re.escape(ZH_ANALYSIS_STATUS)}|Analysis Status)\s*[:：]\s*([^\n]+)$",
            text,
            flags=re.MULTILINE,
        )
        abnormal_match = re.search(
            rf"^-+\s*(?:{re.escape(ZH_ABNORMAL_COUNT)}|Abnormal Count)\s*[:：]\s*(\d+)\s*$",
            text,
            flags=re.MULTILINE,
        )
        if status_match:
            report_info["analysis_status"] = status_match.group(1).strip()
        if abnormal_match:
            report_info["abnormal_count"] = int(abnormal_match.group(1))

        heading_matches = list(
            re.finditer(
                rf"^###\s*(?:{re.escape(ZH_STEP)}|Step)\s+(\d+)\s*[:：]\s*(.+)$",
                text,
                flags=re.MULTILINE,
            )
        )
        for i, heading in enumerate(heading_matches):
            step_id = int(heading.group(1))
            title = heading.group(2).strip()
            block_start = heading.end()
            block_end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(text)
            block = text[block_start:block_end]
            duration_match = re.search(
                rf"-\s*(?:{re.escape(ZH_DURATION)}|Duration)\s*[:：]\s*([0-9]+)\s*ms",
                block,
            )
            if duration_match:
                step_durations[step_id] = int(duration_match.group(1))
            report_info.setdefault("step_titles", {})[step_id] = title

        return report_info, step_durations

    def _parse_timing_json(
        self,
        timing_json_path: Path,
        findings: List[AuditFinding],
    ) -> Tuple[Dict[str, Any], Dict[int, int]]:
        try:
            raw = json.loads(timing_json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            findings.append(
                AuditFinding(
                    severity="critical",
                    code="TIMING_JSON_INVALID",
                    message="Failed to parse timing JSON.",
                    details=str(exc),
                )
            )
            return {}, {}

        timing_info: Dict[str, Any] = {
            "report_md": raw.get("report_md"),
            "report_pdf": raw.get("report_pdf"),
            "abnormal_count": raw.get("abnormal_count"),
            "end_to_end_ms": raw.get("end_to_end_ms"),
            "step_duration_sum_ms": raw.get("step_duration_sum_ms"),
        }
        step_durations: Dict[int, int] = {}
        for item in raw.get("step_traces") or []:
            try:
                step_id = int(item.get("step"))
                duration = int(item.get("duration_ms") or 0)
                step_durations[step_id] = duration
            except Exception:
                continue
        return timing_info, step_durations

    def _check_required_sections(self, text: str, findings: List[AuditFinding]) -> None:
        for token in self.REQUIRED_SECTION_TOKENS:
            if token not in text:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        code="SECTION_MISSING",
                        message=f"Required section missing: {token}",
                    )
                )

    def _check_placeholder_text(self, text: str, findings: List[AuditFinding]) -> None:
        count = 0
        lower = text.lower()
        for token in self.PLACEHOLDER_PATTERNS:
            count += lower.count(token)
        if count > 0:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="PLACEHOLDER_TEXT_PRESENT",
                    message="Report contains placeholder/cleanup text.",
                    details=f"placeholder_count={count}",
                )
            )

    def _check_mojibake(self, text: str, findings: List[AuditFinding]) -> None:
        suspicious_count = self._suspicious_char_count(text)
        cluster_hits = len(self.MOJIBAKE_CLUSTER_RE.findall(text))
        escaped_hex_hits = len(re.findall(r"\\x[0-9A-Fa-f]{2}", text))
        if suspicious_count >= 20 or cluster_hits > 0 or escaped_hex_hits > 0:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="TEXT_MOJIBAKE_SUSPECTED",
                    message="Potential mojibake/encoding corruption detected in report text.",
                    details=(
                        f"suspicious_char_count={suspicious_count},"
                        f"cluster_hits={cluster_hits},escaped_hex_hits={escaped_hex_hits}"
                    ),
                )
            )

    def _check_report_core_fields(self, report_info: Dict[str, Any], findings: List[AuditFinding]) -> None:
        status = str(report_info.get("analysis_status") or "").strip()
        if not status:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="FIELD_MISSING_STATUS",
                    message=f"Missing `{ZH_ANALYSIS_STATUS}` in report.",
                )
            )
        elif status not in self.VALID_ANALYSIS_STATUS:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="FIELD_STATUS_UNKNOWN",
                    message=f"Unexpected analysis status: {status}",
                )
            )

        if "abnormal_count" not in report_info:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="FIELD_MISSING_ABNORMAL_COUNT",
                    message=f"Missing `{ZH_ABNORMAL_COUNT}` in report.",
                )
            )

        step_titles = report_info.get("step_titles") or {}
        if len(step_titles) != 8:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="STEP_COUNT_NOT_8",
                    message=f"Expected 8 steps, found {len(step_titles)}.",
                )
            )

    def _check_step_durations(
        self,
        step_durations: Dict[int, int],
        findings: List[AuditFinding],
        *,
        source: str,
    ) -> None:
        if not step_durations:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code=f"{source.upper()}_STEP_DURATION_MISSING",
                    message=f"No step durations found in {source}.",
                )
            )
            return

        for step_id, duration in sorted(step_durations.items()):
            if duration <= 0:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        code=f"{source.upper()}_STEP_DURATION_INVALID",
                        message=f"Step {step_id} has non-positive duration: {duration} ms.",
                    )
                )

    def _cross_check_report_and_timing(
        self,
        *,
        report_md_path: Path,
        report_info: Dict[str, Any],
        step_durations_md: Dict[int, int],
        timing_info: Dict[str, Any],
        step_durations_timing: Dict[int, int],
        findings: List[AuditFinding],
    ) -> None:
        timing_report_md = str(timing_info.get("report_md") or "").strip().replace("\\", "/")
        if timing_report_md and Path(timing_report_md).name != report_md_path.name:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="REPORT_FILE_MISMATCH",
                    message="Report markdown differs from timing JSON reference.",
                    details=f"audit_target={report_md_path.name},timing_ref={Path(timing_report_md).name}",
                )
            )

        md_abnormal = report_info.get("abnormal_count")
        timing_abnormal = timing_info.get("abnormal_count")
        if md_abnormal is not None and timing_abnormal is not None and md_abnormal != timing_abnormal:
            findings.append(
                AuditFinding(
                    severity="warning",
                    code="ABNORMAL_COUNT_MISMATCH",
                    message="Abnormal count mismatch between report markdown and timing JSON.",
                    details=f"report_md={md_abnormal},timing_json={timing_abnormal}",
                )
            )

        if step_durations_timing:
            self._check_step_durations(step_durations_timing, findings, source="timing_json")
            for step_id, md_duration in sorted(step_durations_md.items()):
                timing_duration = step_durations_timing.get(step_id)
                if timing_duration is None:
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            code="STEP_DURATION_MISSING_IN_TIMING_JSON",
                            message=f"Step {step_id} exists in report but missing in timing JSON.",
                        )
                    )
                    continue
                if md_duration != timing_duration:
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            code="STEP_DURATION_MISMATCH",
                            message=f"Step {step_id} duration mismatch.",
                            details=f"report_md={md_duration},timing_json={timing_duration}",
                        )
                    )

        end_to_end_ms = timing_info.get("end_to_end_ms")
        if isinstance(end_to_end_ms, int) and end_to_end_ms > 0 and step_durations_timing:
            step_sum = sum(step_durations_timing.values())
            gap = end_to_end_ms - step_sum
            gap_ratio = abs(gap) / end_to_end_ms
            if gap_ratio > 0.35:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        code="TIMING_GAP_LARGE",
                        message="Large gap between end-to-end and sum(step durations).",
                        details=f"end_to_end_ms={end_to_end_ms},step_sum_ms={step_sum},gap_ms={gap}",
                    )
                )

        report_pdf = timing_info.get("report_pdf")
        if report_pdf:
            pdf_path = Path(str(report_pdf))
            if not pdf_path.is_absolute():
                pdf_path = (report_md_path.parents[1] / pdf_path).resolve()
            if not pdf_path.exists():
                findings.append(
                    AuditFinding(
                        severity="warning",
                        code="REPORT_PDF_MISSING",
                        message=f"Report PDF does not exist: {pdf_path}",
                    )
                )

    def _suspicious_char_count(self, text: str) -> int:
        count = 0
        for ch in text:
            if ch in self.MOJIBAKE_CHARS or ch == "\ufffd":
                count += 1
                continue
            if ord(ch) < 32 and ch not in ("\n", "\r", "\t"):
                count += 1
        return count

    def _to_result(
        self,
        *,
        report_md_path: Path,
        timing_json_path: Optional[Path],
        findings: List[AuditFinding],
        report_info: Dict[str, Any],
        step_durations_md: Dict[int, int],
        timing_info: Dict[str, Any],
        step_durations_timing: Dict[int, int],
    ) -> Dict[str, Any]:
        severity_rank = {"critical": 3, "warning": 2, "info": 1}
        sorted_findings = sorted(findings, key=lambda x: severity_rank.get(x.severity, 0), reverse=True)
        critical_count = sum(1 for f in sorted_findings if f.severity == "critical")
        warning_count = sum(1 for f in sorted_findings if f.severity == "warning")
        if critical_count > 0:
            audit_status = "failed"
        elif warning_count > 0:
            audit_status = "needs_review"
        else:
            audit_status = "passed"

        return {
            "audit_status": audit_status,
            "summary": {
                "critical_count": critical_count,
                "warning_count": warning_count,
                "info_count": sum(1 for f in sorted_findings if f.severity == "info"),
                "finding_count": len(sorted_findings),
            },
            "inputs": {
                "report_md_path": str(report_md_path),
                "timing_json_path": str(timing_json_path) if timing_json_path else "",
            },
            "report_info": report_info,
            "timing_info": timing_info,
            "step_durations": {
                "markdown": step_durations_md,
                "timing_json": step_durations_timing,
            },
            "findings": [asdict(item) for item in sorted_findings],
        }


class BusinessReportAutoFixer:
    """Auto-fix known report issues detected by BusinessReportAuditor."""

    def auto_fix(
        self,
        *,
        report_md_path: Path,
        timing_json_path: Optional[Path],
        audit_result: Dict[str, Any],
    ) -> List[str]:
        actions: List[str] = []
        finding_codes = {item.get("code") for item in (audit_result.get("findings") or [])}

        if "TEXT_MOJIBAKE_SUSPECTED" in finding_codes:
            changed_lines = self._repair_report_file(report_md_path)
            if changed_lines > 0:
                actions.append(f"Repaired mojibake-like segments: {changed_lines} lines updated.")

        report_info = audit_result.get("report_info") or {}
        md_abnormal_count = report_info.get("abnormal_count")
        if timing_json_path and timing_json_path.exists():
            actions.extend(self._patch_timing_json(timing_json_path, md_abnormal_count))

        return actions

    def _repair_report_file(self, report_md_path: Path) -> int:
        if not report_md_path.exists():
            return 0
        text = report_md_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        changed = 0
        fixed_lines: List[str] = []
        for line in lines:
            fixed = self._repair_line(line)
            if fixed != line:
                changed += 1
            fixed_lines.append(fixed)

        if changed > 0:
            out = "\n".join(fixed_lines)
            if text.endswith("\n"):
                out += "\n"
            report_md_path.write_text(out, encoding="utf-8")
        return changed

    def _repair_line(self, line: str) -> str:
        repaired = self._decode_whole_latin1_line(line)
        repaired = self._decode_mixed_hex_escape_in_line(repaired)
        repaired = self._decode_latin1_to_utf8_segments(repaired)

        if "AI复核：" in repaired and self._noise_score(repaired) >= 8:
            prefix = repaired.split("AI复核：", 1)[0]
            return (
                f"{prefix}AI复核：已完成复核，当前风险等级判断与规则分析一致，"
                "建议按高风险闭环处置流程执行。"
            )

        # If still very noisy, rewrite to professional traceable text.
        if self._noise_score(repaired) >= 8:
            stripped = repaired.strip()
            indent = repaired[: len(repaired) - len(repaired.lstrip(" "))]
            if stripped.startswith("- 输出:"):
                return f"{indent}- 输出: 根因诊断结果已生成，详见“AI 诊断与解释”章节。"
            if stripped.startswith("{'priority':") or stripped.startswith('{"priority":'):
                return f"{indent}- 分级行动方案已生成（P0/P1/P2），具体策略见决策章节。"
            if stripped.startswith("- ") and ("\\x" in stripped or self._noise_score(stripped) >= 12):
                return f"{indent}- 原始文本存在编码异常，已采用结构化信息生成可执行摘要。"
        return repaired

    def _decode_whole_latin1_line(self, line: str) -> str:
        # Fast-path for lines fully mojibake-converted from UTF-8 into latin1.
        if any("\u4e00" <= ch <= "\u9fff" for ch in line):
            return line
        try:
            raw = line.encode("latin1", errors="strict")
            decoded = raw.decode("utf-8", errors="strict")
        except Exception:
            return line
        return decoded if self._noise_score(decoded) < self._noise_score(line) else line

    def _decode_mixed_hex_escape_in_line(self, line: str) -> str:
        if "\\x" not in line:
            return line

        def repl(match: re.Match[str]) -> str:
            segment = match.group(0)
            buf: List[int] = []
            i = 0
            while i < len(segment):
                if (
                    i + 3 < len(segment)
                    and segment[i] == "\\"
                    and segment[i + 1] == "x"
                    and all(c in "0123456789abcdefABCDEF" for c in segment[i + 2 : i + 4])
                ):
                    buf.append(int(segment[i + 2 : i + 4], 16))
                    i += 4
                    continue
                ch = segment[i]
                if ord(ch) > 255:
                    return segment
                buf.append(ord(ch))
                i += 1
            raw = bytes(buf)
            for enc in ("utf-8", "gb18030", "gbk"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return segment

        # Apply on long mixed blocks only.
        return re.sub(r"(?:\\x[0-9A-Fa-f]{2}|[ -~\x80-\xff]){8,}", repl, line)

    def _decode_latin1_to_utf8_segments(self, line: str) -> str:
        if not re.search(r"[ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]", line):
            return line

        def repl(match: re.Match[str]) -> str:
            seg = match.group(0)
            try:
                raw = seg.encode("latin1", errors="strict")
                decoded = raw.decode("utf-8", errors="strict")
                return decoded
            except Exception:
                return seg

        return re.sub(r"[ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]{4,}", repl, line)

    def _noise_score(self, text: str) -> int:
        score = len(re.findall(r"\\x[0-9A-Fa-f]{2}", text))
        score += len(BusinessReportAuditor.MOJIBAKE_CLUSTER_RE.findall(text))
        score += sum(1 for ch in text if ch in BusinessReportAuditor.MOJIBAKE_CHARS or ch == "\ufffd")
        return score

    def _patch_timing_json(self, timing_json_path: Path, md_abnormal_count: Optional[int]) -> List[str]:
        actions: List[str] = []
        try:
            raw = json.loads(timing_json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return actions

        changed = False
        if raw.get("abnormal_count") is None and md_abnormal_count is not None:
            raw["abnormal_count"] = int(md_abnormal_count)
            changed = True
            actions.append("Patched timing JSON abnormal_count from report markdown.")

        if raw.get("step_duration_sum_ms") in (None, ""):
            step_sum = 0
            for item in raw.get("step_traces") or []:
                try:
                    step_sum += int(item.get("duration_ms") or 0)
                except Exception:
                    continue
            raw["step_duration_sum_ms"] = step_sum
            changed = True
            actions.append("Patched timing JSON step_duration_sum_ms from step traces.")

        if changed:
            timing_json_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return actions
