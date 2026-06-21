"""Run sample-data workflow with supervisor audit and timing records."""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib
import json
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import websockets


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WS_SERVER_PATH = PROJECT_ROOT / "src" / "api" / "ws" / "server.py"
DEFAULT_WS_PORT = 8001


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sample workflow with timing and supervisor audit.")
    parser.add_argument("--sample-file", default="", help="Sample xlsx path relative to project root.")
    parser.add_argument("--execution-feedback-json", default="", help="Execution feedback json path relative to project root.")
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="WebSocket service port.")
    parser.add_argument("--timeout-sec", type=int, default=900, help="Max wait time for one full run.")
    parser.add_argument("--task-note", default="Automated full-chain sample run with timing trace.", help="Task note.")
    parser.add_argument("--audit-max-rounds", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--no-auto-fix", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--disable-audit", action="store_true", help="Skip report audit stage entirely.")
    parser.add_argument("--max-supervisor-runs", type=int, default=3, help="Max full workflow reruns until accepted.")
    return parser.parse_args()


def parse_dotenv(dotenv_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for raw in dotenv_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def pick_sample_file(sample_file_arg: str) -> Path:
    if sample_file_arg:
        candidate = (PROJECT_ROOT / sample_file_arg).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Sample file does not exist: {candidate}")
        if candidate.suffix.lower() != ".xlsx":
            raise ValueError(f"Sample file must be .xlsx: {candidate}")
        return candidate

    data_dir = PROJECT_ROOT / "data"
    candidates = sorted(
        [p for p in data_dir.glob("*.xlsx") if p.is_file() and not p.name.startswith("~$")],
        key=lambda p: p.name.lower(),
    )
    if not candidates:
        raise FileNotFoundError("No .xlsx sample file found under data/.")
    return candidates[0]


def wait_for_port(port: int, timeout_sec: int = 30) -> bool:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_sec:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def start_ws_server(port: int, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        [sys.executable, str(WS_SERVER_PATH), str(port)],
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process._codex_log_file = log_file  # type: ignore[attr-defined]
    return process


def stop_ws_server(process: Optional[subprocess.Popen]) -> None:
    if not process:
        return
    try:
        process.terminate()
        process.wait(timeout=8)
    except Exception:
        process.kill()
    finally:
        log_file = getattr(process, "_codex_log_file", None)
        if log_file:
            log_file.close()


def relpath_for_payload(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
        return str(rel).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def build_payload(
    *,
    sample_file: Path,
    dotenv_values: Dict[str, str],
    task_note: str,
    execution_feedback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    llm_api_key = dotenv_values.get("LLM_API_KEY", "")
    llm_base_url = dotenv_values.get("LLM_BASE_URL", "")
    llm_model = dotenv_values.get("LLM_MODEL_NAME", "")
    dify_api_key = dotenv_values.get("DIFY_API_KEY", "")
    dify_api_url = dotenv_values.get("DIFY_DATASETS_API_URL") or dotenv_values.get("DIFY_API_URL", "http://localhost/v1")
    dify_dataset_id = dotenv_values.get("DIFY_DATASET_ID", "")

    if not dify_api_key:
        raise ValueError("Missing DIFY_API_KEY in .env; retrieval is a required workflow step.")
    if not llm_api_key or not llm_base_url or not llm_model:
        raise ValueError("Missing direct LLM config in .env (LLM_API_KEY/LLM_BASE_URL/LLM_MODEL_NAME).")

    payload: Dict[str, Any] = {
        "type": "start",
        "enable_cot": True,
        "data_source": "sample",
        "sample_file": relpath_for_payload(sample_file),
        "task_note": task_note,
        "dify_config": {
            "api_url": dify_api_url,
            "api_key": dify_api_key,
            "app_name": "dify-retrieval",
            "api_mode": "datasets_retrieve",
            "dataset_id": dify_dataset_id,
            "keyword": dotenv_values.get("DIFY_DATASETS_KEYWORD", ""),
            "tag_ids": dotenv_values.get("DIFY_DATASETS_TAG_IDS", ""),
            "page": dotenv_values.get("DIFY_DATASETS_PAGE", 1),
            "limit": dotenv_values.get("DIFY_DATASETS_LIMIT", 20),
            "include_all": dotenv_values.get("DIFY_DATASETS_INCLUDE_ALL", False),
            "top_k": dotenv_values.get("DIFY_RETRIEVE_TOP_K", 5),
            "search_method": dotenv_values.get("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search"),
            "reranking_enable": dotenv_values.get("DIFY_RETRIEVE_RERANKING_ENABLE", False),
            "score_threshold": dotenv_values.get("DIFY_RETRIEVE_SCORE_THRESHOLD", 0),
        },
        "llm_config": {
            "base_url": llm_base_url,
            "api_key": llm_api_key,
            "model": llm_model,
        },
    }
    if isinstance(execution_feedback, dict) and execution_feedback:
        payload["execution_feedback"] = execution_feedback
    return payload


def load_execution_feedback(raw_path: str) -> Optional[Dict[str, Any]]:
    text = str(raw_path or "").strip()
    if not text:
        return None
    feedback_path = (PROJECT_ROOT / text).resolve()
    if not feedback_path.exists():
        raise FileNotFoundError(f"Execution feedback json not found: {feedback_path}")
    with feedback_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Execution feedback json must be an object.")
    return payload


async def run_client(
    *,
    ws_port: int,
    payload: Dict[str, Any],
    timeout_sec: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    uri = f"ws://127.0.0.1:{ws_port}"
    messages: List[Dict[str, Any]] = []
    result_data: Dict[str, Any] = {}

    async with websockets.connect(uri, max_size=16 * 1024 * 1024, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        started = time.perf_counter()
        while True:
            if time.perf_counter() - started > timeout_sec:
                raise TimeoutError(f"Workflow timed out after {timeout_sec} seconds.")
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
            data = json.loads(raw)
            messages.append(data)
            msg_type = data.get("type")
            if msg_type == "interaction":
                await ws.send(json.dumps({"type": "interaction_response", "value": "yes"}, ensure_ascii=False))
            elif msg_type == "result":
                result_data = data.get("data") or {}
                break
            elif msg_type == "phase_update" and data.get("status") == "error":
                error_code = data.get("error_code", "UNKNOWN")
                error_message = data.get("error_message", "Unknown phase error")
                raise RuntimeError(f"Workflow failed: [{error_code}] {error_message}")
    return result_data, messages


def _format_duration_ms(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return str(int(value))
    except Exception:
        return str(value)


def write_run_outputs(
    *,
    sample_file: Path,
    end_to_end_ms: int,
    result_data: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> Tuple[Path, Path]:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"sample_flow_timing_{ts}.json"
    md_path = reports_dir / f"sample_flow_timing_{ts}.md"

    traceability = result_data.get("traceability") or {}
    step_traces = traceability.get("step_traces") or []
    interaction_count = len([m for m in messages if m.get("type") == "interaction"])
    abnormal_count = result_data.get("abnormal_count")
    if abnormal_count is None:
        abnormal_count = len(result_data.get("abnormal_indicators") or [])
    step_duration_sum_ms = sum(int(step.get("duration_ms") or 0) for step in step_traces)

    summary_payload = {
        "generated_at": datetime.now().isoformat(),
        "workflow": "统一流程",
        "sample_file": str(sample_file),
        "end_to_end_ms": end_to_end_ms,
        "step_duration_sum_ms": step_duration_sum_ms,
        "report_md": result_data.get("report_md"),
        "report_pdf": result_data.get("report_pdf"),
        "abnormal_count": abnormal_count,
        "interaction_count": interaction_count,
        "step_traces": step_traces,
    }
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Sample Workflow Timing Report\n\n")
    lines.append(f"- run_time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("- workflow: 统一流程（直连LLM推理 + Dify知识检索）\n")
    lines.append(f"- sample_file: {sample_file}\n")
    lines.append(f"- end_to_end_ms: {end_to_end_ms}\n")
    lines.append(f"- step_duration_sum_ms: {step_duration_sum_ms}\n")
    lines.append(f"- abnormal_count: {abnormal_count}\n")
    lines.append(f"- interaction_count: {interaction_count}\n")
    lines.append(f"- business_report_md: {result_data.get('report_md')}\n")
    lines.append(f"- business_report_pdf: {result_data.get('report_pdf')}\n")

    if step_traces:
        lines.append("\n## Step Durations\n\n")
        lines.append("| Step | Title | Duration(ms) | Started | Ended |\n")
        lines.append("|---|---|---:|---|---|\n")
        for step in step_traces:
            lines.append(
                "| {step} | {title} | {duration} | {start} | {end} |\n".format(
                    step=step.get("step", "-"),
                    title=str(step.get("title", "-")).replace("|", "/"),
                    duration=_format_duration_ms(step.get("duration_ms")),
                    start=step.get("started_at", "-"),
                    end=step.get("ended_at", "-"),
                )
            )
    else:
        lines.append("\n## Step Durations\n\n- step_traces not found.\n")

    md_path.write_text("".join(lines), encoding="utf-8")
    return json_path, md_path


def write_supervisor_ledger(record: Dict[str, Any]) -> Path:
    ledger_path = PROJECT_ROOT / "reports" / "supervisor_runs.csv"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "timestamp",
        "attempt",
        "mode",
        "sample_file",
        "execution_feedback",
        "end_to_end_ms",
        "audit_enabled",
        "audit_status",
        "audit_rounds",
        "finding_count",
        "result",
        "report_md",
        "report_pdf",
        "timing_json",
        "audit_json",
        "ws_log",
        "note",
    ]
    write_header = not ledger_path.exists()
    with ledger_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if write_header:
            writer.writeheader()
        row = {k: record.get(k, "") for k in columns}
        writer.writerow(row)
    return ledger_path


def resolve_business_report_md_path(raw_path: Any) -> Optional[Path]:
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def load_audit_tools(disable_audit: bool):
    if disable_audit:
        return None, "disabled_by_flag"
    try:
        module = importlib.import_module("src.utils.report_audit")
        return module.BusinessReportAuditor, "enabled"
    except Exception as exc:
        return None, f"disabled_missing_module:{exc}"


def run_report_closed_loop(
    *,
    report_md_path: Path,
    timing_json_path: Path,
    auditor_cls,
) -> Dict[str, Any]:
    auditor = auditor_cls()
    result = auditor.audit(report_md_path=report_md_path, timing_json_path=timing_json_path)
    rounds: List[Dict[str, Any]] = [
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
    return result


def write_closed_loop_audit_output(audit_result: Dict[str, Any]) -> Tuple[Path, Path]:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"business_report_audit_{ts}.json"
    md_path = reports_dir / f"business_report_audit_{ts}.md"
    json_path.write_text(json.dumps(audit_result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Business Report Audit Closed Loop\n\n")
    lines.append(f"- audit_status: {audit_result.get('audit_status')}\n")
    summary = audit_result.get("summary") or {}
    lines.append(f"- critical_count: {summary.get('critical_count', 0)}\n")
    lines.append(f"- warning_count: {summary.get('warning_count', 0)}\n")
    lines.append(f"- finding_count: {summary.get('finding_count', 0)}\n")
    closed_loop = audit_result.get("closed_loop") or {}
    lines.append(f"- final_round: {closed_loop.get('final_round', 0)}\n")
    lines.append(f"- auto_fix_enabled: {closed_loop.get('auto_fix_enabled', False)}\n")
    lines.append("\n## Closed-Loop Rounds\n\n")
    for item in closed_loop.get("rounds") or []:
        lines.append(
            f"- Round {item.get('round')}: status={item.get('audit_status')} "
            f"summary={item.get('summary')} actions={item.get('actions')}\n"
        )
    lines.append("\n## Findings\n\n")
    findings = audit_result.get("findings") or []
    if not findings:
        lines.append("- none\n")
    else:
        for idx, f in enumerate(findings, start=1):
            lines.append(f"{idx}. [{f.get('severity')}] {f.get('code')} - {f.get('message')}\n")
            if f.get("details"):
                lines.append(f"   - details: {f.get('details')}\n")
    md_path.write_text("".join(lines), encoding="utf-8")
    return json_path, md_path


def run_single_supervised_attempt(
    *,
    args: argparse.Namespace,
    payload: Dict[str, Any],
    sample_file: Path,
    attempt: int,
    max_attempts: int,
    auditor_cls,
    audit_mode_label: str,
) -> Tuple[bool, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    server_log = PROJECT_ROOT / "logs" / f"sample_flow_ws_server_{ts}.log"
    ws_process: Optional[subprocess.Popen] = None
    run_start = time.perf_counter()

    audit_status = "skipped"
    audit_rounds = 0
    finding_count = 0
    audit_json_path: Optional[Path] = None
    report_md_path: Optional[Path] = None
    report_pdf_path: Optional[str] = None
    timing_json_path: Optional[Path] = None

    try:
        ws_process = start_ws_server(args.ws_port, server_log)
        if not wait_for_port(args.ws_port, timeout_sec=30):
            raise RuntimeError(f"WebSocket server did not open port {args.ws_port} within 30 seconds.")

        result_data, messages = asyncio.run(
            run_client(
                ws_port=args.ws_port,
                payload=payload,
                timeout_sec=args.timeout_sec,
            )
        )
        end_to_end_ms = int((time.perf_counter() - run_start) * 1000)
        timing_json_path, timing_md_path = write_run_outputs(
            sample_file=sample_file,
            end_to_end_ms=end_to_end_ms,
            result_data=result_data,
            messages=messages,
        )
        report_md_path = resolve_business_report_md_path(result_data.get("report_md"))
        report_pdf_path = result_data.get("report_pdf")

        if auditor_cls and report_md_path and report_md_path.exists():
            audit_result = run_report_closed_loop(
                report_md_path=report_md_path,
                timing_json_path=timing_json_path,
                auditor_cls=auditor_cls,
            )
            audit_status = str(audit_result.get("audit_status") or "unknown")
            audit_rounds = int((audit_result.get("closed_loop") or {}).get("final_round") or 0)
            finding_count = int((audit_result.get("summary") or {}).get("finding_count") or 0)
            audit_json_path, audit_md_path = write_closed_loop_audit_output(audit_result)
        else:
            audit_md_path = None
            if args.disable_audit or not auditor_cls:
                audit_status = "skipped"

        print("Workflow attempt completed.")
        print(f"Attempt: {attempt}/{max_attempts}")
        print(f"Sample: {sample_file}")
        print(f"End-to-end: {end_to_end_ms} ms")
        print(f"Business report MD: {result_data.get('report_md')}")
        print(f"Business report PDF: {result_data.get('report_pdf')}")
        print(f"Timing summary JSON: {timing_json_path}")
        print(f"Timing summary MD: {timing_md_path}")
        if report_md_path:
            print(f"Audit target report MD: {report_md_path}")
        if audit_json_path and audit_md_path:
            print(f"Audit closed-loop JSON: {audit_json_path}")
            print(f"Audit closed-loop MD: {audit_md_path}")
        print(f"Audit mode: {audit_mode_label}")
        print(f"Audit status: {audit_status}")
        print(f"WebSocket server log: {server_log}")

        ledger_path = write_supervisor_ledger(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "attempt": attempt,
                "mode": "统一流程",
                "sample_file": str(sample_file),
                "execution_feedback": bool(payload.get("execution_feedback")),
                "end_to_end_ms": end_to_end_ms,
                "audit_enabled": bool(auditor_cls),
                "audit_status": audit_status,
                "audit_rounds": audit_rounds,
                "finding_count": finding_count,
                "result": "passed" if audit_status in {"passed", "skipped"} else "failed",
                "report_md": str(report_md_path) if report_md_path else "",
                "report_pdf": str(report_pdf_path or ""),
                "timing_json": str(timing_json_path) if timing_json_path else "",
                "audit_json": str(audit_json_path) if audit_json_path else "",
                "ws_log": str(server_log),
                "note": args.task_note,
            }
        )
        print(f"Supervisor ledger: {ledger_path}")

        if audit_status in {"passed", "skipped"}:
            print("Supervisor decision: PASSED.")
            return True, ""
        return False, f"Audit status is `{audit_status}`."
    finally:
        stop_ws_server(ws_process)


def main() -> int:
    args = parse_args()
    dotenv_values = parse_dotenv(PROJECT_ROOT / ".env")
    sample_file = pick_sample_file(args.sample_file)
    execution_feedback = load_execution_feedback(args.execution_feedback_json)
    payload = build_payload(
        sample_file=sample_file,
        dotenv_values=dotenv_values,
        task_note=args.task_note,
        execution_feedback=execution_feedback,
    )

    auditor_cls, audit_mode_label = load_audit_tools(args.disable_audit)
    max_attempts = max(1, int(args.max_supervisor_runs))
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            ok, reason = run_single_supervised_attempt(
                args=args,
                payload=payload,
                sample_file=sample_file,
                attempt=attempt,
                max_attempts=max_attempts,
                auditor_cls=auditor_cls,
                audit_mode_label=audit_mode_label,
            )
            if ok:
                return 0
            last_error = reason
            if attempt < max_attempts:
                print("Supervisor decision: retrying full workflow because audit did not pass.")
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                print(f"Supervisor decision: attempt failed ({exc}), retrying...")
            else:
                raise

    raise RuntimeError(f"Supervisor failed after {max_attempts} attempts. Last error: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
