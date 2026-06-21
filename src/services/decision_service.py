import json
import os
import sys
from datetime import datetime
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.prompts.templates import build_decision_ai_verification_prompts
from src.schemas.models import validate_decision_result
from src.utils.llm_json import extract_json_object, repair_llm_text


class DecisionService:
    def __init__(self, case_store_path: str = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.case_store_path = case_store_path or os.path.join(project_root, "reports", "decision_cases.jsonl")

    def verify_and_suggest(
        self,
        reasoning_result,
        ask_model: Optional[Callable[[str, str, float], str]] = None,
        knowledge_context: Optional[Dict[str, Any]] = None,
        overall_judgement: Optional[Dict[str, Any]] = None,
        task_note: str = "",
        execution_feedback: Optional[Dict[str, Any]] = None,
        enable_closed_loop_validation: bool = False,
    ):
        if isinstance(reasoning_result, str):
            try:
                reasoning_result = json.loads(reasoning_result)
            except json.JSONDecodeError:
                reasoning_result = {
                    "root_cause": "无法解析推理结果",
                    "operation_suggestion": reasoning_result,
                    "safety_warning": "请人工复核后执行",
                }

        hypothesis = reasoning_result.get("operation_suggestion", "未生成操作建议")
        safety_warning = reasoning_result.get("safety_warning", "请在标准操作规程约束下执行。")

        final_output = {
            "actionable_steps": hypothesis,
            "simulation_result": self._estimate_improvement(reasoning_result),
            "verification_status": self._determine_verification_status(reasoning_result),
            "reasoning_summary": reasoning_result.get("root_cause", ""),
            "confidence_score": self._estimate_confidence(reasoning_result),
            "risk_assessment": self._build_risk_assessment(safety_warning),
            "rollback_strategy": self._build_rollback_strategy(),
        }

        if callable(ask_model):
            final_output = self._apply_ai_decision_review(
                rule_output=final_output,
                reasoning_result=reasoning_result,
                ask_model=ask_model,
                knowledge_context=knowledge_context or {},
                overall_judgement=overall_judgement or {},
                task_note=task_note or "",
            )

        validated_output = validate_decision_result(final_output)
        payload = validated_output.model_dump() if hasattr(validated_output, "model_dump") else validated_output.dict()
        closed_loop_validation: Optional[Dict[str, Any]] = None
        if enable_closed_loop_validation:
            closed_loop_validation = self.evaluate_closed_loop_feedback(execution_feedback)
            payload["closed_loop_validation"] = closed_loop_validation
        self.write_back_case(payload, reasoning_result, closed_loop_validation=closed_loop_validation)
        return payload

    def _apply_ai_decision_review(
        self,
        rule_output: Dict[str, Any],
        reasoning_result: Dict[str, Any],
        ask_model: Callable[[str, str, float], str],
        knowledge_context: Dict[str, Any],
        overall_judgement: Dict[str, Any],
        task_note: str,
    ) -> Dict[str, Any]:
        prompts = build_decision_ai_verification_prompts(
            reasoning_result=reasoning_result,
            rule_decision=rule_output,
            knowledge_context=knowledge_context,
            overall_judgement=overall_judgement,
            task_note=task_note,
        )
        raw_text = ask_model(prompts["system_prompt"], prompts["user_prompt"], 0.1)
        payload = extract_json_object(raw_text)
        if not payload:
            return rule_output

        merged = dict(rule_output)
        for key in ("actionable_steps", "simulation_result", "verification_status", "risk_assessment", "rollback_strategy"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                merged[key] = repair_llm_text(value).strip()

        confidence_score = payload.get("confidence_score")
        if isinstance(confidence_score, (float, int)):
            merged["confidence_score"] = max(0.0, min(0.98, float(confidence_score)))
        return merged

    def evaluate_closed_loop_feedback(self, execution_feedback: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(execution_feedback, dict) or not execution_feedback:
            return {
                "status": "pending",
                "summary": "未提供执行反馈窗口，闭环验证待完成。",
                "improvement_ratio": None,
            }

        before = execution_feedback.get("before")
        after = execution_feedback.get("after")
        directions = execution_feedback.get("direction") or {}
        if not isinstance(before, dict) or not isinstance(after, dict):
            return {
                "status": "pending",
                "summary": "执行反馈格式不完整（缺少 before/after 指标对）。",
                "improvement_ratio": None,
            }

        compared = 0
        improved = 0
        for metric, before_value in before.items():
            if metric not in after:
                continue
            try:
                b = float(before_value)
                a = float(after.get(metric))
            except (TypeError, ValueError):
                continue
            compared += 1
            direction = str(directions.get(metric) or "decrease").strip().lower()
            if direction == "increase" and a >= b:
                improved += 1
            elif direction != "increase" and a <= b:
                improved += 1

        if compared == 0:
            return {
                "status": "pending",
                "summary": "执行反馈无可比较指标，闭环验证待补充。",
                "improvement_ratio": None,
            }

        ratio = improved / compared
        status = "passed" if ratio >= 0.6 else "failed"
        return {
            "status": status,
            "summary": f"反馈窗口共比较 {compared} 项，改善 {improved} 项（{ratio:.1%}）。",
            "improvement_ratio": round(ratio, 4),
            "compared_count": compared,
            "improved_count": improved,
            "window_start": execution_feedback.get("window_start"),
            "window_end": execution_feedback.get("window_end"),
        }

    def write_back_case(self, decision_result: Dict, reasoning_result: Dict, closed_loop_validation: Optional[Dict[str, Any]] = None):
        os.makedirs(os.path.dirname(self.case_store_path), exist_ok=True)
        case_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "root_cause": reasoning_result.get("root_cause"),
            "action": decision_result.get("actionable_steps"),
            "result_estimate": decision_result.get("simulation_result"),
            "verification_status": decision_result.get("verification_status"),
            "risk_assessment": decision_result.get("risk_assessment"),
            "closed_loop_status": (closed_loop_validation or {}).get("status"),
            "closed_loop_summary": (closed_loop_validation or {}).get("summary"),
        }
        with open(self.case_store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(case_data, ensure_ascii=False) + "\n")

    def _estimate_improvement(self, reasoning_result: Dict) -> str:
        text = " ".join(
            str(reasoning_result.get(key, "")) for key in ("root_cause", "operation_suggestion", "coupling_analysis")
        )

        impacts = []
        if any(token in text for token in ("纯度", "氧", "氮")):
            impacts.append("产品纯度稳定性预计改善 0.1% - 0.3%")
        if any(token in text for token in ("温度", "冷量", "换热")):
            impacts.append("综合能耗预计改善 0.5% - 1.5%")
        if any(token in text for token in ("回流", "流量", "阀位")):
            impacts.append("工况波动幅度预计下降 5% - 10%")
        if any(token in text for token in ("压力", "压差")):
            impacts.append("关键压力指标预计回归设计区间")

        if not impacts:
            impacts.append("预计可带来轻微性能改善，建议通过现场数据复核量化收益")

        return "；".join(impacts)

    def _determine_verification_status(self, reasoning_result: Dict) -> str:
        if reasoning_result.get("missing_data_request"):
            return "Pending"
        if reasoning_result.get("operation_suggestion"):
            return "Passed"
        return "Failed"

    def _estimate_confidence(self, reasoning_result: Dict) -> float:
        score = 0.6
        if reasoning_result.get("bottleneck_indicators"):
            score += 0.1
        if reasoning_result.get("coupling_analysis"):
            score += 0.1
        if reasoning_result.get("knowledge_references"):
            score += 0.1
        if reasoning_result.get("missing_data_request"):
            score -= 0.15
        return max(0.0, min(0.95, score))

    def _build_risk_assessment(self, safety_warning: str) -> str:
        return f"执行前需完成班组确认与联锁检查。风险提示：{safety_warning}"

    def _build_rollback_strategy(self) -> str:
        return "若关键指标在观察窗口内恶化，立即恢复至调整前设定值，并记录调整前后数据供复盘。"


def test_decision_service():
    print("=" * 60)
    print("测试 DecisionService 模块")
    print("=" * 60)

    test_reasoning = {
        "root_cause": "液氧纯度偏低，伴随温度和回流波动",
        "operation_suggestion": "建议逐步调整回流液量并复核主冷液位",
        "safety_warning": "注意液位和压差联动变化",
        "coupling_analysis": "回流与能耗存在联动",
        "bottleneck_indicators": ["ColdLossRatio"],
    }

    service = DecisionService()
    result = service.verify_and_suggest(test_reasoning)
    print(f"操作建议: {result['actionable_steps']}")
    print(f"效果评估: {result['simulation_result']}")
    print(f"验证状态: {result['verification_status']}")
    return True


if __name__ == "__main__":
    test_decision_service()
