"""
配置管理模块单元测试
"""
import pytest
import os
import tempfile

from src.config import ConfigManager, MetricConfig, get_config_manager


def create_test_config_file(file_path: str):
    """创建测试用的配置文件"""
    content = """version: v1
description: 测试配置
metrics:
  TestMetric1:
    name_cn: 测试指标1
    design_value: 100.0
    min_value: 0.0
    max_value: 200.0
    unit: kW
  TestMetric2:
    name_cn: 测试指标2
    design_value: 50.0
    min_value: 10.0
    max_value: 100.0
    unit: ratio
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


class TestConfigManager:
    """测试ConfigManager"""
    
    def test_load_config_success(self):
        """测试成功加载配置"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "metric_design_values.yaml")
            create_test_config_file(config_path)
            
            manager = ConfigManager(config_dir=temp_dir)
            
            metric1 = manager.get_metric_config("TestMetric1")
            assert metric1 is not None
            assert metric1.metric_code == "TestMetric1"
            assert metric1.name_cn == "测试指标1"
            assert metric1.design_value == 100.0
            assert metric1.min_value == 0.0
            assert metric1.max_value == 200.0
            assert metric1.unit == "kW"
    
    def test_get_nonexistent_metric(self):
        """测试获取不存在的指标"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "metric_design_values.yaml")
            create_test_config_file(config_path)
            
            manager = ConfigManager(config_dir=temp_dir)
            metric = manager.get_metric_config("NonExistentMetric")
            assert metric is None
    
    def test_get_all_metrics(self):
        """测试获取所有指标"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "metric_design_values.yaml")
            create_test_config_file(config_path)
            
            manager = ConfigManager(config_dir=temp_dir)
            all_metrics = manager.get_all_metric_configs()
            
            assert len(all_metrics) == 2
            assert "TestMetric1" in all_metrics
            assert "TestMetric2" in all_metrics
    
    def test_config_file_not_exists(self):
        """测试配置文件不存在的情况"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(config_dir=temp_dir)
            all_metrics = manager.get_all_metric_configs()
            assert len(all_metrics) == 0


class TestGetConfigManager:
    """测试get_config_manager单例"""
    
    def test_singleton(self):
        """测试单例模式"""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        assert manager1 is manager2


class TestMetricConfig:
    """测试MetricConfig数据类"""
    
    def test_create_metric_config(self):
        """测试创建MetricConfig"""
        metric = MetricConfig(
            metric_code="Test",
            name_cn="测试",
            design_value=100.0,
            min_value=0.0,
            max_value=200.0,
            unit="kW"
        )
        
        assert metric.metric_code == "Test"
        assert metric.name_cn == "测试"
        assert metric.design_value == 100.0
        assert metric.min_value == 0.0
        assert metric.max_value == 200.0
        assert metric.unit == "kW"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
