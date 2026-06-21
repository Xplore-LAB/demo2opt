from src.services.data_loader import ExcelDataLoader


def test_quality_gate_filters_missing_duplicate_and_abnormal_sampling():
    loader = ExcelDataLoader("dummy.xlsx")
    records = [
        {"tag_id": "A", "name": "A", "value": 10.0, "timestamp": "2026-03-10T10:00:00"},
        {"tag_id": "A", "name": "A", "value": 10.1, "timestamp": "2026-03-10T10:00:00"},  # duplicate
        {"tag_id": "A", "name": "A", "value": 10.2, "timestamp": "2026-03-10T10:01:00"},
        {"tag_id": "A", "name": "A", "value": 10.3, "timestamp": "2026-03-10T10:02:00"},
        {"tag_id": "A", "name": "A", "value": 9.0, "timestamp": "2026-03-11T10:00:00"},  # extreme jump
        {"tag_id": "A", "name": "A", "value": 8.9, "timestamp": ""},  # missing timestamp
    ]

    result = loader.apply_quality_gate(records)
    gate = result["gate"]

    assert gate["status"] == "WARNING"
    assert gate["input_count"] == 6
    assert gate["filtered_missing"] == 1
    assert gate["filtered_duplicates"] == 1
    assert gate["filtered_abnormal_sampling"] == 1
    assert gate["output_count"] == 3
    assert len(result["records"]) == 3
