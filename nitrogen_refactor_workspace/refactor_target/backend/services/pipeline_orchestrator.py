from __future__ import annotations

from typing import Any, Dict, List

from ..schemas.contracts import DetectionEvent
from .detection_service import NitrogenDetectionService
from .process_analysis_service import ProcessAnalysisService
from .twin_validation_service import TwinValidationService


class NitrogenPipelineOrchestrator:
    def __init__(self) -> None:
        self.detection_service = NitrogenDetectionService()
        self.process_analysis_service = ProcessAnalysisService()
        self.twin_validation_service = TwinValidationService()

    def run(self, rows: List[Dict[str, Any]], options: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = self.detection_service.detect_from_timeseries(rows, options)
        outputs: List[Dict[str, Any]] = []
        for event in events:
            diagnosis = self.process_analysis_service.analyze_event(
                event=event,
                rows_before=[],
                rows_during=[],
                rows_after=[],
            )
            validation = self.twin_validation_service.validate_diagnosis(diagnosis)
            outputs.append(self._pack(event, diagnosis, validation))
        return outputs

    def _pack(self, event: DetectionEvent, diagnosis: Any, validation: Any) -> Dict[str, Any]:
        return {
            "event": event,
            "diagnosis": diagnosis,
            "validation": validation,
        }
