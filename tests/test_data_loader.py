import pandas as pd
import pytest
from unittest.mock import patch
from pathlib import Path


class TestExcelDataLoader:
    @patch("pandas.read_excel")
    def test_load_valid_tall_excel(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame(
            {
                "timestamp": ["2024-01-01 10:00:00", "2024-01-01 10:01:00"],
                "tag_id": ["T001", "T002"],
                "name": ["主换冷损", "空压机负荷"],
                "value": [100.0, 200.0],
                "unit": ["℃", "kPa"],
            }
        )

        from src.services.data_loader import ExcelDataLoader

        result = ExcelDataLoader("test.xlsx").load_and_standardize()

        assert len(result["records"]) == 2
        assert result["records"][0]["tag_id"] == "T001"
        assert result["records"][0]["unit"] == "℃"
        assert result["parsing_audit"]["layout_detected"] == "tall_table"
        assert result["parsing_audit"]["data_start_row"] == 0

    @patch("pandas.read_excel")
    def test_load_wide_table_keeps_first_real_timestamp(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame(
            [
                ["指标名称", "膨胀机A制冷量", "膨胀机B制冷量"],
                ["2025-01-01", 101.0, 201.0],
                ["2025-01-02", 102.0, 202.0],
            ],
            columns=["timestamp", "T001", "T002"],
        )

        from src.services.data_loader import ExcelDataLoader

        result = ExcelDataLoader("test.xlsx").load_and_standardize()

        timestamps = sorted({row["timestamp"] for row in result["records"]})
        assert len(result["records"]) == 4
        assert timestamps == ["2025-01-01", "2025-01-02"]
        assert result["parsing_audit"]["layout_detected"] == "wide_table"
        assert result["parsing_audit"]["descriptor_row"] == 0
        assert result["parsing_audit"]["design_ref_row"] is None
        assert result["parsing_audit"]["data_start_row"] == 1
        assert result["parsing_audit"]["timepoint_count_after_gate"] == 2

    @patch("pandas.read_excel")
    def test_load_wide_table_detects_design_ref_row(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame(
            [
                ["指标名称", "主换冷损", "液氩产量"],
                ["design_ref", 70.0, 45.0],
                ["2025-01-01", 92.0, 39.5],
                ["2025-01-02", 88.0, 40.0],
            ],
            columns=["timestamp", "T001", "T002"],
        )

        from src.services.data_loader import ExcelDataLoader

        result = ExcelDataLoader("test.xlsx").load_and_standardize()

        assert len(result["records"]) == 4
        assert min(row["timestamp"] for row in result["records"]) == "2025-01-01"
        assert {row["design_ref"] for row in result["records"] if row["tag_id"] == "T001"} == {70.0}
        assert {row["design_ref"] for row in result["records"] if row["tag_id"] == "T002"} == {45.0}
        assert result["parsing_audit"]["descriptor_row"] == 0
        assert result["parsing_audit"]["design_ref_row"] == 1
        assert result["parsing_audit"]["data_start_row"] == 2

    def test_load_repo_sample_keeps_first_day_and_expected_counts(self):
        from src.services.data_loader import ExcelDataLoader

        sample_path = next(Path("data").glob("*.xlsx"))
        result = ExcelDataLoader(str(sample_path)).load_and_standardize()

        timestamps = {row["timestamp"] for row in result["records"]}
        assert len(result["records"]) == 3685
        assert len(timestamps) == 335
        assert "2025-01-01 00:00:00" in timestamps
        assert result["parsing_audit"]["data_start_row"] == 1
        assert result["parsing_audit"]["design_ref_row"] is None
        assert result["parsing_audit"]["timepoint_count_after_gate"] == 335
        assert result["parsing_audit"]["record_count_after_gate"] == 3685

    def test_load_nonexistent_file(self):
        from src.services.data_loader import ExcelDataLoader

        with pytest.raises(Exception):
            ExcelDataLoader("nonexistent.xlsx").load_and_standardize()

    @patch("pandas.read_excel")
    def test_quality_gate_empty_data(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame()

        from src.services.data_loader import ExcelDataLoader

        result = ExcelDataLoader("test.xlsx").load_and_standardize()

        assert result["records"] == []
        assert result["quality_gate"]["status"] == "FAIL"
        assert result["parsing_audit"]["layout_detected"] == "empty_or_invalid"


class TestASUDataLoader:
    @patch("src.services.data_loader.ASUPipelineService")
    def test_load_asu_data(self, mock_pipeline):
        mock_pipeline.return_value.load_and_process.return_value = {
            "facts": pd.DataFrame({"tag_code": ["T001"], "value": [100.0]}),
            "derived": pd.DataFrame({"metric_code": ["M001"], "value": [50.0]}),
            "quality": {"n_points": 10},
        }

        from src.services.data_loader import ASUDataLoader

        loader = ASUDataLoader()
        result = loader.load_asu_data("test.xlsx")

        assert "facts" in result
        assert "derived" in result
        mock_pipeline.return_value.load_and_process.assert_called_once_with("test.xlsx", None)
