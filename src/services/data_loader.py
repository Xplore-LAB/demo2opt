import pandas as pd
from typing import Any, List, Dict, Optional, Tuple
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from src.schemas.models import SensorDataModel, validate_sensor_data, ASUFactModel, validate_asu_facts
from .asu_pipeline import ASUPipelineService


class ExcelDataLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            ts = pd.to_datetime(text, errors="coerce")
            if pd.isna(ts):
                return None
            return ts.to_pydatetime()
        except Exception:
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _is_tall_layout(self, df: pd.DataFrame) -> bool:
        lowered = {str(col).strip().lower() for col in df.columns}
        has_time = any(name in lowered for name in {"timestamp", "time"})
        has_tag = any(name in lowered for name in {"tag_id", "tag_code"})
        has_value = "value" in lowered
        return has_time and has_tag and has_value

    def _is_descriptor_row(self, row: pd.Series, sensor_cols: List[Any], time_col: Any) -> bool:
        if not sensor_cols:
            return False
        time_value = row.get(time_col)
        if self._parse_timestamp(time_value) is not None:
            return False
        text_count = 0
        numeric_count = 0
        for col in sensor_cols:
            value = row.get(col)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if self._safe_float(value) is not None:
                numeric_count += 1
            else:
                text_count += 1
        return text_count > 0 and text_count >= max(1, len(sensor_cols) // 2) and numeric_count == 0

    def _is_design_ref_row(self, row: pd.Series, sensor_cols: List[Any], time_col: Any) -> bool:
        if not sensor_cols:
            return False
        time_value = row.get(time_col)
        if self._parse_timestamp(time_value) is not None:
            return False
        numeric_count = 0
        non_empty_count = 0
        for col in sensor_cols:
            value = row.get(col)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            non_empty_count += 1
            if self._safe_float(value) is not None:
                numeric_count += 1
        return non_empty_count > 0 and numeric_count >= max(1, int(len(sensor_cols) * 0.8))

    def _empty_result(self, *, reason: str, quality_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gate = {
            "status": "FAIL",
            "input_count": 0,
            "output_count": 0,
            "filtered_total": 0,
            "filtered_missing": 0,
            "filtered_duplicates": 0,
            "filtered_abnormal_sampling": 0,
            "pass_rate": 0.0,
            "sampling_rules": {
                "non_positive_interval": 0,
                "extreme_interval_jump": 0,
                "interval_jump_ratio_threshold": 20.0,
            },
        }
        return {
            "records": [],
            "raw_records": [],
            "quality": quality_report or {"status": "FAIL"},
            "quality_gate": gate,
            "parsing_audit": {
                "layout_detected": "empty_or_invalid",
                "data_start_row": None,
                "design_ref_row": None,
                "dropped_rows": [],
                "first_included_timestamp": None,
                "last_included_timestamp": None,
                "count_change_reason": reason,
            },
        }

    def _parse_tall_table(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        lowered = {str(col).strip().lower(): col for col in df.columns}
        time_col = lowered.get("timestamp") or lowered.get("time")
        tag_col = lowered.get("tag_id") or lowered.get("tag_code")
        value_col = lowered.get("value")
        name_col = lowered.get("name") or lowered.get("tag_name_cn")
        unit_col = lowered.get("unit")
        design_ref_col = lowered.get("design_ref")

        standardized_data: List[Dict[str, Any]] = []
        invalid_rows = 0
        for _, row in df.iterrows():
            timestamp = row.get(time_col)
            value_float = self._safe_float(row.get(value_col))
            tag_id = str(row.get(tag_col) or "").strip()
            if not tag_id or timestamp is None or value_float is None:
                invalid_rows += 1
                continue
            standardized_data.append(
                {
                    "tag_id": tag_id,
                    "name": str(row.get(name_col) or tag_id),
                    "value": value_float,
                    "unit": str(row.get(unit_col) or ""),
                    "design_ref": self._safe_float(row.get(design_ref_col)) if design_ref_col else None,
                    "timestamp": str(timestamp),
                }
            )

        timestamps = [item["timestamp"] for item in standardized_data]
        parsing_audit = {
            "layout_detected": "tall_table",
            "descriptor_row": None,
            "data_start_row": 0,
            "design_ref_row": None,
            "dropped_rows": ([{"row_index": "dynamic", "reason": f"invalid_tall_rows={invalid_rows}"}] if invalid_rows else []),
            "first_included_timestamp": min(timestamps) if timestamps else None,
            "last_included_timestamp": max(timestamps) if timestamps else None,
            "count_change_reason": "输入被识别为行式数据表，逐行读取 timestamp/tag/value 字段；未使用额外设计参考值行。",
        }
        return standardized_data, parsing_audit

    def _parse_wide_table(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        time_col = df.columns[0]
        sensor_cols = list(df.columns[1:])
        descriptor_row = 0 if df.shape[0] > 0 and self._is_descriptor_row(df.iloc[0], sensor_cols, time_col) else None
        design_ref_row = None
        candidate_design_ref_row = (descriptor_row + 1) if descriptor_row is not None else 0
        if candidate_design_ref_row < df.shape[0] and self._is_design_ref_row(df.iloc[candidate_design_ref_row], sensor_cols, time_col):
            design_ref_row = candidate_design_ref_row

        data_start_row = 0
        if design_ref_row is not None:
            data_start_row = design_ref_row + 1
        elif descriptor_row is not None:
            data_start_row = descriptor_row + 1

        name_map = {
            str(sensor_col): (
                str(df.at[descriptor_row, sensor_col])
                if descriptor_row is not None and pd.notna(df.at[descriptor_row, sensor_col])
                else str(sensor_col)
            )
            for sensor_col in sensor_cols
        }
        design_ref_map = {
            str(sensor_col): (
                self._safe_float(df.at[design_ref_row, sensor_col])
                if design_ref_row is not None
                else None
            )
            for sensor_col in sensor_cols
        }

        standardized_data: List[Dict[str, Any]] = []
        invalid_cells = 0
        for row_idx in range(data_start_row, df.shape[0]):
            timestamp = df.at[row_idx, time_col]
            if pd.isna(timestamp):
                invalid_cells += len(sensor_cols)
                continue
            for sensor_col in sensor_cols:
                value_float = self._safe_float(df.at[row_idx, sensor_col])
                if value_float is None:
                    invalid_cells += 1
                    continue
                standardized_data.append(
                    {
                        "tag_id": str(sensor_col),
                        "name": name_map[str(sensor_col)],
                        "value": value_float,
                        "unit": "",
                        "design_ref": design_ref_map[str(sensor_col)],
                        "timestamp": str(timestamp),
                    }
                )

        dropped_rows: List[Dict[str, Any]] = []
        if descriptor_row is not None:
            dropped_rows.append({"row_index": descriptor_row, "reason": "descriptor_row"})
        if design_ref_row is not None:
            dropped_rows.append({"row_index": design_ref_row, "reason": "design_ref_row"})
        if invalid_cells > 0:
            dropped_rows.append({"row_index": "dynamic", "reason": f"invalid_cells={invalid_cells}"})

        timestamps = [item["timestamp"] for item in standardized_data]
        if design_ref_row is not None:
            count_change_reason = (
                f"当前样本识别为宽表：第 {descriptor_row} 行为指标名称，第 {design_ref_row} 行为设计参考值，"
                f"第 {data_start_row} 行开始为真实数据。"
            )
        elif descriptor_row is not None:
            count_change_reason = (
                f"当前样本识别为宽表：第 {descriptor_row} 行为指标名称，第 {data_start_row} 行开始为真实数据；"
                "未识别独立设计参考值行，因此纳入首个真实时间点。"
            )
        else:
            count_change_reason = "当前样本识别为宽表，未命中说明行或设计参考值行，按首行开始读取真实数据。"

        parsing_audit = {
            "layout_detected": "wide_table",
            "descriptor_row": descriptor_row,
            "data_start_row": data_start_row,
            "design_ref_row": design_ref_row,
            "dropped_rows": dropped_rows,
            "first_included_timestamp": min(timestamps) if timestamps else None,
            "last_included_timestamp": max(timestamps) if timestamps else None,
            "count_change_reason": count_change_reason,
        }
        return standardized_data, parsing_audit

    def check_data_quality(self, df: pd.DataFrame) -> Dict:
        """
        S2 数据质量校验
        执行质量门禁：缺失率统计、常量序列识别、异常值检查
        """
        quality_report = {
            "missing_rates": {},
            "constant_columns": [],
            "outliers": {},
            "status": "PASS"
        }
        
        # 缺失率统计
        missing_series = df.isnull().mean()
        quality_report["missing_rates"] = missing_series[missing_series > 0].to_dict()
        
        # 常量序列识别 (标准差为0)
        numeric_df = df.select_dtypes(include=['number'])
        std_series = numeric_df.std()
        quality_report["constant_columns"] = std_series[std_series == 0].index.tolist()
        
        # 简单异常值检查 (Z-score > 3)
        for col in numeric_df.columns:
            z_scores = (numeric_df[col] - numeric_df[col].mean()) / numeric_df[col].std()
            outliers_count = (z_scores.abs() > 3).sum()
            if outliers_count > 0:
                quality_report["outliers"][col] = int(outliers_count)
                
        # 判定
        if len(quality_report["missing_rates"]) > 0 or len(quality_report["constant_columns"]) > 0:
            quality_report["status"] = "WARNING"
            
        return quality_report

    def apply_quality_gate(self, records: List[Dict]) -> Dict[str, Any]:
        """
        S2 数据质量门禁（可执行过滤）
        - 过滤缺失关键字段
        - 过滤重复采样（tag_id + timestamp）
        - 过滤明显异常采样节拍（同一tag下时间倒退或极端跳点）
        """
        input_count = len(records or [])
        cleaned: List[Dict] = []
        filtered_missing = 0

        for row in records or []:
            if not row.get("tag_id") or row.get("timestamp") in (None, ""):
                filtered_missing += 1
                continue
            if row.get("value") is None:
                filtered_missing += 1
                continue
            cleaned.append(row)

        deduped: List[Dict] = []
        seen = set()
        filtered_duplicates = 0
        for row in cleaned:
            key = (str(row.get("tag_id")), str(row.get("timestamp")))
            if key in seen:
                filtered_duplicates += 1
                continue
            seen.add(key)
            deduped.append(row)

        grouped: Dict[str, List[Dict]] = {}
        for row in deduped:
            grouped.setdefault(str(row.get("tag_id")), []).append(row)

        abnormal_keys = set()
        abnormal_sampling_rules = {
            "non_positive_interval": 0,
            "extreme_interval_jump": 0,
        }
        interval_jump_ratio_threshold = 20.0

        for tag_id, rows in grouped.items():
            parsed_rows = []
            for row in rows:
                ts = self._parse_timestamp(str(row.get("timestamp", "")))
                if ts is None:
                    continue
                parsed_rows.append((ts, row))
            if len(parsed_rows) < 4:
                continue

            parsed_rows.sort(key=lambda x: x[0])
            intervals = []
            for idx in range(1, len(parsed_rows)):
                delta = (parsed_rows[idx][0] - parsed_rows[idx - 1][0]).total_seconds()
                if delta > 0:
                    intervals.append(delta)

            if not intervals:
                continue

            median_interval = float(pd.Series(intervals).median())
            if median_interval <= 0:
                continue

            for idx in range(1, len(parsed_rows)):
                prev_ts = parsed_rows[idx - 1][0]
                curr_ts, curr_row = parsed_rows[idx]
                delta = (curr_ts - prev_ts).total_seconds()
                if delta <= 0:
                    abnormal_keys.add((tag_id, str(curr_row.get("timestamp"))))
                    abnormal_sampling_rules["non_positive_interval"] += 1
                    continue
                if delta > median_interval * interval_jump_ratio_threshold:
                    abnormal_keys.add((tag_id, str(curr_row.get("timestamp"))))
                    abnormal_sampling_rules["extreme_interval_jump"] += 1

        gated_records: List[Dict] = []
        filtered_abnormal_sampling = 0
        for row in deduped:
            key = (str(row.get("tag_id")), str(row.get("timestamp")))
            if key in abnormal_keys:
                filtered_abnormal_sampling += 1
                continue
            gated_records.append(row)

        filtered_total = filtered_missing + filtered_duplicates + filtered_abnormal_sampling
        pass_rate = (len(gated_records) / input_count) if input_count else 0.0
        gate_status = "PASS"
        if len(gated_records) == 0:
            gate_status = "FAIL"
        elif filtered_total > 0:
            gate_status = "WARNING"

        gate_report = {
            "status": gate_status,
            "input_count": input_count,
            "output_count": len(gated_records),
            "filtered_total": filtered_total,
            "filtered_missing": filtered_missing,
            "filtered_duplicates": filtered_duplicates,
            "filtered_abnormal_sampling": filtered_abnormal_sampling,
            "pass_rate": round(pass_rate, 4),
            "sampling_rules": {
                **abnormal_sampling_rules,
                "interval_jump_ratio_threshold": interval_jump_ratio_threshold,
            },
        }
        return {"records": gated_records, "gate": gate_report}

    def load_and_standardize(self) -> Dict:
        """
        S1 数据接入与标准化
        读取Excel并转换为标准语义字典列表，同时返回质量报告
        """
        if not self.file_path:
            raise ValueError("文件路径不能为空")

        if not self.file_path.endswith(('.xlsx', '.xls')):
            raise ValueError("仅支持 .xlsx, .xls 格式")

        df = pd.read_excel(self.file_path)

        # 执行 S2 数据质量校验
        quality_report = self.check_data_quality(df)
        if df.empty or df.shape[1] < 2:
            return self._empty_result(
                reason="Excel文件至少需要包含时间列和一个传感器列。",
                quality_report=quality_report,
            )

        if self._is_tall_layout(df):
            standardized_data, parsing_audit = self._parse_tall_table(df)
        else:
            standardized_data, parsing_audit = self._parse_wide_table(df)

        validated_data = validate_sensor_data(standardized_data)
        validated_records = [item.model_dump() for item in validated_data]
        gate_result = self.apply_quality_gate(validated_records)
        gate_records = gate_result["records"]
        gated_timestamps = [str(item.get("timestamp")) for item in gate_records if item.get("timestamp")]
        parsing_audit["first_included_timestamp"] = min(gated_timestamps) if gated_timestamps else parsing_audit.get("first_included_timestamp")
        parsing_audit["last_included_timestamp"] = max(gated_timestamps) if gated_timestamps else parsing_audit.get("last_included_timestamp")
        parsing_audit["record_count_before_gate"] = len(validated_records)
        parsing_audit["record_count_after_gate"] = len(gate_records)
        parsing_audit["timepoint_count_before_gate"] = len({str(item.get('timestamp')) for item in validated_records if item.get("timestamp")})
        parsing_audit["timepoint_count_after_gate"] = len(set(gated_timestamps))
        parsing_audit["sensor_count"] = len({str(item.get('tag_id')) for item in gate_records if item.get("tag_id")})

        # 返回包含数据、质量报告与门禁结果的字典
        return {
            "records": gate_records,
            "raw_records": validated_records,
            "quality": quality_report,
            "quality_gate": gate_result["gate"],
            "parsing_audit": parsing_audit,
        }


class ASUDataLoader:
    def __init__(self, derived_yaml: Optional[str] = None):
        self.pipeline_service = ASUPipelineService(derived_yaml)

    def load_asu_data(self, excel_path: str, data_dictionary_csv: Optional[str] = None) -> Dict:
        """
        使用ASU管道加载和处理数据

        参数:
            excel_path: Excel文件路径
            data_dictionary_csv: 数据字典CSV文件路径（可选，默认为data/data_dictionary.csv）

        返回:
            包含facts, meta, derived, quality的字典
        """
        return self.pipeline_service.load_and_process(excel_path, data_dictionary_csv)

    def get_available_metrics(self) -> List[str]:
        """获取可用的衍生指标列表"""
        return self.pipeline_service.get_available_metrics()

    def get_metric_info(self, metric_code: str) -> Optional[Dict]:
        """获取指定指标的详细信息"""
        return self.pipeline_service.get_metric_info(metric_code)


def test_data_loader():
    """
    测试数据加载器模块
    """
    import os
    print("="*60)
    print("测试 ExcelDataLoader 模块")
    print("="*60)
    
    test_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "【原始数据】运行诊断.xlsx")
    if not os.path.exists(test_file):
        print(f"测试文件不存在: {test_file}")
        return False
    
    try:
        loader = ExcelDataLoader(test_file)
        result = loader.load_and_standardize()
        data = result["records"]
        quality = result["quality"]
        
        print(f"✓ 成功加载 {len(data)} 条数据")
        print(f"  质量检查: {quality['status']}")
        if data:
            print(f"  示例数据: {data[0]}")
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_data_loader()
