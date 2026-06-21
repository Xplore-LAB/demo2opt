import json
from pathlib import Path

import scripts.run_business_report_audit as audit_script


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pick_matching_timing_json_prefers_report_md_reference(monkeypatch, tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(audit_script, "PROJECT_ROOT", tmp_path)

    report = reports_dir / "analysis_report_20260309_210650.md"
    report.write_text("# demo\n", encoding="utf-8")

    timing_old = reports_dir / "sample_flow_timing_20260309_210651.json"
    timing_new = reports_dir / "sample_flow_timing_20260309_210652.json"
    _write_json(timing_old, {"report_md": "reports/analysis_report_20260309_174909.md"})
    _write_json(timing_new, {"report_md": f"reports/{report.name}"})

    matched = audit_script.pick_matching_timing_json(report)
    assert matched == timing_new.resolve()


def test_pick_matching_timing_json_returns_none_when_no_match(monkeypatch, tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(audit_script, "PROJECT_ROOT", tmp_path)

    report = reports_dir / "analysis_report_20260309_210650.md"
    report.write_text("# demo\n", encoding="utf-8")

    timing = reports_dir / "sample_flow_timing_20260309_220000.json"
    _write_json(timing, {"report_md": "reports/analysis_report_20260309_220000.md"})

    assert audit_script.pick_matching_timing_json(report) is None
