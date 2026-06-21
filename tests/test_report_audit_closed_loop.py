import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.utils.report_audit import BusinessReportAuditor, BusinessReportAutoFixer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "reports"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    src = FIXTURE_DIR / fixture_name
    dst = tmp_path / fixture_name
    shutil.copy2(src, dst)
    return dst


def test_auditor_passes_clean_fixture(tmp_path: Path):
    report = _copy_fixture(tmp_path, "sample_report_ok.md")
    timing = _copy_fixture(tmp_path, "sample_timing_ok.json")

    raw = json.loads(timing.read_text(encoding="utf-8"))
    raw["report_md"] = str(report)
    timing.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    result = BusinessReportAuditor().audit(report_md_path=report, timing_json_path=timing)
    assert result["audit_status"] == "passed"
    assert result["summary"]["finding_count"] == 0


def test_mojibake_report_can_be_fixed_and_pass(tmp_path: Path):
    report = _copy_fixture(tmp_path, "sample_report_bad_mojibake.md")
    timing = _copy_fixture(tmp_path, "sample_timing_needs_patch.json")

    raw = json.loads(timing.read_text(encoding="utf-8"))
    raw["report_md"] = str(report)
    timing.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    auditor = BusinessReportAuditor()
    fixer = BusinessReportAutoFixer()

    before = auditor.audit(report_md_path=report, timing_json_path=timing)
    assert before["audit_status"] in {"needs_review", "failed"}
    assert any(item["code"] == "TEXT_MOJIBAKE_SUSPECTED" for item in before["findings"])

    actions = fixer.auto_fix(report_md_path=report, timing_json_path=timing, audit_result=before)
    assert actions

    after = auditor.audit(report_md_path=report, timing_json_path=timing)
    assert after["audit_status"] == "passed"

    patched_timing = json.loads(timing.read_text(encoding="utf-8"))
    assert patched_timing["abnormal_count"] == 3
    assert patched_timing["step_duration_sum_ms"] == 800


def test_audit_script_exit_code_and_outputs():
    report = FIXTURE_DIR / "sample_report_ok.md"
    timing = FIXTURE_DIR / "sample_timing_ok.json"
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_business_report_audit.py"),
        "--report-md",
        str(report),
        "--timing-json",
        str(timing),
        "--max-rounds",
        "1",
        "--no-auto-fix",
    ]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True)
    stdout = (completed.stdout or b"").decode("utf-8", errors="ignore")
    stderr = (completed.stderr or b"").decode("utf-8", errors="ignore")
    assert completed.returncode == 0, stdout + "\n" + stderr
    assert "audit_status: passed" in stdout
