"""
Interactive REPL: Dify dataset retrieve mode only.

This script only uses:
  POST /datasets/{dataset_id}/retrieve

Env required:
  LLM_API_KEY
  LLM_BASE_URL
  LLM_MODEL_NAME
  DIFY_API_KEY
  DIFY_DATASET_ID

Env optional:
  DIFY_DATASETS_API_URL or DIFY_API_URL (default: http://localhost/v1)
  DIFY_RETRIEVE_TOP_K (default: 5)
  DIFY_RETRIEVE_SEARCH_METHOD (default: semantic_search)
  DIFY_RETRIEVE_RERANKING_ENABLE (default: false)
  DIFY_RETRIEVE_SCORE_THRESHOLD (default: 0)
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


class DatasetRetrieveInteractive:
    def __init__(self, dataset_id_override: str = "") -> None:
        load_dotenv()
        _configure_console_utf8()

        llm_api_key = _require_env("LLM_API_KEY")
        llm_base_url = _require_env("LLM_BASE_URL")
        llm_model_name = _require_env("LLM_MODEL_NAME")

        kb_api_key = _require_env("DIFY_API_KEY")
        kb_dataset_id = str(dataset_id_override or os.getenv("DIFY_DATASET_ID", "")).strip()
        if not kb_dataset_id:
            raise RuntimeError("Missing dataset_id. Set DIFY_DATASET_ID or pass --dataset-id.")
        kb_api_url = (
            str(os.getenv("DIFY_DATASETS_API_URL", "")).strip()
            or str(os.getenv("DIFY_API_URL", "")).strip()
            or "http://localhost/v1"
        )

        self.retrieval_stage = "primary"
        self.show_kb_details = True
        self.dataset_id = kb_dataset_id
        self.top_k = int(str(os.getenv("DIFY_RETRIEVE_TOP_K", "5") or "5"))

        self.kb_service = KnowledgeRetrievalService(
            {
                "api_url": kb_api_url,
                "api_key": kb_api_key,
                "api_mode": "datasets_retrieve",
                "dataset_id": kb_dataset_id,
                "top_k": self.top_k,
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

    @staticmethod
    def _fmt_chunks(records: List[Dict[str, Any]], limit: int = 5) -> str:
        if not records:
            return "未命中知识片段"
        lines: List[str] = []
        for item in records[:limit]:
            rank = item.get("rank", "-")
            title = str(item.get("title") or f"chunk_{rank}")
            score = item.get("score")
            content = str(item.get("content") or "").strip()
            if len(content) > 500:
                content = f"{content[:500].rstrip()}..."
            lines.append(f"[{rank}] {title} | score={score}\n{content}")
        return "\n---\n".join(lines)

    def _retrieve(self, query: str) -> Dict[str, Any]:
        safe_query = self._sanitize_text(query)
        self.kb_service.retrieval_model["top_k"] = max(1, int(self.top_k))
        return self.kb_service.retrieve_measures(
            overall_judgement={"summary": f"用户问题：{safe_query}"},
            abnormal_details=[],
            task_note=safe_query,
            retrieval_stage=self.retrieval_stage,
        )

    def _ask_llm(self, query: str, kb: Dict[str, Any]) -> str:
        safe_query = self._sanitize_text(query)
        summary = str(kb.get("retrieval_summary") or "未返回检索摘要")
        chunks = self._fmt_chunks(kb.get("records") if isinstance(kb.get("records"), list) else [], limit=self.top_k)
        refs = kb.get("knowledge_references") if isinstance(kb.get("knowledge_references"), list) else []
        refs_text = "\n".join(str(x) for x in refs[:5]) if refs else "无"

        system_prompt = (
            "你是工业空分装置优化助手。请严格基于给定知识片段回答。"
            "如果知识片段不足，请明确写“知识库中未找到充分依据”，不得编造。"
            "输出结构：结论、建议步骤、风险提示。"
        )
        user_prompt = (
            f"用户问题:\n{safe_query}\n\n"
            f"检索摘要:\n{summary}\n\n"
            f"命中片段:\n{chunks}\n\n"
            f"参考索引:\n{refs_text}\n\n"
            "请用中文回答。"
        )

        result = self.llm.chat(query=user_prompt, system_prompt=system_prompt, temperature=0.2)
        if not result.get("ok", True):
            raise RuntimeError(f"LLM 调用失败: {result.get('error')}")
        return self._repair_mojibake(str(result.get("answer") or "").strip()) or "模型未返回有效文本。"

    def _print_help(self) -> None:
        print("Commands:")
        print("  /help               查看帮助")
        print("  /exit               退出")
        print("  /stage primary      主检索")
        print("  /stage review       复核检索")
        print("  /topk N             设置 top_k (1-20)")
        print("  /showkb on|off      显示/隐藏片段详情")
        print("  /selftest           固定问题联调")

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
            print(f"已切换检索阶段: {self.retrieval_stage}")
            return True
        if cmd.startswith("/topk "):
            raw = cmd.split(" ", 1)[1].strip()
            try:
                value = int(raw)
                if value < 1 or value > 20:
                    raise ValueError("out of range")
                self.top_k = value
                print(f"已设置 top_k: {self.top_k}")
            except Exception:
                print("请使用 /topk 1~20")
            return True
        if cmd.startswith("/showkb "):
            value = cmd.split(" ", 1)[1].strip().lower()
            self.show_kb_details = value in {"on", "1", "true", "yes", "y"}
            print(f"显示片段详情: {'开启' if self.show_kb_details else '关闭'}")
            return True
        if cmd == "/selftest":
            sample = "膨胀机B制冷量偏低，先做什么？"
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
        try:
            kb = self._retrieve(safe_query)
        except Exception as exc:
            print(f"\n[错误] 知识库检索失败: {exc}")
            return

        if self.show_kb_details:
            print("\n[知识库检索]")
            print(str(kb.get("retrieval_summary") or "未返回检索摘要"))
            print(self._fmt_chunks(kb.get("records") if isinstance(kb.get("records"), list) else [], limit=self.top_k))

        try:
            answer = self._ask_llm(safe_query, kb)
        except Exception as exc:
            print(f"\n[错误] 模型调用失败: {exc}")
            return

        print("\n[模型回答]")
        print(answer)

    def run(self) -> None:
        print("=" * 72)
        print("LLM + Dify Dataset Retrieve 交互测试 (仅新模式)")
        print(f"dataset_id: {self.dataset_id}")
        print(f"default top_k: {self.top_k}")
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

            self._handle_query(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM + Dify Dataset Retrieve 交互测试（仅新模式）")
    parser.add_argument("--once", type=str, default="", help="单次测试问题，执行后退出")
    parser.add_argument("--dataset-id", type=str, default="", help="Dify dataset_id（优先于环境变量 DIFY_DATASET_ID）")
    args = parser.parse_args()

    runner = DatasetRetrieveInteractive(dataset_id_override=args.dataset_id)
    if args.once:
        runner._handle_query(args.once)
    else:
        runner.run()
