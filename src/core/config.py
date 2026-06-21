"""
配置管理模块

统一管理项目的所有配置，支持从配置文件加载
"""
import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class MetricConfig:
    metric_code: str
    name_cn: str
    design_value: float
    min_value: float
    max_value: float
    unit: str


class ConfigManager:
    """
    配置管理器
    """
    
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            # 修改为指向项目根目录下的 config 文件夹
            # src/core/config.py -> src/core -> src -> demo2opt -> config
            config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config')
        self.config_dir = config_dir
        self._metric_configs: Dict[str, MetricConfig] = {}
        self._load_metric_configs()
    
    def _load_metric_configs(self):
        """加载指标设计值配置"""
        config_path = os.path.join(self.config_dir, 'metric_design_values.yaml')
        if not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            metrics_data = data.get('metrics', {})
            for metric_code, metric_info in metrics_data.items():
                self._metric_configs[metric_code] = MetricConfig(
                    metric_code=metric_code,
                    name_cn=metric_info.get('name_cn', ''),
                    design_value=metric_info.get('design_value', 0.0),
                    min_value=metric_info.get('min_value', 0.0),
                    max_value=metric_info.get('max_value', 0.0),
                    unit=metric_info.get('unit', '')
                )
        except Exception as e:
            pass
    
    def get_metric_config(self, metric_code: str) -> Optional[MetricConfig]:
        """
        获取指标配置

        Args:
            metric_code: 指标代码

        Returns:
            指标配置对象，如果不存在返回None
        """
        return self._metric_configs.get(metric_code)
    
    def get_all_metric_configs(self) -> Dict[str, MetricConfig]:
        """
        获取所有指标配置

        Returns:
            指标配置字典
        """
        return self._metric_configs.copy()


_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """
    获取全局配置管理器单例

    Returns:
        配置管理器
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
