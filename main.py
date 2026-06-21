"""Thin entrypoint for the unified agent runtime."""

from __future__ import annotations

import argparse

from src.agent.cli import AirSeparationOptimizer, run_all_tests, run_cli_analysis, start_services


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="工业空分装置智能优化系统 v2.0")
    parser.add_argument("--test", action="store_true", help="运行内置模块测试")
    parser.add_argument("--analyze", action="store_true", help="执行一次离线分析，而不是启动前后端")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开前端页面")
    parser.add_argument("--data", type=str, default=None, help="传感器数据文件路径")
    parser.add_argument("--async", action="store_true", dest="enable_async", help="启用异步处理模式")
    parser.add_argument("--no-cot", action="store_true", dest="disable_cot", help="禁用多步思考（Chain of Thought）")
    parser.add_argument("--asu", action="store_true", dest="use_asu_pipeline", help="使用 ASU 时间序列管道")
    parser.add_argument("--execution-feedback-json", type=str, default="", help="执行反馈 JSON 路径（用于闭环验证）")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.test:
        run_all_tests()
        return
    if args.analyze:
        run_cli_analysis(args)
        return
    start_services(open_browser=args.open_browser)


if __name__ == "__main__":
    main()

