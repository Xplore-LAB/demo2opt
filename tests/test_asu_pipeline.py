"""
ASU管道单元测试
"""
import pytest
import pandas as pd
import os
import tempfile
from datetime import datetime

from src.services.asu_pipeline import (
    ASUExcelReader,
    DerivedMetricsEngine,
    ASUPipelineService,
    ReadResult,
    DerivedResult
)


def create_test_excel(file_path: str):
    """创建测试用的Excel文件"""
    import pandas as pd
    from openpyxl import Workbook
    
    wb = Workbook()
    ws = wb.active
    
    ws.append(["", "Pump1_Loss_kW", "Pump2_Loss_kW", "ExpA_Cold_kW", "ExpB_Cold_kW", "HX_Loss_kW", "ColdBox_Loss_kW"])
    ws.append(["", "1号泵冷损", "2号泵冷损", "膨胀机A冷量", "膨胀机B冷量", "主换冷损", "冷箱冷损"])
    
    base_time = datetime(2026, 2, 14, 10, 0)
    for i in range(10):
        time_str = (base_time + pd.Timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        ws.append([
            time_str,
            20.0 + i * 0.5,
            25.0 + i * 0.3,
            500.0 + i * 2,
            500.0 + i * 1.5,
            30.0 + i * 0.4,
            40.0 + i * 0.6
        ])
    
    wb.save(file_path)


def create_test_data_dictionary(file_path: str):
    """创建测试用的数据字典"""
    content = """tag_code,unified_field,tag_name_cn,unit,kpi_role
Pump1_Loss_kW,Pump1_Loss_kW,1号泵冷损,kW,loss
Pump2_Loss_kW,Pump2_Loss_kW,2号泵冷损,kW,loss
ExpA_Cold_kW,ExpA_Cold_kW,膨胀机A冷量,kW,cold
ExpB_Cold_kW,ExpB_Cold_kW,膨胀机B冷量,kW,cold
HX_Loss_kW,HX_Loss_kW,主换冷损,kW,loss
ColdBox_Loss_kW,ColdBox_Loss_kW,冷箱冷损,kW,loss
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def create_test_derived_metrics(file_path: str):
    """创建测试用的衍生指标配置"""
    content = """version: v1
assumptions:
  test: true
metrics:
- metric_code: Pump_Loss_kW
  name_cn: 低温泵冷损
  unit: kW
  type: derived
  formula: Pump1_Loss_kW + Pump2_Loss_kW
  inputs:
  - Pump1_Loss_kW
  - Pump2_Loss_kW
  quality:
    missing_policy: any_missing->missing
    range_check: value>=0
- metric_code: ExpanderCold_kW
  name_cn: 膨胀机制冷量合计
  unit: kW
  type: derived
  formula: ExpA_Cold_kW + ExpB_Cold_kW
  inputs:
  - ExpA_Cold_kW
  - ExpB_Cold_kW
  quality:
    missing_policy: any_missing->missing
    range_check: value>=0
- metric_code: TotalColdLoss_kW
  name_cn: 综合冷损
  unit: kW
  type: derived
  formula: HX_Loss_kW + ColdBox_Loss_kW + Pump_Loss_kW
  inputs:
  - HX_Loss_kW
  - ColdBox_Loss_kW
  - Pump_Loss_kW
  quality:
    missing_policy: any_missing->missing
    range_check: value>=0
- metric_code: ColdLossRatio
  name_cn: 冷损占比
  unit: ratio
  type: derived
  formula: TotalColdLoss_kW / ExpanderCold_kW
  inputs:
  - TotalColdLoss_kW
  - ExpanderCold_kW
  quality:
    missing_policy: any_missing->missing
    div0_policy: denom<=eps->missing+flag:DIV0
    eps: 1.0e-06
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


class TestASUExcelReader:
    """测试ASUExcelReader"""
    
    def test_read_success(self):
        """测试读取Excel成功"""
        with tempfile.TemporaryDirectory() as temp_dir:
            excel_path = os.path.join(temp_dir, "test.xlsx")
            dict_path = os.path.join(temp_dir, "data_dictionary.csv")
            
            create_test_excel(excel_path)
            create_test_data_dictionary(dict_path)
            
            reader = ASUExcelReader()
            result = reader.read(excel_path, dict_path)
            
            assert isinstance(result, ReadResult)
            assert result.facts is not None
            assert result.meta is not None
            assert len(result.facts) > 0
            assert len(result.meta) > 0
    
    def test_read_missing_tags(self):
        """测试读取缺少标签的情况"""
        with tempfile.TemporaryDirectory() as temp_dir:
            excel_path = os.path.join(temp_dir, "test.xlsx")
            dict_path = os.path.join(temp_dir, "data_dictionary.csv")
            
            create_test_excel(excel_path)
            
            with open(dict_path, 'w', encoding='utf-8') as f:
                f.write("tag_code,unified_field,tag_name_cn,unit,kpi_role\n")
            
            reader = ASUExcelReader()
            with pytest.raises(ValueError):
                reader.read(excel_path, dict_path)


class TestDerivedMetricsEngine:
    """测试DerivedMetricsEngine"""
    
    def test_compute_derived_metrics(self):
        """测试计算衍生指标"""
        with tempfile.TemporaryDirectory() as temp_dir:
            excel_path = os.path.join(temp_dir, "test.xlsx")
            dict_path = os.path.join(temp_dir, "data_dictionary.csv")
            derived_path = os.path.join(temp_dir, "derived_metrics.yaml")
            
            create_test_excel(excel_path)
            create_test_data_dictionary(dict_path)
            create_test_derived_metrics(derived_path)
            
            reader = ASUExcelReader()
            read_result = reader.read(excel_path, dict_path)
            
            engine = DerivedMetricsEngine(derived_path)
            derived_result = engine.compute(read_result.facts)
            
            assert isinstance(derived_result, DerivedResult)
            assert derived_result.derived is not None
            assert len(derived_result.derived) > 0
            
            metric_codes = derived_result.derived['metric_code'].unique()
            expected_metrics = ['Pump_Loss_kW', 'ExpanderCold_kW', 'TotalColdLoss_kW', 'ColdLossRatio']
            for metric in expected_metrics:
                assert metric in metric_codes


class TestASUPipelineService:
    """测试ASUPipelineService"""
    
    def test_load_and_process(self):
        """测试完整管道"""
        with tempfile.TemporaryDirectory() as temp_dir:
            excel_path = os.path.join(temp_dir, "test.xlsx")
            dict_path = os.path.join(temp_dir, "data_dictionary.csv")
            derived_path = os.path.join(temp_dir, "derived_metrics.yaml")
            
            create_test_excel(excel_path)
            create_test_data_dictionary(dict_path)
            create_test_derived_metrics(derived_path)
            
            service = ASUPipelineService(derived_yaml=derived_path)
            result = service.load_and_process(excel_path, dict_path)
            
            assert 'facts' in result
            assert 'meta' in result
            assert 'derived' in result
            assert 'quality' in result
            
            assert len(result['facts']) > 0
            assert len(result['derived']) > 0
    
    def test_get_available_metrics(self):
        """测试获取可用指标"""
        with tempfile.TemporaryDirectory() as temp_dir:
            derived_path = os.path.join(temp_dir, "derived_metrics.yaml")
            create_test_derived_metrics(derived_path)
            
            service = ASUPipelineService(derived_yaml=derived_path)
            metrics = service.get_available_metrics()
            
            assert len(metrics) == 4
            assert 'Pump_Loss_kW' in metrics
            assert 'ExpanderCold_kW' in metrics
    
    def test_get_metric_info(self):
        """测试获取指标信息"""
        with tempfile.TemporaryDirectory() as temp_dir:
            derived_path = os.path.join(temp_dir, "derived_metrics.yaml")
            create_test_derived_metrics(derived_path)
            
            service = ASUPipelineService(derived_yaml=derived_path)
            metric_info = service.get_metric_info('Pump_Loss_kW')
            
            assert metric_info is not None
            assert metric_info['metric_code'] == 'Pump_Loss_kW'
            assert metric_info['name_cn'] == '低温泵冷损'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
