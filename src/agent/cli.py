"""CLI/runtime helpers for the agent entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from src.agent.core.runtime import AgentRuntimeHooks
from src.agent.workflows.runner import run_analysis
from src.utils.llm_json import repair_llm_text

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_START_SCRIPT = PROJECT_ROOT / "scripts" / "start_web.py"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_DATA_FILE = "data/【原始数据】运行诊断.xlsx"


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def clean_console_text(value: Any) -> str:
    return repair_llm_text(str(value or "")).replace("\ufffd", "").strip()


def verification_status_text(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status == "passed":
        return "通过"
    if status == "failed":
        return "未通过"
    if status == "pending":
        return "待现场验证"
    return clean_console_text(value) or "未提供"


configure_console_encoding()


class ConsoleHooks(AgentRuntimeHooks):
    def __init__(self):
        super().__init__(on_log=self._log, on_phase_update=self._phase_update)

    @staticmethod
    def _log(text: str, level: str = "info", category: str = "system", **kwargs: Any) -> None:
        prefix = f"[{category}/{level}]"
        if kwargs.get("workflow_step_title"):
            prefix += f" {clean_console_text(kwargs['workflow_step_title'])}"
        print(f"{prefix} {clean_console_text(text)}")

    @staticmethod
    def _phase_update(phase: str, status: str, step: Optional[int] = None, **kwargs: Any) -> None:
        if status == "running" and kwargs.get("workflow_step_state") == "started":
            title = clean_console_text(kwargs.get("workflow_step_title") or phase)
            print(f"\n[{phase}] {title}...")


class AirSeparationOptimizer:
    """Compatibility adapter that delegates orchestration to the agent runner."""

    def __init__(
        self,
        data_file: Optional[str] = None,
        enable_async: bool = False,
        enable_cot: bool = True,
        use_asu_pipeline: bool = False,
        execution_feedback: Optional[Dict[str, Any]] = None,
    ):
        self.data_file = data_file or os.getenv("DATA_FILE", DEFAULT_DATA_FILE)
        self.enable_async = enable_async
        self.enable_cot = enable_cot
        self.use_asu_pipeline = use_asu_pipeline
        self.execution_feedback = execution_feedback or {}

    def _service_overrides(self) -> Dict[str, Any]:
        overrides = {}
        for name in ("data_loader", "semantics_service", "reasoning_engine", "decision_service", "report_generator"):
            if hasattr(self, name):
                overrides[name] = getattr(self, name)
        return overrides

    def run_analysis(self) -> Dict[str, Any]:
        data_file = getattr(self, "data_file", os.getenv("DATA_FILE", DEFAULT_DATA_FILE))
        result = run_analysis(
            {
                "entrypoint": "cli",
                "data_file": data_file,
                "display_file_name": os.path.basename(data_file),
                "enable_async": getattr(self, "enable_async", False),
                "enable_cot": getattr(self, "enable_cot", True),
                "use_asu_pipeline": getattr(self, "use_asu_pipeline", False),
                "execution_feedback": getattr(self, "execution_feedback", {}) or {},
                "auto_confirm": True,
                "service_overrides": self._service_overrides(),
            },
            hooks=ConsoleHooks(),
        )
        analysis_result = result.get("analysis_result") or {}
        if analysis_result.get("status") == "abnormal":
            self._print_results(
                analysis_result.get("semantic_data") or [],
                analysis_result.get("reasoning_result") or {},
                analysis_result.get("decision_result") or {},
            )
        return analysis_result

    def _print_results(self, semantic_data: Any, reasoning_result: Any, decision_result: Any) -> None:
        print("\n【异常指标】")
        abnormal_items = [x for x in semantic_data if x.get("state_desc") not in ["正常", "Unknown"]]
        for item in abnormal_items[:5]:
            print(
                f"  - {clean_console_text(item.get('name'))}: "
                f"{clean_console_text(item.get('state_desc'))} "
                f"(当前值: {item.get('current_value')})"
            )
        print("\n【推理分析】")
        print(f"  根本原因: {clean_console_text((reasoning_result or {}).get('root_cause', 'N/A'))}")
        print(f"  操作建议: {clean_console_text((reasoning_result or {}).get('operation_suggestion', 'N/A'))}")
        print(f"  安全警告: {clean_console_text((reasoning_result or {}).get('safety_warning', 'N/A'))}")
        print("\n【决策建议】")
        print(f"  操作步骤: {clean_console_text((decision_result or {}).get('actionable_steps', 'N/A'))}")
        print(f"  验证状态: {verification_status_text((decision_result or {}).get('verification_status', 'N/A'))}")


def _npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _frontend_command(frontend_port: int) -> list[str]:
    vite_cli = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    vite_args = ["--host", "0.0.0.0", "--port", str(frontend_port), "--strictPort"]
    if os.name == "nt" and vite_cli.exists():
        return ["node", str(vite_cli), *vite_args]
    return [_npm_executable(), "run", "dev", "--", *vite_args]


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _find_free_port(preferred: int, attempts: int = 20) -> int:
    for port in range(preferred, preferred + attempts):
        if _port_in_use(port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_services(open_browser: bool = False) -> None:
    frontend_port = _find_free_port(8080)
    backend_cmd = [sys.executable, str(BACKEND_START_SCRIPT)]
    frontend_cmd = _frontend_command(frontend_port)
    popen_kwargs: Dict[str, Any] = {}

    print("=" * 80)
    print("工业空分装置智能优化系统 v2.0 - 一键启动")
    print("=" * 80)
    print(f"后端启动命令: {' '.join(backend_cmd)}")
    print(f"前端启动目录: {FRONTEND_DIR}")
    print("REST API: http://127.0.0.1:5000")
    print("WebSocket: ws://127.0.0.1:8001")
    print(f"前端页面: http://127.0.0.1:{frontend_port}")
    print("按 Ctrl+C 停止全部服务")

    backend_proc = subprocess.Popen(backend_cmd, cwd=str(PROJECT_ROOT), **popen_kwargs)
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=str(FRONTEND_DIR), **popen_kwargs)

    if open_browser:
        import webbrowser

        time.sleep(2)
        webbrowser.open(f"http://127.0.0.1:{frontend_port}")

    try:
        while True:
            backend_code = backend_proc.poll()
            frontend_code = frontend_proc.poll()
            if backend_code is not None:
                raise RuntimeError(f"后端服务已退出，退出码={backend_code}")
            if frontend_code is not None and not _port_in_use(frontend_port):
                raise RuntimeError(f"前端服务已退出，退出码={frontend_code}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到退出信号，正在停止前后端服务...")
    finally:
        for proc in (frontend_proc, backend_proc):
            if proc.poll() is None:
                try:
                    if os.name == "nt":
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        proc.terminate()
                except Exception:
                    proc.terminate()
        for proc in (frontend_proc, backend_proc):
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


def run_all_tests() -> None:
    from src.services.data_loader import test_data_loader
    from src.services.data_semantics import test_data_semantics
    from src.services.decision_service import test_decision_service
    from src.services.reasoning_engine_v2 import test_reasoning_engine

    tests = [
        ("数据加载器", test_data_loader),
        ("数据语义服务", test_data_semantics),
        ("决策服务", test_decision_service),
        ("推理引擎", test_reasoning_engine),
    ]
    results = []
    for name, test_func in tests:
        try:
            results.append((name, test_func()))
        except Exception:
            results.append((name, False))
    passed = sum(1 for _, result in results if result)
    print(f"通过: {passed}/{len(results)}")
    for name, result in results:
        print(f"  {name}: {'通过' if result else '失败'}")


def run_cli_analysis(args: argparse.Namespace) -> None:
    execution_feedback = None
    if args.execution_feedback_json:
        with open(args.execution_feedback_json, "r", encoding="utf-8") as handle:
            execution_feedback = json.load(handle)
    optimizer = AirSeparationOptimizer(
        data_file=args.data,
        enable_async=args.enable_async,
        enable_cot=not args.disable_cot,
        use_asu_pipeline=args.use_asu_pipeline,
        execution_feedback=execution_feedback,
    )
    result = optimizer.run_analysis()
    if result.get("report_pdf") or result.get("report_md"):
        print("\n报告产物")
        if result.get("report_pdf"):
            print(f"  PDF: {result['report_pdf']}")
        if result.get("report_md"):
            print(f"  Markdown: {result['report_md']}")

