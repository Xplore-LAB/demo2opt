from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DetectionEvent:
    event_id: str
    start_ms: int
    valley_ms: int
    end_ms: int
    shape_type: str
    severity: str
    confidence: float
    workpoint: Optional[float] = None
    min_value: Optional[float] = None
    dip_depth: Optional[float] = None
    duration_min: Optional[float] = None
    recovery_ratio: Optional[float] = None
    supporting_tags: List[str] = field(default_factory=list)
    image_refs: List[str] = field(default_factory=list)
    series_refs: List[str] = field(default_factory=list)
    trace: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessDiagnosis:
    event_id: str
    conclusion: str
    branch_ranking: List[Dict[str, Any]] = field(default_factory=list)
    evidence_nodes: List[Dict[str, Any]] = field(default_factory=list)
    missing_information: List[Any] = field(default_factory=list)
    action_advice: List[str] = field(default_factory=list)
    analysis_confidence: float = 0.0
    trace: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TwinValidationResult:
    event_id: str
    scenario_id: str
    constraints_passed: bool
    predicted_kpis: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "unknown"
    rollback_hint: str = ""
    validation_trace: Dict[str, Any] = field(default_factory=dict)
