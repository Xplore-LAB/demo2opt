"""Run report audit without modifying the original report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.report_audit import BusinessReportAuditor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit business report quality and consistency.")
    parser.add_argument("--report-md", default="", help="Target report markdown path. Defaults to latest analysis_report_*.md")
    parser.add_argument("--timing-json", default="", help="Timing json path. Defaults to latest sample_flow_timing_*.json")
    parser.add_argument("--max-rounds", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--no-auto-fix", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def pick_latest(pattern: str) -> Optional[Path]:
    candidates = sorted((PROJECT_ROOT / "reports").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _extract_report_timestamp(report_md: Path) -> Optional[str]:
    match = re.search(r"analysis_report_(\d{8}_\d{6})", report_md.stem)
    return match.group(1) if match else None


def pick_matching_timing_json(report_md: Optional[Path]) -> Optional[Path]:
    if not report_md:
        return None
    reports_dir = PROJECT_ROOT / "reports"
    if not reports_dir.exists():
        return None

    target_name = report_md.name
    candidates = sorted(reports_dir.glob("sample_flow_timing_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        ref_name = Path(str(payload.get("report_md", "")).replace("\\", "/")).name
        if ref_name == target_name:
            return candidate.resolve()

    ts = _extract_report_timestamp(report_md)
    if ts:
        by_name = reports_dir / f"sample_flow_timing_{ts}.json"
        if by_name.exists():
            return by_name.resolve()
    return None


def resolve_input_path(raw: str, default_path: Optional[Path]) -> Optional[Path]:
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    return default_path.resolve() if default_path else None


def write_audit_outputs(result: Dict[str, Any]) -> Dict[str, Path]:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"business_report_audit_{ts}.json"
    md_path = reports_dir / f"business_report_audit_{ts}.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Business Report Audit Result\n\n")
    lines.append(f"- audit_time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"- audit_status: {result.get('audit_status')}\n")
    summary = result.get("summary") or {}
    lines.append(f"- critical_count: {summary.get('critical_count', 0)}\n")
    lines.append(f"- warning_count: {summary.get('warning_count', 0)}\n")
    lines.append(f"- finding_count: {summary.get('finding_count', 0)}\n")

    inputs = result.get("inputs") or {}
    lines.append("\n## Inputs\n\n")
    lines.append(f"- report_md: {inputs.get('report_md_path', '')}\n")
    lines.append(f"- timing_json: {inputs.get('timing_json_path', '')}\n")

    closed_loop = result.get("closed_loop") or {}
    lines.append("\n## Closed Loop\n\n")
    lines.append(f"- auto_fix_enabled: {closed_loop.get('auto_fix_enabled', False)}\n")
    lines.append(f"- final_round: {closed_loop.get('final_round', 0)}\n")
    for item in closed_loop.get("rounds") or []:
        lines.append(
            f"- round={item.get('round')} status={item.get('audit_status')} "
            f"summary={item.get('summary')} actions={item.get('actions')}\n"
        )

    lines.append("\n## Findings\n\n")
    findings = result.get("findings") or []
    if not findings:
        lines.append("- none\n")
    else:
        for idx, item in enumerate(findings, start=1):
            lines.append(f"{idx}. [{item.get('severity')}] {item.get('code')} - {item.get('message')}\n")
            details = str(item.get("details") or "").strip()
            if details:
                lines.append(f"   - details: {details}\n")

    lines.append("\n## Step Duration Comparison\n\n")
    step_durations = result.get("step_durations") or {}
    md_steps = step_durations.get("markdown") or {}
    timing_steps = step_durations.get("timing_json") or {}
    all_steps = sorted({int(k) for k in list(md_steps.keys()) + list(timing_steps.keys())})
    if all_steps:
        lines.append("| Step | report_md(ms) | timing_json(ms) |\n")
        lines.append("|---:|---:|---:|\n")
        for step in all_steps:
            md_val = md_steps.get(step, md_steps.get(str(step), "-"))
            tj_val = timing_steps.get(step, timing_steps.get(str(step), "-"))
            lines.append(f"| {step} | {md_val} | {tj_val} |\n")
    else:
        lines.append("- no step durations found.\n")

    md_path.write_text("".join(lines), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def main() -> int:
    args = parse_args()
    default_report = pick_latest("analysis_report_*.md")
    report_md = resolve_input_path(args.report_md, default_report)
    default_timing = pick_latest("sample_flow_timing_*.json") if args.timing_json else pick_matching_timing_json(report_md)
    timing_json = resolve_input_path(args.timing_json, default_timing)

    if not report_md:
        raise FileNotFoundError("No report markdown found. Provide --report-md.")

    auditor = BusinessReportAuditor()
    result = auditor.audit(report_md_path=report_md, timing_json_path=timing_json)
    rounds: list[dict[str, Any]] = [
        {
            "round": 1,
            "audit_status": result.get("audit_status"),
            "summary": result.get("summary"),
            "actions": [],
        }
    ]

    result["closed_loop"] = {
        "auto_fix_enabled": False,
        "rounds": rounds,
        "final_round": len(rounds),
    }
    output_paths = write_audit_outputs(result)

    print("Business report audit completed.")
    print(f"audit_status: {result.get('audit_status')}")
    print(f"finding_count: {(result.get('summary') or {}).get('finding_count', 0)}")
    print(f"rounds: {len(rounds)}")
    print("auto_fix: disabled")
    print(f"audit_json: {output_paths['json']}")
    print(f"audit_md: {output_paths['md']}")
    return 0 if result.get("audit_status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
