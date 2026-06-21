from __future__ import annotations

from ..schemas.contracts import ProcessDiagnosis, TwinValidationResult


class TwinValidationService:
    """
    第一阶段先定义独立验证接口。
    后续把物料平衡、稳态验证、动态验证逐步接进来。
    """

    def validate_diagnosis(self, diagnosis: ProcessDiagnosis) -> TwinValidationResult:
        return TwinValidationResult(
            event_id=diagnosis.event_id,
            scenario_id=f"{diagnosis.event_id}-placeholder",
            constraints_passed=False,
            predicted_kpis={},
            risk_level="pending",
            rollback_hint="待接入稳态/动态仿真后生成。",
            validation_trace={
                "status": "placeholder",
                "next_source": "legacy_snapshot/services/decision_service.py",
            },
        )
