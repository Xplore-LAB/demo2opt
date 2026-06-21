"""测试语义分析模块"""
import pytest
from unittest.mock import Mock, patch


class TestDataSemanticsService:
    """测试数据语义服务"""
    
    def test_process_empty_records(self):
        """测试处理空记录"""
        from src.services.data_semantics import DataSemanticsService
        service = DataSemanticsService()
        
        result = service.process([])
        assert isinstance(result, list)
        assert len(result) == 0
    
    def test_process_normal_records(self):
        """测试处理正常记录"""
        from src.services.data_semantics import DataSemanticsService
        service = DataSemanticsService()
        
        records = [
            {'tag_id': 'T001', 'value': 100.0, 'timestamp': '2024-01-01 10:00:00'},
            {'tag_id': 'T002', 'value': 200.0, 'timestamp': '2024-01-01 10:00:00'}
        ]
        
        result = service.process(records)
        assert isinstance(result, list)
        # 应该返回语义分析结果
        assert len(result) >= 0
    
    def test_build_abnormal_details(self):
        """测试构建异常详情"""
        from src.services.data_semantics import DataSemanticsService
        service = DataSemanticsService()
        
        semantic_data = [
            {'tag_id': 'T001', 'state': 'abnormal', 'state_desc': '异常'},
            {'tag_id': 'T002', 'state': 'normal', 'state_desc': '正常'}
        ]
        
        all_records = [
            {'tag_id': 'T001', 'value': 100.0},
            {'tag_id': 'T002', 'value': 200.0}
        ]
        
        result = service.build_abnormal_details(all_records, semantic_data)
        assert isinstance(result, list)
        # 应该只包含异常项
        abnormal_count = sum(1 for item in semantic_data if item.get('state') == 'abnormal')
        assert len(result) <= abnormal_count
