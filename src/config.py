"""Backward-compatible config exports."""

from src.core.config import ConfigManager, MetricConfig, get_config_manager

__all__ = ["ConfigManager", "MetricConfig", "get_config_manager"]
