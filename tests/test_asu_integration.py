"""
Test script for ASU pipeline integration
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.asu_pipeline import ASUPipelineService, ASUExcelReader, DerivedMetricsEngine
from src.services.data_loader import ASUDataLoader
from src.services.data_semantics import DataSemanticsService
from src.schemas import ASUFactModel, ASUDerivedResultModel


def test_asu_pipeline_service():
    """Test ASU pipeline service"""
    print("=" * 60)
    print("Testing ASUPipelineService")
    print("=" * 60)

    try:
        service = ASUPipelineService()
        
        available_metrics = service.get_available_metrics()
        print(f"Available metrics: {available_metrics}")
        
        for metric in available_metrics:
            info = service.get_metric_info(metric)
            print(f"  {metric}: {info['name_cn']} ({info['unit']})")
        
        print("✓ ASUPipelineService test passed")
        return True
    except Exception as e:
        print(f"✗ ASUPipelineService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_asu_data_loader():
    """Test ASU data loader"""
    print("\n" + "=" * 60)
    print("Testing ASUDataLoader")
    print("=" * 60)

    excel_path = os.path.join(os.path.dirname(__file__), "..", "data", "【原始数据】运行诊断.xlsx")
    
    if not os.path.exists(excel_path):
        print(f"Test file not found: {excel_path}")
        return False

    try:
        loader = ASUDataLoader()
        
        result = loader.load_asu_data(excel_path)
        
        print(f"Facts shape: {result['facts'].shape}")
        print(f"Meta shape: {result['meta'].shape}")
        print(f"Derived shape: {result['derived'].shape}")
        print(f"Quality info: {result['quality']}")
        
        if not result['facts'].empty:
            print(f"Sample fact: {result['facts'].iloc[0].to_dict()}")
        
        if not result['derived'].empty:
            print(f"Sample derived: {result['derived'].iloc[0].to_dict()}")
        
        print("✓ ASUDataLoader test passed")
        return True
    except Exception as e:
        print(f"✗ ASUDataLoader test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_semantics_integration():
    """Test data semantics integration with ASU"""
    print("\n" + "=" * 60)
    print("Testing DataSemanticsService integration")
    print("=" * 60)

    try:
        service = DataSemanticsService()
        
        test_derived_data = [
            ASUDerivedResultModel(
                time="2024-01-01 00:00:00",
                metric_code="Pump_Loss_kW",
                value=45.0,
                quality_flags=None
            ),
            ASUDerivedResultModel(
                time="2024-01-01 00:00:00",
                metric_code="ExpanderCold_kW",
                value=1050.0,
                quality_flags=None
            ),
            ASUDerivedResultModel(
                time="2024-01-01 00:00:00",
                metric_code="TotalColdLoss_kW",
                value=180.0,
                quality_flags=None
            ),
            ASUDerivedResultModel(
                time="2024-01-01 00:00:00",
                metric_code="ColdLossRatio",
                value=0.17,
                quality_flags=None
            )
        ]
        
        semantic_vector = service.process_asu_derived_metrics(test_derived_data)
        
        print(f"Processed {len(semantic_vector)} derived metrics")
        for item in semantic_vector:
            print(f"  {item['name']}: {item['state_desc']} (值: {item['current_value']}, 隶属度: {item['membership_degree']})")
        
        print("✓ DataSemanticsService integration test passed")
        return True
    except Exception as e:
        print(f"✗ DataSemanticsService integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_end_to_end():
    """Test end-to-end integration"""
    print("\n" + "=" * 60)
    print("Testing End-to-End Integration")
    print("=" * 60)

    excel_path = os.path.join(os.path.dirname(__file__), "..", "data", "【原始数据】运行诊断.xlsx")
    
    if not os.path.exists(excel_path):
        print(f"Test file not found: {excel_path}")
        return False

    try:
        loader = ASUDataLoader()
        semantics_service = DataSemanticsService()
        
        result = loader.load_asu_data(excel_path)
        
        if result['derived'].empty:
            print("No derived data available for semantic analysis")
            return True
        
        derived_dicts = result['derived'].to_dict('records')
        derived_models = []
        for d in derived_dicts:
            try:
                model = ASUDerivedResultModel(**d)
                derived_models.append(model)
            except Exception as e:
                print(f"Warning: Failed to create model for {d}: {e}")
        
        if derived_models:
            semantic_vector = semantics_service.process_asu_derived_metrics(derived_models)
            print(f"Semantic analysis completed for {len(semantic_vector)} metrics")
            
            for item in semantic_vector[:5]:
                print(f"  {item['name']}: {item['state_desc']} (值: {item['current_value']})")
        
        print("✓ End-to-end integration test passed")
        return True
    except Exception as e:
        print(f"✗ End-to-end integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    results = []
    
    results.append(("ASUPipelineService", test_asu_pipeline_service()))
    results.append(("ASUDataLoader", test_asu_data_loader()))
    results.append(("DataSemanticsService Integration", test_data_semantics_integration()))
    results.append(("End-to-End Integration", test_end_to_end()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    
    sys.exit(0 if all_passed else 1)
