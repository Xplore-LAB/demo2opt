from __future__ import annotations

from typing import Any, Dict, List

from ..schemas.contracts import DetectionEvent


class NitrogenDetectionService:
    """
    第一阶段先保留规则检测入口。
    后续可替换为图像小模型或规则+模型双轨输出。
    """

    def detect_from_timeseries(self, rows: List[Dict[str, Any]], options: Dict[str, Any]) -> List[DetectionEvent]:
        """
        占位实现：
        - 当前先定义统一入口
        - 下一步把 legacy_snapshot/frontend/utils/nitrogenCore.js 的核心检测逻辑迁移进来
        """
        _ = rows
        _ = options
        return []
