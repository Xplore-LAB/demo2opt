"""
Terminal REPL for live testing: external knowledge API + current LLM.

Usage:
  python scripts/run_llm_kb_interactive.py
  python scripts/run_llm_kb_interactive.py --once "your question"
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.prompts.templates import SimpleLLMClient
from src.services.knowledge_retrieval_service import KnowledgeRetrievalService


def _configure_console_utf8() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _require_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


class LLMKBInteractiveRunner:
    def __init__(self) -> None:
        load_dotenv()
        _configure_console_utf8()

        llm_api_key = _require_env("LLM_API_KEY")
        llm_base_url = _require_env("LLM_BASE_URL")
        llm_model_name = _require_env("LLM_MODEL_NAME")

        kb_api_key = _require_env("DIFY_API_KEY")
        kb_api_url = (
            str(os.getenv("DIFY_DATASETS_API_URL", "")).strip()
            or str(os.getenv("DIFY_API_URL", "")).strip()
            or "http://localhost/v1"
        )
        kb_mode = str(os.getenv("DIFY_RETRIEVAL_API_MODE", "datasets_retrieve")).strip() or "datasets_retrieve"
        kb_dataset_id = str(os.getenv("DIFY_DATASET_ID", "")).strip()

        self.retrieval_stage = "primary"
        self.show_kb_details = True
        self.kb_mode = kb_mode
        self.kb_dataset_id = kb_dataset_id

        self.kb_service = KnowledgeRetrievalService(
            {
                "api_url": kb_api_url,
                "api_key": kb_api_key,
                "api_mode": kb_mode,
                "dataset_id": kb_dataset_id,
                "page": 1,
                "limit": 20,
                "top_k": int(os.getenv("DIFY_RETRIEVE_TOP_K", "5") or 5),
                "search_method": os.getenv("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search"),
                "reranking_enable": os.getenv("DIFY_RETRIEVE_RERANKING_ENABLE", "false"),
                "score_threshold": os.getenv("DIFY_RETRIEVE_SCORE_THRESHOLD", "0"),
            }
        )
        self.llm = SimpleLLMClient(
            api_url=llm_base_url,
            api_key=llm_api_key,
            model_name=llm_model_name,
            knowledge_manager=None,
        )

    @staticmethod
    def _format_list(items: List[str], title: str, empty_text: str) -> str:
        if not items:
            return f"{title}\n- {empty_text}"
        lines = [title]
        for idx, item in enumerate(items[:5], start=1):
            lines.append(f"{idx}. {item}")
        return "\n".join(lines)

    @staticmethod
    def _sanitize_text(text: str) -> str:
        raw = str(text or "")
        sanitized = "".join(ch for ch in raw if not (0xD800 <= ord(ch) <= 0xDFFF))
        sanitized = sanitized.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        return sanitized.strip()

    @staticmethod
    def _repair_mojibake(text: str) -> str:
        raw = str(text or "")
        if not raw:
            return raw
        try:
            repaired = raw.encode("latin1", errors="strict").decode("utf-8", errors="strict")
        except Exception:
            return raw
        origin_zh = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
        repaired_zh = sum(1 for ch in repaired if "\u4e00" <= ch <= "\u9fff")
        return repaired if repaired_zh > origin_zh else raw

    def _retrieve_knowledge(self, query: str) -> Dict[str, Any]:
        safe_query = self._sanitize_text(query)
        try:
            return self.kb_service.retrieve_measures(
                overall_judgement={"summary": f"用户问题：{safe_query}"},
                abnormal_details=[],
                task_note=safe_query,
                retrieval_stage=self.retrieval_stage,
            )
        except Exception as exc:
            return {
                "retrieval_summary": f"外挂知识库检索失败：{exc}",
                "knowledge_references": [],
                "risk_tips": [f"知识库接口异常：{exc}"],
                "datasets": [],
                "records": [],
            }

    def _build_kb_context_text(self, kb: Dict[str, Any]) -> str:
        summary = str(kb.get("retrieval_summary") or "未返回检索摘要。")
        refs = kb.get("knowledge_references") or []
        references = [str(x) for x in refs if str(x).strip()]
        risk_tips = [str(x) for x in (kb.get("risk_tips") or []) if str(x).strip()]
        hit_chunks = kb.get("records") if isinstance(kb.get("records"), list) else []
        hit_info = f"命中片段数: {len(hit_chunks)}"

        sections = [
            f"检索摘要: {summary}",
            hit_info,
            self._format_list(references, "知识支撑项:", "未命中可用知识条目"),
            self._format_list(risk_tips, "风险提示:", "无"),
        ]
        return "\n".join(sections)

    def _ask_llm(self, query: str, kb: Dict[str, Any]) -> str:
        safe_query = self._sanitize_text(query)
        kb_context = self._build_kb_context_text(kb)
        system_prompt = (
            "你是工业空分装置优化助手。必须结合“外挂知识库检索结果”与用户输入给出中文回答。"
            "若知识库未命中，必须明确说明“知识库未命中”，并给出可执行的通用建议。"
            "输出结构固定为：结论、建议步骤、风险提示。"
        )
        user_prompt = (
            f"用户问题:\n{safe_query}\n\n"
            f"外挂知识库检索结果:\n{kb_context}\n\n"
            "请基于以上信息作答，避免编造未给出的具体参数。"
        )
        result = self.llm.chat(query=user_prompt, system_prompt=system_prompt, temperature=0.2)
        if not result.get("ok", True):
            raise RuntimeError(f"LLM 调用失败: {result.get('error')}")
        answer = str(result.get("answer") or "").strip()
        answer = self._repair_mojibake(answer)
        return answer or "模型未返回有效文本。"

    def _print_help(self) -> None:
        print("可用命令:")
        print("  /help                 查看帮助")
        print("  /exit                 退出")
        print("  /stage primary        主检索模式")
        print("  /stage review         复核检索模式")
        print("  /showkb on|off        显示/隐藏检索详情")
        print("  /selftest             固定问题联调自测")

    def _handle_command(self, text: str) -> bool:
        cmd = text.strip()
        if cmd in {"/exit", "/quit"}:
            return False
        if cmd == "/help":
            self._print_help()
            return True
        if cmd.startswith("/stage "):
            mode = cmd.split(" ", 1)[1].strip().lower()
            if mode not in {"primary", "review"}:
                print("仅支持 /stage primary 或 /stage review")
                return True
            self.retrieval_stage = mode
            print(f"已切换检索模式: {self.retrieval_stage}")
            return True
        if cmd.startswith("/showkb "):
            value = cmd.split(" ", 1)[1].strip().lower()
            self.show_kb_details = value in {"on", "1", "true", "yes", "y"}
            print(f"显示检索详情: {'开启' if self.show_kb_details else '关闭'}")
            return True
        if cmd == "/selftest":
            sample = "膨胀机B制冷量偏低，应该先做什么？"
            print(f"你> {sample}")
            self._handle_query(sample)
            return True

        print("未知命令，输入 /help 查看说明。")
        return True

    def _handle_query(self, query: str) -> None:
        safe_query = self._sanitize_text(query)
        if not safe_query:
            print("\n[错误] 输入为空或包含非法字符。")
            return

        kb = self._retrieve_knowledge(safe_query)
        if self.show_kb_details:
            print("\n[外挂知识库]")
            print(self._build_kb_context_text(kb))
        answer = self._ask_llm(safe_query, kb)
        print("\n[模型回答]")
        print(answer)

    def run(self) -> None:
        print("=" * 72)
        print("LLM + 外挂知识库 终端交互测试")
        print(f"检索模式(api_mode): {self.kb_mode} (single-mode runtime)")
        print(f"dataset_id: {self.kb_dataset_id or '(未设置)'}")
        print("输入问题直接测试；输入 /help 查看命令；输入 /exit 退出。")
        print("=" * 72)

        while True:
            try:
                text = input("\n你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出。")
                break

            if not text:
                continue
            if text.startswith("/"):
                if not self._handle_command(text):
                    break
                continue

            try:
                self._handle_query(text)
            except Exception as exc:
                print(f"\n[错误] {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM + 外挂知识库终端交互测试")
    parser.add_argument("--once", type=str, default="", help="单次测试问题，执行后退出")
    args = parser.parse_args()

    try:
        runner = LLMKBInteractiveRunner()
        if args.once:
            runner._handle_query(args.once)
        else:
            runner.run()
    except Exception as exc:
        print(f"启动失败: {exc}")
        raise
