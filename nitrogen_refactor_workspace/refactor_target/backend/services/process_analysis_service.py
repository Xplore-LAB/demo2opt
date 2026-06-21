from __future__ import annotations

from typing import Any, Dict, List

from ..schemas.contracts import DetectionEvent, ProcessDiagnosis


class ProcessAnalysisService:
    """
    第一阶段先承接当前区间分析接口的结构化输出能力。
    后续再逐步引入垂域微调模型。
    """

    def analyze_event(
        self,
        event: DetectionEvent,
        rows_before: List[Dict[str, Any]],
        rows_during: List[Dict[str, Any]],
        rows_after: List[Dict[str, Any]],
    ) -> ProcessDiagnosis:
        _ = rows_before
        _ = rows_during
        _ = rows_after
        return ProcessDiagnosis(
            event_id=event.event_id,
            conclusion="pending",
            branch_ranking=[],
            evidence_nodes=[],
            missing_information=[],
            action_advice=[],
            analysis_confidence=0.0,
            trace={
                "status": "placeholder",
                "next_source": "legacy_snapshot/backend/server.py -> nitrogen_agent_analyze",
            },
        )
