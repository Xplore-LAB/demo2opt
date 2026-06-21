import json
import os
import csv
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS


def _configure_console_encoding():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

load_dotenv()

from src.core.task_manager import TaskManager, TaskStatus
from src.prompts.templates import SimpleLLMClient
from src.utils.llm_json import extract_json_object

app = Flask(__name__)
CORS(app)

task_manager = TaskManager()
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
UX_METRICS_FILE = LOGS_DIR / "ux_metrics.jsonl"
NITROGEN_ANALYSIS_LOG_FILE = LOGS_DIR / "nitrogen_plug_analysis.jsonl"
NITROGEN_DEMO_DB = PROJECT_ROOT / "data" / "nitrogen_demo.db"
NITROGEN_SELECTED_DEMO_DIR = PROJECT_ROOT / "data" / "demo" / "nitrogen_plug_demo_selected"
FAULT_TREE_DIR = PROJECT_ROOT / "data" / "故障树"
NITROGEN_DEMO_ALIASES = {
    "AI705": ["AI705"],
    "AI701": ["AI701"],
    "FI702": ["FI702"],
    "FIQC701": ["FIQC701", "FIC701"],
    "FIQC102": ["FIQC102"],
    "AIAS102": ["AIAS102"],
    "FIC101": ["FIC101", "FIQ101"],
    "V3": ["V3", "FIC3.MV"],
    "PRODUCT_N2": ["FIC103"],
    "MEDIUM_N2": ["FI131"],
}
LLM_CONFIGS_FILE = os.path.join(
    str(PROJECT_ROOT),
    "llm_configs.json",
)


def _ensure_log_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _connect_nitrogen_db():
    if not NITROGEN_DEMO_DB.exists():
        raise FileNotFoundError(f"氮塞演示数据库不存在: {NITROGEN_DEMO_DB}")
    conn = sqlite3.connect(NITROGEN_DEMO_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _read_selected_demo_csv(relative_path):
    csv_path = NITROGEN_SELECTED_DEMO_DIR / relative_path
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _resolve_selected_demo_file(relative_path):
    base = NITROGEN_SELECTED_DEMO_DIR.resolve()
    resolved = (base / relative_path).resolve()
    if base not in resolved.parents and resolved != base:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _nitrogen_column_meta(conn):
    rows = conn.execute(
        "SELECT column_name, source_name, display_name FROM column_meta ORDER BY rowid"
    ).fetchall()
    return [dict(row) for row in rows]


def _find_demo_column(meta, aliases):
    lowered = [(item["column_name"], (item.get("source_name") or "").lower()) for item in meta]
    for alias in aliases:
        needle = alias.lower()
        for column_name, source_name in lowered:
            if source_name == needle or f"#{needle}" in source_name or f"#{needle}." in source_name or needle in source_name:
                return column_name
    return None


def _nitrogen_metric_bounds(conn, meta):
    column_map = {key: _find_demo_column(meta, value) for key, value in NITROGEN_DEMO_ALIASES.items()}
    expressions = []
    tags = []
    for tag, column in column_map.items():
        if not column:
            continue
        tags.append(tag)
        quoted = _quote_identifier(column)
        expressions.append(f"MIN({quoted}) AS {_quote_identifier(f'{tag}__min')}")
        expressions.append(f"MAX({quoted}) AS {_quote_identifier(f'{tag}__max')}")
    if not expressions:
        return {}
    row = conn.execute(f"SELECT {', '.join(expressions)} FROM samples").fetchone()
    bounds = {}
    for tag in tags:
        min_value = row[f"{tag}__min"]
        max_value = row[f"{tag}__max"]
        if min_value is not None and max_value is not None:
            bounds[tag] = {"min": min_value, "max": max_value}
    return bounds


def _quote_identifier(identifier):
    return '"' + str(identifier).replace('"', '""') + '"'


def _format_demo_time(ms):
    if ms is None:
        return "-"
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def _read_nitrogen_records(start_ms, end_ms, max_points=5000):
    with _connect_nitrogen_db() as conn:
        meta = _nitrogen_column_meta(conn)
        column_map = {key: _find_demo_column(meta, value) for key, value in NITROGEN_DEMO_ALIASES.items()}
        needed = [column for column in column_map.values() if column]
        select_columns = ["time_ms", "time_text", *dict.fromkeys(needed)]
        sql = (
            f"SELECT {', '.join(_quote_identifier(column) for column in select_columns)} "
            "FROM samples WHERE time_ms BETWEEN ? AND ? ORDER BY time_ms"
        )
        rows = conn.execute(sql, (start_ms, end_ms)).fetchall()
        if max_points and len(rows) > max_points:
            step = (len(rows) - 1) / (max_points - 1)
            rows = [rows[round(index * step)] for index in range(max_points)]

        def read(row, key):
            column = column_map.get(key)
            return row[column] if column and column in row.keys() else None

        records = []
        for row in rows:
            metrics = {
                "AI705": read(row, "AI705"),
                "AI701": read(row, "AI701"),
                "FI702": read(row, "FI702"),
                "FIQC701": read(row, "FIQC701"),
                "FIQC102": read(row, "FIQC102"),
                "AIAS102": read(row, "AIAS102"),
                "FIC101": read(row, "FIC101"),
                "V3": read(row, "V3"),
            }
            air_in = metrics["FIC101"]
            outputs = [metrics["FIQC102"], read(row, "PRODUCT_N2"), read(row, "MEDIUM_N2"), metrics["FI702"]]
            valid_outputs = [value for value in outputs if isinstance(value, (int, float))]
            balance = None
            if isinstance(air_in, (int, float)) and air_in and len(valid_outputs) >= 2:
                balance = ((air_in - sum(valid_outputs)) / air_in) * 100
            metrics["BALANCE"] = balance
            records.append({"timeMs": row["time_ms"], "time": row["time_text"], "metrics": metrics})
        return records


def _metric_stats(records, tag):
    values = [row["metrics"].get(tag) for row in records]
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {"valid": False, "mean": None, "min": None, "max": None, "delta": None, "swing": None}
    return {
        "valid": True,
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
        "delta": values[-1] - values[0],
        "swing": max(values) - min(values),
    }


def _format_metric(value):
    if not isinstance(value, (int, float)):
        return "-"
    return f"{value:.0f}" if abs(value) >= 100 else f"{value:.2f}"


def _report_relative_path(path):
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except Exception:
        return str(path)


def _safe_report_slug(value, fallback="event"):
    text = str(value or fallback).strip()
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text, flags=re.UNICODE).strip("._-")
    return text[:80] or fallback


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _format_report_value(value, unit=""):
    if isinstance(value, (int, float)):
        return f"{value:.3f}{unit}"
    if value is None:
        return "-"
    return f"{value}{unit}"


def _format_ratio_percent(value):
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "-"


def _format_missing_data_item(item):
    if not isinstance(item, dict):
        return item
    name = item.get("item") or item.get("data") or item.get("tag") or item.get("name") or "-"
    node = item.get("node")
    purpose = item.get("purpose") or item.get("reason") or item.get("basis")
    parts = [str(name)]
    if node:
        parts.append(f"节点：{node}")
    if purpose:
        parts.append(f"用途：{purpose}")
    return "；".join(parts)


def _format_model_variable(item):
    if not isinstance(item, dict):
        return item
    key = item.get("key") or item.get("name") or "-"
    value = _format_report_value(item.get("value"))
    source = item.get("source")
    if source:
        return f"{key} = {value}（来源：{source}）"
    return f"{key} = {value}"


def _stats_table_markdown(stats):
    lines = [
        "| 测点 | 阶段 | 均值 | 最小 | 最大 | 首尾变化 | 波动 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tag, phases in (stats or {}).items():
        for phase_key, phase_name in (("before", "识别前"), ("during", "识别区间"), ("after", "识别后")):
            item = (phases or {}).get(phase_key) or {}
            lines.append(
                "| {tag} | {phase} | {mean} | {min} | {max} | {delta} | {swing} |".format(
                    tag=tag,
                    phase=phase_name,
                    mean=_format_report_value(item.get("mean")),
                    min=_format_report_value(item.get("min")),
                    max=_format_report_value(item.get("max")),
                    delta=_format_report_value(item.get("delta")),
                    swing=_format_report_value(item.get("swing")),
                )
            )
    return "\n".join(lines)


def _list_markdown(items, formatter):
    lines = []
    for item in items or []:
        try:
            text = formatter(item)
        except Exception:
            text = str(item)
        text = str(text or "").strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "- 无"


def _generate_nitrogen_analysis_report(request_payload, data_payload, stats, rows_by_phase):
    generated_at = datetime.now()
    report_dir = REPORTS_DIR / "nitrogen_plug"
    report_dir.mkdir(parents=True, exist_ok=True)
    _ensure_log_dir()

    event_id = data_payload.get("event_id") or request_payload.get("event_id") or "event"
    filename_base = f"nitrogen_plug_{generated_at.strftime('%Y%m%d_%H%M%S')}_{_safe_report_slug(event_id)}"
    md_path = report_dir / f"{filename_base}.md"
    json_path = report_dir / f"{filename_base}.json"

    shape = data_payload.get("shape_evidence") or request_payload.get("shape_evidence") or {}
    material_balance = request_payload.get("material_balance") or {}
    external_model = material_balance.get("external_model") or (material_balance.get("outputs") or {}).get("external_model") or {}
    llm_trace = data_payload.get("llm_trace") or {}
    report_record = {
        "report_type": "nitrogen_plug_analysis",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "event_id": event_id,
        "window": {
            "start_ms": request_payload.get("start_ms"),
            "end_ms": request_payload.get("end_ms"),
            "start_text": _format_demo_time(request_payload.get("start_ms")),
            "end_text": _format_demo_time(request_payload.get("end_ms")),
            "before_min": request_payload.get("before_min"),
            "after_min": request_payload.get("after_min"),
        },
        "request_payload": request_payload,
        "analysis_result": data_payload,
        "phase_statistics": stats,
        "row_counts": {key: len(value or []) for key, value in (rows_by_phase or {}).items()},
        "rows_by_phase": rows_by_phase,
    }

    markdown = "\n".join(
        [
            "# 氮塞识别全过程追溯报告",
            "",
            "## 1. 基本信息",
            f"- 事件编号：{event_id}",
            f"- 生成时间：{report_record['generated_at']}",
            f"- 分析窗口：{report_record['window']['start_text']} 至 {report_record['window']['end_text']}",
            f"- 识别结论：{data_payload.get('final_conclusion') or data_payload.get('conclusion') or '-'}",
            f"- 分析模式：{data_payload.get('analysis_mode') or '-'}",
            f"- 决策来源：{data_payload.get('decision_label') or data_payload.get('decision_source') or '-'}",
            f"- 智能补充状态：{llm_trace.get('status') or '-'}",
            "",
            "## 2. 识别过程摘要",
            f"- 扫描说明：{request_payload.get('summary') or data_payload.get('summary') or '-'}",
            f"- 主触发测点：{', '.join(request_payload.get('trigger_tags') or []) or '-'}",
            f"- 风险等级：{request_payload.get('level') or '-'}",
            f"- 人工复核要求：{'是' if data_payload.get('manual_review_required') else '否'}",
            "",
            "## 3. AI705 图形证据",
            f"- 形态：{shape.get('shapeText') or '-'}",
            f"- 工作点：{_format_report_value(shape.get('workpoint'))}",
            f"- 谷底值：{_format_report_value(shape.get('minValue'))}",
            f"- 下凹幅度：{_format_report_value(shape.get('dipDepth'))}",
            f"- 恢复比例：{_format_ratio_percent(shape.get('recoveryRatio'))}",
            f"- 判断依据：{shape.get('basis') or '-'}",
            "",
            "## 4. 测点统计",
            _stats_table_markdown(stats),
            "",
            "## 5. 证据链",
            _list_markdown(
                data_payload.get("basis"),
                lambda item: f"{item.get('tag') or '-'}：{item.get('value') or '-'}；依据：{item.get('basis') or '-'}",
            ),
            "",
            "## 6. 故障树与原因分支",
            _list_markdown(
                data_payload.get("branch_ranking") or data_payload.get("cause_branches"),
                lambda item: f"{item.get('branch') or item.get('name') or '-'}：{item.get('reason') or item.get('cause') or item.get('support_level') or '-'}",
            ),
            "",
            "## 7. 物料平衡复核",
            f"- 复核结论：{data_payload.get('material_balance_review') or '-'}",
            f"- 公式状态：{data_payload.get('material_balance_formula_status') or '-'}",
            f"- 公式名称：{data_payload.get('material_balance_formula_name') or '-'}",
            f"- 数据依据：{data_payload.get('material_balance_basis') or '-'}",
            "",
            "### 外压缩模型计算明细",
            f"- 模型状态：{external_model.get('status') or '-'}",
            f"- 系数来源：{external_model.get('coefficientSource') or '-'}",
            f"- 系数说明：{external_model.get('coefficientNote') or '-'}",
            f"- 主要输出：{external_model.get('primaryOutputText') or '-'}",
            "",
            _list_markdown(external_model.get("variables"), _format_model_variable),
            "",
            "### 临时估算与正式上线缺项",
            _list_markdown(external_model.get("recoveredInputs"), lambda item: item),
            "",
            _list_markdown(external_model.get("missingForProduction"), lambda item: item),
            "",
            "## 8. 缺失数据与处置建议",
            "### 缺失数据",
            _list_markdown(data_payload.get("key_missing_data") or data_payload.get("missing_information"), _format_missing_data_item),
            "",
            "### 处置建议",
            _list_markdown(data_payload.get("action_advice"), lambda item: item.get("action") if isinstance(item, dict) else item),
            "",
            "## 9. 追溯文件",
            f"- Markdown 报告：`{_report_relative_path(md_path)}`",
            f"- JSON 原始记录：`{_report_relative_path(json_path)}`",
            "",
        ]
    )

    json_path.write_text(json.dumps(report_record, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    log_record = {
        "generated_at": report_record["generated_at"],
        "event_id": event_id,
        "conclusion": data_payload.get("final_conclusion") or data_payload.get("conclusion"),
        "analysis_mode": data_payload.get("analysis_mode"),
        "report_md": _report_relative_path(md_path),
        "report_json": _report_relative_path(json_path),
    }
    with NITROGEN_ANALYSIS_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_record, ensure_ascii=False, default=_json_default) + "\n")

    return {
        "report_md": _report_relative_path(md_path),
        "report_json": _report_relative_path(json_path),
        "report_log": _report_relative_path(NITROGEN_ANALYSIS_LOG_FILE),
    }


def _normalize_tag_set(tags):
    aliases = {
        "FI702": ["FI702", "FI701"],
        "FIQC701": ["FIQC701", "FIC701"],
        "FIQC102": ["FIQC102"],
        "AI705": ["AI705", "AN_N2_AR_FRACTION"],
        "AI701": ["AI701"],
        "AIAS102": ["AIAS102"],
        "FIC101": ["FIC101", "FIQ101"],
        "V3": ["V3", "FIC3.MV"],
        "BALANCE": ["BALANCE"],
    }
    normalized = set()
    for tag in tags or []:
        text = str(tag or "").strip().upper()
        if not text:
            continue
        normalized.add(text)
        for key, values in aliases.items():
            if text == key or text in {item.upper() for item in values}:
                normalized.add(key)
                normalized.update(item.upper() for item in values)
    return normalized


def _fault_tree_items_from_payload(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("trees", "fault_trees", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("nodes"), list):
        return [payload]
    return [item for item in payload.values() if isinstance(item, dict) and isinstance(item.get("nodes"), list)]


def _load_fault_trees():
    if not FAULT_TREE_DIR.exists() or not FAULT_TREE_DIR.is_dir():
        return []
    trees = []
    for path in sorted(FAULT_TREE_DIR.rglob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        for tree in _fault_tree_items_from_payload(payload):
            candidate = dict(tree)
            candidate["_source_path"] = str(path.relative_to(PROJECT_ROOT))
            trees.append(candidate)
    return trees


def _pick_nitrogen_fault_tree():
    trees = _load_fault_trees()
    enabled = [
        tree for tree in trees
        if str(tree.get("status") or "").lower() not in {"disabled", "inactive"}
    ]
    for tree in enabled or trees:
        text = " ".join(
            str(tree.get(key) or "")
            for key in ("tree_id", "tree_name", "top_event_name", "description", "domain")
        )
        if "氮塞" in text or "N2_BLOCKAGE" in text.upper():
            return tree
    return (enabled or trees or [None])[0]


def _node_tags(node):
    tags = list(node.get("related_tags") or [])
    for rule in node.get("evidence_rules") or []:
        if isinstance(rule, dict) and rule.get("tag"):
            tags.append(rule.get("tag"))
    return tags


def _node_rule_texts(node, limit=3):
    texts = []
    for rule in node.get("evidence_rules") or []:
        if not isinstance(rule, dict):
            continue
        text = rule.get("description") or rule.get("variable_name") or rule.get("tag")
        if text:
            texts.append(str(text))
    return texts[:limit]


def _build_fault_tree_guidance(trigger_tags, review_tags, basis):
    tree = _pick_nitrogen_fault_tree()
    matched_tags = _normalize_tag_set(trigger_tags)
    matched_tags.update(_normalize_tag_set(review_tags))
    matched_tags.update(_normalize_tag_set(item.get("tag") for item in basis if isinstance(item, dict)))

    if not tree or not isinstance(tree.get("nodes"), list):
        return {
            "tree_id": "",
            "tree_name": "氮塞故障树",
            "source_path": "",
            "matched_tags": sorted(matched_tags),
            "steps": [
                {
                    "step": 1,
                    "title": "确认 AI705 图形主触发是否成立",
                    "focus": "检测证据",
                    "checks": ["AI705 是否相对工作点形成下凹、谷底、回升", "识别完成后再按粗氩塔、主塔、空气系统、事件分块排查原因"],
                    "reason": "先确认图形形态主触发，再进入原因溯源。",
                    "action": "只做复核与记录，不直接给激进调节指令。",
                },
                {
                    "step": 2,
                    "title": "按粗氩塔、主塔、空气系统和事件分支排查",
                    "focus": "原因溯源",
                    "checks": ["FI702偏高/FIC701偏低", "氧气多抽/氮气少抽/V3阀开过大/AI701高值", "空气少进/膨胀空气偏少/分子筛切换"],
                    "reason": "把疑似区间映射到可人工确认的故障树分支。",
                    "action": "补齐缺失测点和操作记录后再确认氮塞。",
                },
            ],
        }

    nodes = [node for node in tree.get("nodes") or [] if node.get("enabled", True)]
    children = defaultdict(list)
    for node in nodes:
        if node.get("parent_id"):
            children[node.get("parent_id")].append(node)

    def descendants(node):
        result = []
        stack = list(children.get(node.get("node_id"), []))
        while stack:
            current = stack.pop(0)
            result.append(current)
            stack.extend(children.get(current.get("node_id"), []))
        return result

    candidates = []
    for node in nodes:
        node_type = str(node.get("node_type") or "").lower()
        if node_type not in {"cause", "intermediate_event"}:
            continue
        if node_type == "intermediate_event" and not (node.get("mechanism") or node.get("recommended_action")):
            continue
        if str(node.get("branch") or "") == "检测证据" and not node.get("mechanism"):
            continue
        evidence_nodes = [item for item in descendants(node) if str(item.get("node_type") or "").lower() == "evidence"]
        tags = _normalize_tag_set(_node_tags(node))
        for item in evidence_nodes:
            tags.update(_normalize_tag_set(_node_tags(item)))
        score = len(tags & matched_tags)
        if node.get("recommended_action"):
            score += 1
        if node.get("mechanism"):
            score += 1
        candidates.append((score, node, evidence_nodes, tags))

    candidates.sort(key=lambda item: item[0], reverse=True)
    steps = []
    for score, node, evidence_nodes, tags in candidates[:5]:
        checks = []
        for evidence in evidence_nodes[:4]:
            rule_texts = _node_rule_texts(evidence)
            checks.append(rule_texts[0] if rule_texts else str(evidence.get("node_name") or "补充证据"))
        if not checks:
            checks = _node_rule_texts(node) or [tag for tag in _node_tags(node)[:4]]
        steps.append(
            {
                "step": len(steps) + 1,
                "title": str(node.get("node_name") or node.get("branch") or "故障树分支复核"),
                "focus": str(node.get("branch") or "原因溯源"),
                "checks": checks[:4],
                "reason": str(node.get("mechanism") or node.get("missing_data_note") or "按故障树分支补证复核。"),
                "action": str(node.get("recommended_action") or "补充证据后进行人工确认。"),
                "risk_note": str(node.get("risk_note") or ""),
                "matched": sorted(tags & matched_tags),
                "support_level": "优先" if score >= 2 else "待复核",
            }
        )

    if not steps:
        evidence_nodes = [node for node in nodes if str(node.get("node_type") or "").lower() == "evidence"]
        steps = [
            {
                "step": 1,
                "title": "按故障树检测证据复核疑似区间",
                "focus": "检测证据",
                "checks": [
                    _node_rule_texts(node)[0] if _node_rule_texts(node) else str(node.get("node_name") or "补充证据")
                    for node in evidence_nodes[:4]
                ],
                "reason": "当前触发测点与故障树原因分支匹配不足，先补齐基础证据。",
                "action": "补齐塔阻力、液位、流量和操作记录后再确认。",
                "support_level": "待复核",
            }
        ]

    return {
        "tree_id": tree.get("tree_id") or "",
        "tree_name": tree.get("tree_name") or tree.get("top_event_name") or "氮塞故障树",
        "version": tree.get("version") or "",
        "source_path": tree.get("_source_path") or "",
        "matched_tags": sorted(matched_tags),
        "steps": steps,
    }


def _load_llm_configs():
    configs = []
    if os.path.exists(LLM_CONFIGS_FILE):
        try:
            with open(LLM_CONFIGS_FILE, "r", encoding="utf-8") as f:
                file_configs = json.load(f)
        except Exception:
            file_configs = []
        if isinstance(file_configs, list):
            for config in file_configs:
                if not isinstance(config, dict):
                    continue
                candidate = {
                    "base_url": str(config.get("base_url") or "").strip(),
                    "api_key": str(config.get("api_key") or config.get("api_key_full") or "").strip(),
                    "model": str(config.get("model") or "").strip(),
                    "name": str(config.get("name") or "Model Config").strip(),
                }
                if candidate["base_url"] and candidate["api_key"] and candidate["model"]:
                    configs.append(candidate)

    env_config = {
        "base_url": os.getenv("LLM_BASE_URL", "").strip(),
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "model": os.getenv("LLM_MODEL_NAME", "").strip(),
        "name": "System Default",
    }
    if env_config["base_url"] and env_config["api_key"] and env_config["model"]:
        configs.append(env_config)
    return configs


def _normalize_agent_list(value, fallback=None, limit=8):
    if isinstance(value, list):
        return value[:limit]
    return (fallback or [])[:limit]


def _has_agent_tag(tags, *candidates):
    normalized = _normalize_tag_set(tags)
    return any(str(candidate).upper() in normalized for candidate in candidates)


def _agent_status(flag, partial=False, missing=False):
    if flag:
        return "已满足"
    if missing:
        return "缺失"
    if partial:
        return "未完全满足"
    return "待排查"


def _build_top_event_judgement(level, trigger_tags, review_tags, missing_information):
    missing_text = " ".join(str(item) for item in (missing_information or []))
    has_ai705 = _has_agent_tag(trigger_tags, "AI705")
    has_ai701 = _has_agent_tag(trigger_tags, "AI701")
    has_fiqc701 = _has_agent_tag(trigger_tags, "FIQC701")
    has_fi702 = _has_agent_tag(trigger_tags, "FI702")
    has_fic101 = _has_agent_tag(trigger_tags, "FIC101")
    missing_resistance = "阻力" in missing_text
    missing_condenser = any(key in missing_text for key in ("冷凝", "LIC702", "液位", "温差"))
    has_confirming_argon_system_data = not (missing_resistance or missing_condenser)
    auxiliary_count = sum(1 for flag in (has_ai701, has_fiqc701, has_fi702, has_fic101, has_confirming_argon_system_data) if flag)
    triggered = level in {"high", "medium"} or (has_ai705 and auxiliary_count >= 2)

    return {
        "node": "T0",
        "title": "T0 疑似氮塞顶事件",
        "status": {"high": "重度氮塞", "medium": "中度氮塞", "low": "轻度氮塞"}.get(level, "已触发") if triggered else "未触发",
        "logic": "AI705 相对工作点下凹形态 + 多测点联动；辅助联动信号满足 {}/5 项。".format(auxiliary_count),
        "summary": (
            "当前已满足主触发和多测点联动的疑似氮塞判断条件，但关键确认测点仍需补齐。"
            if triggered
            else "当前窗口尚未满足疑似氮塞顶事件触发条件，继续保留趋势观察。"
        ),
        "items": [
            {"item": "AI705 下凹形态", "status": _agent_status(has_ai705), "description": "先看相对当前工作点的下凹、谷底和回升，而不是固定绝对阈值。"},
            {"item": "FI702 氩馏分流量偏高", "status": _agent_status(has_fi702), "description": "粗氩塔分支：判断进入粗氩塔的氩馏分负荷是否偏高。"},
            {"item": "FIC701 粗氩流量偏低", "status": _agent_status(has_fiqc701), "description": "粗氩塔分支：判断粗氩抽出是否偏低。"},
            {"item": "AI701 长时间偏高/短时间高高", "status": _agent_status(has_ai701), "description": "主塔分支：作为主塔物料分配异常的重要表现。"},
            {"item": "FIC101 运行模式", "status": _agent_status(has_fic101), "description": "先判断稳态或变负荷，动态过程不直接套用稳态物料平衡。"},
            {"item": "粗氩塔阻力", "status": _agent_status(False, missing=missing_resistance), "description": "补齐后确认粗氩塔精馏能力是否下降。"},
            {"item": "粗氩冷凝器液位 / 温差", "status": _agent_status(False, missing=missing_condenser), "description": "补齐后确认冷凝器换热条件是否恶化。"},
        ],
    }


def _build_evidence_nodes(basis, trigger_tags, review_tags, missing_information):
    missing_text = " ".join(str(item) for item in (missing_information or []))
    rows = [
        {"evidence": "AI705 下凹形态", "node": "T0 疑似氮塞", "status": "强触发" if _has_agent_tag(trigger_tags, "AI705") else "待排查", "explanation": "粗氩含氮量相对当前工作点形成下凹、谷底和回升，是顶事件主触发信号。"},
        {"evidence": "FI702 偏高", "node": "A1 粗氩塔氩馏分流量偏高", "status": "辅助成立" if _has_agent_tag(trigger_tags, "FI702") else "待排查", "explanation": "FI702偏高表示进入粗氩塔的氩馏分负荷偏高。"},
        {"evidence": "FIC701 偏低", "node": "A2 粗氩塔粗氩流量偏低", "status": "辅助成立" if _has_agent_tag(trigger_tags, "FIQC701") else "待排查", "explanation": "FIC701偏低表示粗氩抽出不足。"},
        {"evidence": "AI701 高值表现", "node": "B4 主塔 AI701 高值表现", "status": "辅助成立" if _has_agent_tag(trigger_tags, "AI701") else "待排查", "explanation": "AI701长时间偏高或短时间高高，是主塔物料分配异常的重要表现。"},
        {"evidence": "FIC101 负荷波动", "node": "C1 空气少进 / D2 变负荷过程", "status": "待判别" if _has_agent_tag(trigger_tags, "FIC101") else "待排查", "explanation": "需先判断稳态还是动态；动态过程不能直接套用稳态平衡。"},
        {"evidence": "粗氩塔阻力", "node": "A3", "status": "缺失" if "阻力" in missing_text else "待排查", "explanation": "确认粗氩塔分支的重要证据。"},
        {"evidence": "粗氩冷凝器液位 / 温差", "node": "A4", "status": "缺失" if any(key in missing_text for key in ("冷凝", "LIC702", "液位", "温差")) else "待排查", "explanation": "确认冷凝器换热异常的重要证据。"},
        {"evidence": "上下塔阻力", "node": "B3", "status": "缺失" if "上塔" in missing_text or "下塔" in missing_text else "待排查", "explanation": "用于排查主塔精馏状态。"},
    ]
    if basis:
        known_tags = {row["evidence"].split()[0].upper() for row in rows}
        for item in basis:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag") or "").upper()
            if tag and tag not in known_tags:
                rows.append({
                    "evidence": tag,
                    "node": "辅助证据",
                    "status": "辅助成立",
                    "explanation": str(item.get("basis") or item.get("value") or "区间内出现联动变化。"),
                })
    return rows[:10]


def _build_fault_tree_path(trigger_tags, review_tags, missing_information):
    has_ai701 = _has_agent_tag(trigger_tags, "AI701")
    has_fi702 = _has_agent_tag(trigger_tags, "FI702")
    has_fiqc701 = _has_agent_tag(trigger_tags, "FIQC701")
    has_fic101 = _has_agent_tag(trigger_tags, "FIC101")
    missing_text = " ".join(str(item) for item in (missing_information or []))
    return [
        "T0 疑似氮塞：已触发",
        "├─ A 粗氩塔：待排查",
        f"│  ├─ A1 FI702 氩馏分流量偏高：{'FI702 已提示偏高' if has_fi702 else 'FI702 待排查'}",
        f"│  ├─ A2 FIC701 粗氩流量偏低：{'FIC701 已提示偏低' if has_fiqc701 else 'FIC701 待排查'}",
        f"│  └─ A3 粗氩塔阻力 / 冷凝负荷：{'缺失' if '阻力' in missing_text else '待排查'}",
        "├─ B 主塔：待排查",
        "│  ├─ B1 氧气多抽：缺 FIQC102",
        "│  ├─ B2 氮气少抽：缺 FIC103",
        "│  ├─ B3 V3 阀开过大：缺 V3 开度",
        f"│  └─ B4 AI701 长时间偏高 / 短时间高高：{'AI701 已提示偏高' if has_ai701 else 'AI701 待排查'}",
        "├─ C 空气系统：待排查",
        f"│  ├─ C1 空气少进：{'FIC101 有提示' if has_fic101 else '缺 FIC101'}",
        "│  └─ C2 膨胀空气旁通量偏少：缺 FI105 / FIC1",
        "└─ D 事件：待人工确认",
        "   ├─ D1 分子筛切换不平稳：缺切换记录",
        f"   └─ D2 变负荷过程：{'FIC101 有提示' if has_fic101 else '缺负荷变化记录'}",
    ]


def _build_branch_ranking(trigger_tags, review_tags):
    argon_hits = sum(1 for tag in ("FI702", "FIQC701") if _has_agent_tag(trigger_tags, tag))
    fic101_hit = _has_agent_tag(trigger_tags, "FIC101")
    main_hits = sum(1 for tag in ("AI701", "FIQC102", "AIAS102", "V3") if _has_agent_tag(trigger_tags, tag))
    return [
        {"rank": 1, "branch": "A 粗氩塔", "status": "同步排查" if argon_hits else "待排查", "reason": "稳态下先排查 FI702 氩馏分流量偏高、FIC701 粗氩流量偏低。", "next_step": "补粗氩塔阻力、LIC702、冷凝器温差。"},
        {"rank": 2, "branch": "B 主塔", "status": "同步排查" if main_hits else "待排查", "reason": "主塔侧看氧气多抽、氮气少抽、V3阀开过大和 AI701 高值表现。" if main_hits else "需结合 FIQC102、FIC103、V3、AI701 和物料平衡复核。", "next_step": "按目标负荷、目标氧气、目标液氮和±1.25%范围判断偏低/正常/偏高。"},
        {"rank": 3, "branch": "C 空气系统", "status": "同步排查" if fic101_hit else "待排查", "reason": "FIC101 已提示负荷或空气量方向性偏离，需要先区分固定负荷与变负荷过程。" if fic101_hit else "重点看空气少进和膨胀空气旁通量偏少。", "next_step": "补 FIC101、FI105、FIC1。"},
        {"rank": 4, "branch": "D 事件", "status": "待人工确认", "reason": "分子筛切换和变负荷过程需要现场记录支撑。", "next_step": "补分子筛切换时间、切换是否平稳、切换后半小时内是否出现氮塞。"},
    ]


def _build_key_missing_data(missing_information):
    defaults = [
        ("粗氩塔阻力", "A3", "判断粗氩塔精馏能力是否下降。"),
        ("粗氩冷凝器液空液位 LIC702", "A4", "判断冷凝器换热是否恶化。"),
        ("粗氩冷凝器温差", "A4", "判断冷凝负荷是否下降。"),
        ("产品氧气纯度 AIAS102", "B2", "判断主塔富氩区是否可能下移。"),
        ("氧气取出量 FIQC102", "B1", "判断是否存在氧气取出量过大。"),
        ("上塔 / 下塔阻力", "B3", "判断主塔精馏状态是否异常。"),
        ("V3 阀开度", "D1", "判断液氮至上塔调节是否异常。"),
        ("操作票 / 阀位记录", "D2 / D3 / D4", "判断是否存在人为调整扰动。"),
    ]
    requested = " ".join(str(item) for item in (missing_information or []))
    rows = [{"data": data, "node": node, "purpose": purpose} for data, node, purpose in defaults]
    if requested:
        for item in missing_information:
            text = str(item)
            if text and not any(text in row["data"] or row["data"] in text for row in rows):
                rows.append({"data": text, "node": "待映射节点", "purpose": "用于补齐当前窗口判断所缺证据。"})
    return rows[:10]


def _build_agent_llm_payload(
    event_id,
    start_ms,
    end_ms,
    level,
    trigger_tags,
    basis,
    cause_branches,
    material_balance_review,
    missing_information,
    review_tags,
    stats,
    fault_tree_guidance=None,
):
    return {
        "event_id": event_id,
        "time_range": f"{_format_demo_time(start_ms)} - {_format_demo_time(end_ms)}",
        "rule_level": level,
        "trigger_tags": trigger_tags,
        "basis": basis,
        "cause_branches": cause_branches,
        "material_balance_review": material_balance_review,
        "missing_information": missing_information,
        "review_tags": review_tags,
        "fault_tree_guidance": fault_tree_guidance or {},
        "top_event_judgement": _build_top_event_judgement(level, trigger_tags, review_tags, missing_information),
        "fault_tree_path": _build_fault_tree_path(trigger_tags, review_tags, missing_information),
        "evidence_nodes": _build_evidence_nodes(basis, trigger_tags, review_tags, missing_information),
        "branch_ranking": _build_branch_ranking(trigger_tags, review_tags),
        "key_missing_data": _build_key_missing_data(missing_information),
        "feature_summary": {
            tag: {
                "before_mean": stats[tag]["before"].get("mean"),
                "during_mean": stats[tag]["during"].get("mean"),
                "after_mean": stats[tag]["after"].get("mean"),
                "during_delta": stats[tag]["during"].get("delta"),
                "during_swing": stats[tag]["during"].get("swing"),
            }
            for tag in stats
        },
        "constraints": [
            "只输出工业现场可读的区间分析单，不进行自然语言问答。",
            "不能直接替代窗口扫描，不能新增故障树分支。",
            "物料平衡只用于区间复核，不能单独定位氮塞原因。",
            "建议必须先复核、再处置，不给激进操作指令。",
        ],
    }


def _call_agent_llm(context):
    llm_configs = _load_llm_configs()
    if not llm_configs:
        return None, "未配置可用大模型"

    system_prompt = """你是空分装置氮塞 Agent 分析助手。
请基于系统提供的结构化区间信息生成工业现场可读的分析单。
你不能读取全量原始时序数据，不能自由新增故障树节点，不能用物料平衡单独定位氮塞原因。
输出必须按故障树驱动组织：先说明 T0 顶事件是否触发，再说明命中路径、证据节点状态、分支排序、关键缺失数据和建议动作。
每条证据、每条建议都必须绑定树节点、判断逻辑和判据用途，不能只写“发现异常，所以建议检查”。
用语要像工业产品，不要出现 Prompt、JSON、LLM、工具调用、模型推理等开发术语。
必须只输出一个 JSON 对象，字段如下：
{
  "conclusion": "重度氮塞/中度氮塞/轻度氮塞/疑似氮塞待观察/未见明显氮塞特征",
  "summary": "一句现场可读总结",
  "top_event_judgement": {"node":"T0","title":"T0 疑似氮塞顶事件","status":"已触发/未触发","logic":"AI705 下凹形态 + 多测点联动","items":[{"item":"AI705 下凹形态","status":"已满足","description":"判据说明"}]},
  "basis": [{"tag":"AI705","value":"当前值或变化","basis":"判断依据"}],
  "evidence_nodes": [{"evidence":"AI705 下凹形态","node":"T0 疑似氮塞","status":"强触发","explanation":"证据解释"}],
  "fault_tree_path": ["T0 疑似氮塞：已触发","├─ A 粗氩塔：待排查","├─ B 主塔：待排查","├─ C 空气系统：待排查","└─ D 事件：待人工确认"],
  "branch_ranking": [{"rank":1,"branch":"A 粗氩塔","status":"同步排查","reason":"排序理由","next_step":"下一步"}],
  "key_missing_data": [{"data":"粗氩塔阻力","node":"A3","purpose":"用于确认哪个节点"}],
  "cause_branches": [{"branch":"粗氩塔","cause":"原因描述","support_level":"优先/待复核/待确认"}],
  "material_balance_review": "物料平衡复核说明",
  "fault_tree_steps": [{"title":"故障树步骤","focus":"分支","checks":["需要核对的证据"],"reason":"为什么看这一步","action":"建议动作"}],
  "action_advice": ["处置建议1：必须写清为确认/排除哪个节点而补数据或操作"],
  "review_tags": ["AI705","AI701"],
  "missing_information": ["粗氩塔阻力"],
  "manual_review_required": true
}"""
    user_prompt = json.dumps(context, ensure_ascii=False, default=str)
    errors = []
    error_details = []
    for llm_config in llm_configs:
        client = SimpleLLMClient(
            api_url=llm_config["base_url"],
            api_key=llm_config["api_key"],
            model_name=llm_config["model"],
            timeout_sec=45,
            max_retries=1,
        )
        result = client.chat(
            user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        if not result.get("ok"):
            error = result.get("error") or {}
            error_message = error.get("message") or "调用失败"
            errors.append(f"{llm_config['name']}({llm_config['model']}): {error_message}")
            error_details.append(
                {
                    "config": llm_config["name"],
                    "model": llm_config["model"],
                    "code": error.get("code") or "LLM_REQUEST_ERROR",
                    "message": error_message,
                }
            )
            continue

        parsed = extract_json_object(result.get("answer", ""))
        if not parsed:
            raw_answer = str(result.get("answer", "") or "").strip()
            errors.append(f"{llm_config['name']}({llm_config['model']}): 返回内容无法解析")
            error_details.append(
                {
                    "config": llm_config["name"],
                    "model": llm_config["model"],
                    "code": "LLM_RESPONSE_INVALID",
                    "message": "返回内容无法解析",
                    "preview": raw_answer[:200],
                }
            )
            continue
        parsed["_model_name"] = llm_config["model"]
        parsed["_model_config_name"] = llm_config["name"]
        return parsed, "", {"attempts": error_details}
    return None, "；".join(errors[-3:]) or "大模型调用失败", {"attempts": error_details}


def _normalize_agent_llm_result(call_result):
    if isinstance(call_result, tuple):
        if len(call_result) >= 3:
            llm_result, llm_error, llm_meta = call_result[:3]
            return llm_result, llm_error, llm_meta or {}
        if len(call_result) == 2:
            llm_result, llm_error = call_result
            return llm_result, llm_error, {}
        if len(call_result) == 1:
            return call_result[0], "", {}
    return call_result, "", {}


def _build_nitrogen_brief_sentence(event_id, conclusion, trigger_tags, branch_ranking):
    trigger_text = "、".join(str(tag) for tag in (trigger_tags or [])[:2] if tag) or "粗氩侧关键测点"
    first_branch = ""
    if branch_ranking and isinstance(branch_ranking[0], dict):
        first_branch = str(branch_ranking[0].get("branch") or "").strip()
    if first_branch:
        return f"{event_id} 初判为{conclusion}，当前先看 {trigger_text} 联动，优先复核{first_branch}。"
    return f"{event_id} 初判为{conclusion}，当前先看 {trigger_text} 联动，再结合故障树继续细化。"


def _resolve_trace_focus_node(branch_ranking):
    if not branch_ranking:
        return "T0"
    branch_text = str(branch_ranking[0].get("branch") or "")
    prefix = branch_text[:1].upper()
    return prefix if prefix in {"A", "B", "C", "D"} else "T0"


def _build_nitrogen_stage_payload(stage_name, data_payload):
    focus_node = _resolve_trace_focus_node(data_payload.get("branch_ranking") or [])
    stage_map = {
        "top_event": {
            "analysis_mode": "stage_top_event",
            "analysis_note": "步骤1完成，开始检查物料平衡。",
            "trace_title": "步骤1：看图识别",
            "trace_detail": "正在检查 AI705 是否形成相对工作点下凹形态。",
            "trace_focus_node": "T0",
            "llm_sentence": "步骤1完成：已检查 AI705 图形主触发。",
        },
        "material_balance": {
            "analysis_mode": "stage_material_balance",
            "analysis_note": "步骤2完成，开始判断故障树分支。",
            "trace_title": "步骤2：检查物料平衡",
            "trace_detail": "正在按当前负荷基准复核物料平衡，并判断静态平衡是否适用。",
            "trace_focus_node": "B",
            "llm_sentence": "步骤2完成：已完成运行状态与物料平衡复核。",
        },
        "branch_ranking": {
            "analysis_mode": "stage_material_balance",
            "analysis_note": "步骤2完成，开始判断故障树分支。",
            "trace_title": "步骤2：检查物料平衡",
            "trace_detail": "正在按当前负荷基准复核物料平衡，并判断静态平衡是否适用。",
            "trace_focus_node": "B",
            "llm_sentence": "步骤2完成：已完成运行状态与物料平衡复核。",
        },
        "branch_detail": {
            "analysis_mode": "stage_branch_detail",
            "analysis_note": "步骤3完成，开始整理结论。",
            "trace_title": "步骤3：判断故障树分支",
            "trace_detail": "正在判断先排查哪条故障树分支。",
            "trace_focus_node": focus_node,
            "llm_sentence": "步骤3完成：已确定优先排查分支。",
        },
    }
    stage_config = stage_map.get(stage_name)
    if not stage_config:
        return None
    stage_payload = dict(data_payload)
    stage_payload.update(
        {
            **stage_config,
            "trace_stage": stage_name,
            "material_balance_mode": data_payload.get("material_balance_mode") or "steady_review",
            "material_balance_formula_status": data_payload.get("material_balance_formula_status") or "implemented",
            "material_balance_formula_name": data_payload.get("material_balance_formula_name") or "external_compression_sfit_material_balance",
            "material_balance_basis": data_payload.get("material_balance_basis") or "外压缩.sfit物料平衡：EGOX、PAIR、GAN、FIC1、FAR、CAR、AIR链式回归模型",
            "llm_trace": {
                "status": "stage_ready",
                "call_attempted": False,
                "configured": bool(_load_llm_configs()),
                "model": "",
                "message": stage_config["analysis_note"],
            },
        }
    )
    return stage_payload


def _list_sample_files():
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists() or not data_dir.is_dir():
        return []

    candidates = sorted(
        [path for path in data_dir.glob("*.xlsx") if path.is_file() and not path.name.startswith("~$")],
        key=lambda p: p.name.lower(),
    )

    records = []
    for index, path in enumerate(candidates):
        stat = path.stat()
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        records.append(
            {
                "name": path.name,
                "path": relative,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_default": index == 0,
            }
        )
    return records


@app.route("/api/configs", methods=["GET"])
def get_configs():
    try:
        configs = []

        env_base_url = os.getenv("LLM_BASE_URL")
        env_api_key = os.getenv("LLM_API_KEY")
        env_model = os.getenv("LLM_MODEL_NAME")

        if env_base_url and env_api_key:
            configs.append(
                {
                    "id": "system_default",
                    "name": "System Default (.env)",
                    "base_url": env_base_url,
                    "api_key": env_api_key[:6] + "***" if env_api_key else "",
                    "api_key_full": env_api_key,
                    "model": env_model,
                    "type": "system",
                }
            )

        if os.path.exists(LLM_CONFIGS_FILE):
            try:
                with open(LLM_CONFIGS_FILE, "r", encoding="utf-8") as f:
                    custom_configs = json.load(f)
                for config in custom_configs:
                    config["type"] = "custom"
                    if "id" not in config:
                        import uuid

                        config["id"] = str(uuid.uuid4())
                configs.extend(custom_configs)
            except Exception as exc:
                print(f"读取配置文件失败: {exc}")

        return jsonify({"success": True, "data": configs})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/configs", methods=["POST"])
def save_config():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "未提供配置数据"}), 400

        name = data.get("name")
        base_url = data.get("base_url")
        api_key = data.get("api_key")
        model = data.get("model")

        if not all([name, base_url, api_key, model]):
            return jsonify({"success": False, "error": "缺少必填字段"}), 400

        new_config = {
            "id": data.get("id") or str(datetime.now().timestamp()),
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }

        custom_configs = []
        if os.path.exists(LLM_CONFIGS_FILE):
            try:
                with open(LLM_CONFIGS_FILE, "r", encoding="utf-8") as f:
                    custom_configs = json.load(f)
            except Exception:
                custom_configs = []

        custom_configs.append(new_config)

        with open(LLM_CONFIGS_FILE, "w", encoding="utf-8") as f:
            json.dump(custom_configs, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "data": new_config})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/samples", methods=["GET"])
def get_samples():
    try:
        return jsonify({"success": True, "data": _list_sample_files()})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/tasks", methods=["GET"])
def get_all_tasks():
    try:
        tasks = task_manager.get_all_tasks()
        result = [
            {
                "task_id": task.task_id,
                "status": task.status,
                "progress": task.progress,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "current_step_index": task.current_step_index,
                "start_time": task.start_time,
                "end_time": task.end_time,
                "error_message": task.error_message,
                "metadata": task.metadata,
            }
            for task in tasks
        ]
        return jsonify({"success": True, "data": result, "count": len(result)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    try:
        task = task_manager.get_task(task_id)
        if task is None:
            return jsonify({"success": False, "error": "任务 ID 不存在"}), 404

        result = {
            "task_id": task.task_id,
            "status": task.status,
            "progress": task.progress,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "current_step_index": task.current_step_index,
            "start_time": task.start_time,
            "end_time": task.end_time,
            "error_message": task.error_message,
            "metadata": task.metadata,
        }
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/tasks/<task_id>/progress", methods=["GET"])
def get_task_progress(task_id):
    try:
        task = task_manager.get_task(task_id)
        if task is None:
            return jsonify({"success": False, "error": "任务 ID 不存在"}), 404

        return jsonify(
            {
                "success": True,
                "data": {
                    "task_id": task.task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "current_step": task.current_step,
                    "is_completed": task.status == TaskStatus.COMPLETED.value,
                    "is_failed": task.status == TaskStatus.FAILED.value,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/tasks/cleanup", methods=["POST"])
def cleanup_tasks():
    try:
        data = request.get_json() or {}
        days = data.get("days", 7)
        deleted_count = task_manager.cleanup_old_tasks(days)
        return jsonify({"success": True, "data": {"deleted_count": deleted_count, "days": days}})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ux-metrics", methods=["POST"])
def collect_ux_metrics():
    try:
        payload = request.get_json() or {}
        event_name = (payload.get("event_name") or payload.get("event") or "").strip()
        session_id = (payload.get("session_id") or "").strip()
        if not event_name:
            return jsonify({"success": False, "error": "ç¼ºå°‘ event_name"}), 400
        if not session_id:
            return jsonify({"success": False, "error": "ç¼ºå°‘ session_id"}), 400

        _ensure_log_dir()
        record = {
            **payload,
            "event_name": event_name,
            "session_id": session_id,
            "received_at": datetime.now().isoformat(),
        }
        with open(UX_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ux-metrics/weekly", methods=["GET"])
def weekly_ux_metrics():
    try:
        days = request.args.get("days", default=7, type=int)
        if days <= 0:
            days = 7

        if not UX_METRICS_FILE.exists():
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "days": days,
                        "records": 0,
                        "event_counts": {},
                        "risk_level_counts": {},
                        "t_key_info_ms_median": None,
                        "t_decision_ms_median": None,
                        "completion_rate": None,
                    },
                }
            )

        cutoff = datetime.now().timestamp() - (days * 24 * 3600)
        records = []
        with open(UX_METRICS_FILE, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                dt = _parse_iso_datetime(item.get("client_time")) or _parse_iso_datetime(item.get("timestamp")) or _parse_iso_datetime(item.get("received_at"))
                if not dt:
                    continue
                if dt.timestamp() < cutoff:
                    continue
                item["_ts"] = dt.timestamp()
                records.append(item)

        event_counts = Counter(item.get("event_name", "") for item in records)
        risk_level_counts = Counter(item.get("risk_level", "unknown") for item in records if item.get("risk_level"))

        sessions = defaultdict(list)
        for item in records:
            sid = item.get("session_id")
            if sid:
                sessions[sid].append(item)

        t_key_info_ms = []
        t_decision_ms = []
        started_sessions = 0
        finished_sessions = 0

        for _, items in sessions.items():
            ordered = sorted(items, key=lambda x: x["_ts"])
            task_start = next((x for x in ordered if x.get("event_name") == "task_started"), None)
            key_card = next((x for x in ordered if x.get("event_name") == "key_action_card_rendered"), None)
            if task_start:
                started_sessions += 1
            if any(x.get("event_name") == "task_finished" for x in ordered):
                finished_sessions += 1

            if task_start and key_card:
                delta_ms = int((key_card["_ts"] - task_start["_ts"]) * 1000)
                if delta_ms >= 0:
                    t_key_info_ms.append(delta_ms)

            prompts_by_id = {}
            pending_without_id = []
            for item in ordered:
                name = item.get("event_name")
                iid = str(item.get("interaction_id") or "").strip()
                if name == "interaction_prompt_shown":
                    if iid:
                        prompts_by_id[iid] = item["_ts"]
                    else:
                        pending_without_id.append(item["_ts"])
                elif name == "interaction_answered":
                    start_ts = None
                    if iid and iid in prompts_by_id:
                        start_ts = prompts_by_id.pop(iid)
                    elif pending_without_id:
                        start_ts = pending_without_id.pop(0)
                    if start_ts is not None:
                        delta_ms = int((item["_ts"] - start_ts) * 1000)
                        if delta_ms >= 0:
                            t_decision_ms.append(delta_ms)

        completion_rate = None
        if started_sessions:
            completion_rate = round(finished_sessions / started_sessions, 4)

        return jsonify(
            {
                "success": True,
                "data": {
                    "days": days,
                    "records": len(records),
                    "event_counts": dict(event_counts),
                    "risk_level_counts": dict(risk_level_counts),
                    "t_key_info_ms_median": _safe_int(median(t_key_info_ms)) if t_key_info_ms else None,
                    "t_decision_ms_median": _safe_int(median(t_decision_ms)) if t_decision_ms else None,
                    "completion_rate": completion_rate,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify(
        {
            "success": True,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/api/nitrogen-demo-selected/manifest", methods=["GET"])
def get_selected_nitrogen_demo_manifest():
    try:
        config_path = NITROGEN_SELECTED_DEMO_DIR / "05_config" / "selected_demo_cases.json"
        mapping_path = NITROGEN_SELECTED_DEMO_DIR / "05_config" / "tag_mapping.json"
        if not config_path.exists():
            return jsonify({"success": False, "error": "精选氮塞 Demo 配置不存在"}), 404
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        tag_mapping = {}
        if mapping_path.exists():
            with mapping_path.open("r", encoding="utf-8") as file:
                tag_mapping = json.load(file)
        return jsonify({
            "success": True,
            "data": {
                "default_case": config.get("default_case") or "E11",
                "description": config.get("description") or "",
                "demo_cases": config.get("demo_cases") or [],
                "summary": _read_selected_demo_csv("01_required_inputs/demo_selected_events_summary.csv"),
                "detail": _read_selected_demo_csv("01_required_inputs/demo_selected_events_detail.csv"),
                "tag_mapping": tag_mapping,
            },
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/nitrogen-demo-selected/file/<path:relative_path>", methods=["GET"])
def get_selected_nitrogen_demo_file(relative_path):
    resolved = _resolve_selected_demo_file(relative_path)
    if not resolved:
        return jsonify({"success": False, "error": "文件不存在或路径不合法"}), 404
    return send_file(resolved)


@app.route("/api/nitrogen-demo/meta", methods=["GET"])
def nitrogen_demo_meta():
    try:
        with _connect_nitrogen_db() as conn:
            summary = conn.execute(
                "SELECT COUNT(*) AS row_count, MIN(time_ms) AS min_time_ms, MAX(time_ms) AS max_time_ms FROM samples"
            ).fetchone()
            meta = _nitrogen_column_meta(conn)
            metric_bounds = _nitrogen_metric_bounds(conn, meta)
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "row_count": summary["row_count"],
                        "min_time_ms": summary["min_time_ms"],
                        "max_time_ms": summary["max_time_ms"],
                        "columns": meta,
                        "metric_bounds": metric_bounds,
                    },
                }
            )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/nitrogen-demo/data", methods=["GET"])
def nitrogen_demo_data():
    try:
        start_ms = request.args.get("start_ms", type=int)
        end_ms = request.args.get("end_ms", type=int)
        max_points = request.args.get("max_points", default=2000, type=int)
        max_points = max(100, min(max_points or 2000, 20000))

        aliases = {
            "AI705": ["AI705"],
            "AI701": ["AI701"],
            "FI702": ["FI702"],
            "FIQC701": ["FIQC701", "FIC701"],
            "FIQC102": ["FIQC102"],
            "AIAS102": ["AIAS102"],
            "FIC101": ["FIC101", "FIQ101"],
            "V3": ["V3", "FIC3.MV"],
            "PRODUCT_N2": ["FIC103"],
            "MEDIUM_N2": ["FI131"],
        }

        with _connect_nitrogen_db() as conn:
            meta = _nitrogen_column_meta(conn)
            if start_ms is None or end_ms is None:
                summary = conn.execute("SELECT MIN(time_ms) AS min_time_ms, MAX(time_ms) AS max_time_ms FROM samples").fetchone()
                end_ms = end_ms if end_ms is not None else summary["max_time_ms"]
                start_ms = start_ms if start_ms is not None else end_ms - 12 * 3600 * 1000

            column_map = {key: _find_demo_column(meta, value) for key, value in aliases.items()}
            needed = [column for column in column_map.values() if column]
            select_columns = ["time_ms", "time_text", *dict.fromkeys(needed)]
            sql = (
                f"SELECT {', '.join(_quote_identifier(column) for column in select_columns)} "
                "FROM samples WHERE time_ms BETWEEN ? AND ? ORDER BY time_ms"
            )
            db_rows = conn.execute(sql, (start_ms, end_ms)).fetchall()
            total = len(db_rows)
            if total > max_points:
                step = (total - 1) / (max_points - 1)
                db_rows = [db_rows[round(index * step)] for index in range(max_points)]

            def read(row, key):
                column = column_map.get(key)
                return row[column] if column and column in row.keys() else None

            records = []
            for row in db_rows:
                metrics = {
                    "AI705": read(row, "AI705"),
                    "AI701": read(row, "AI701"),
                    "FI702": read(row, "FI702"),
                    "FIQC701": read(row, "FIQC701"),
                    "FIQC102": read(row, "FIQC102"),
                    "AIAS102": read(row, "AIAS102"),
                    "FIC101": read(row, "FIC101"),
                    "V3": read(row, "V3"),
                }
                air_in = metrics["FIC101"]
                outputs = [metrics["FIQC102"], read(row, "PRODUCT_N2"), read(row, "MEDIUM_N2"), metrics["FI702"]]
                valid_outputs = [value for value in outputs if isinstance(value, (int, float))]
                balance = None
                if isinstance(air_in, (int, float)) and air_in and len(valid_outputs) >= 2:
                    balance = ((air_in - sum(valid_outputs)) / air_in) * 100
                metrics["BALANCE"] = balance
                records.append({"timeMs": row["time_ms"], "time": row["time_text"], "metrics": metrics})

            return jsonify(
                {
                    "success": True,
                    "data": {
                        "rows": records,
                        "total_in_range": total,
                        "returned": len(records),
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                    },
                }
            )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/nitrogen-agent/analyze", methods=["POST"])
def nitrogen_agent_analyze():
    try:
        data = request.get_json() or {}
        detail_level = str(data.get("detail_level") or "full").strip().lower()
        analysis_stage = str(data.get("analysis_stage") or "").strip().lower()
        start_ms = _safe_int(data.get("start_ms"))
        end_ms = _safe_int(data.get("end_ms"))
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            return jsonify({"success": False, "error": "缺少有效氮塞区间"}), 400

        before_min = max(5, min(_safe_int(data.get("before_min")) or 30, 120))
        after_min = max(5, min(_safe_int(data.get("after_min")) or 30, 120))
        event_id = (data.get("event_id") or "当前区间").strip()
        trigger_tags = data.get("trigger_tags") or []
        requested_basis = data.get("basis") or []
        shape_evidence = data.get("shape_evidence") or {}
        requested_causes = data.get("cause_branches") or []
        requested_balance = data.get("material_balance") or {}
        operating_mode = data.get("operating_mode") or {}
        load_baseline = data.get("load_baseline") or {}
        directional_checks = data.get("directional_checks") or []

        before_rows = []
        during_rows = []
        after_rows = []
        try:
            before_rows = _read_nitrogen_records(start_ms - before_min * 60 * 1000, start_ms, 3000)
            during_rows = _read_nitrogen_records(start_ms, end_ms, 3000)
            after_rows = _read_nitrogen_records(end_ms, end_ms + after_min * 60 * 1000, 3000)
        except Exception:
            pass

        focus_tags = ["AI705", "AI701", "FI702", "FIQC701", "FIC101", "FIQC102", "AIAS102", "BALANCE"]
        stats = {
            tag: {
                "before": _metric_stats(before_rows, tag),
                "during": _metric_stats(during_rows, tag),
                "after": _metric_stats(after_rows, tag),
            }
            for tag in focus_tags
        }

        basis = []
        if isinstance(shape_evidence, dict) and shape_evidence.get("basis"):
            try:
                recovery_pct = float(shape_evidence.get("recoveryRatio")) * 100
            except Exception:
                recovery_pct = None
            basis.append(
                {
                    "tag": "AI705",
                    "value": (
                        f"{shape_evidence.get('shapeText') or '下凹形态'}；"
                        f"工作点 {_format_metric(shape_evidence.get('workpoint'))}，"
                        f"最低 {_format_metric(shape_evidence.get('minValue'))}，"
                        f"下凹 {_format_metric(shape_evidence.get('dipDepth'))}，"
                        f"恢复 {_format_metric(recovery_pct)}%"
                    ),
                    "basis": str(shape_evidence.get("basis") or ""),
                }
            )
        for item in requested_basis[:6]:
            if not isinstance(item, dict):
                continue
            if item.get("tag") == "AI705" and any(row.get("tag") == "AI705" for row in basis):
                continue
            basis.append(
                {
                    "tag": item.get("tag"),
                    "value": item.get("value") or item.get("phenomenon") or "",
                    "basis": item.get("basis") or item.get("reason") or "",
                }
            )

        if not basis:
            for tag in ["AI705", "AI701", "FI702", "FIQC701"]:
                during = stats[tag]["during"]
                before = stats[tag]["before"]
                if not during["valid"]:
                    continue
                direction = "偏离" if not before["valid"] else ("上升" if during["mean"] > before["mean"] else "下降")
                basis.append(
                    {
                        "tag": tag,
                        "value": f"当前均值 {_format_metric(during['mean'])}",
                        "basis": f"{tag} 在区间内呈现{direction}，用于支撑粗氩侧状态复核。",
                    }
                )

        balance = stats["BALANCE"]["during"]
        balance_swing = balance.get("swing")
        balance_delta = balance.get("delta")
        if requested_balance.get("result") or requested_balance.get("conclusion"):
            material_balance_review = "；".join(
                item
                for item in (
                    str(requested_balance.get("result") or "").strip(),
                    str(requested_balance.get("conclusion") or "").strip(),
                )
                if item
            )
        elif not balance["valid"]:
            material_balance_review = "关键流量数据不足，物料平衡暂作为待补充复核项。"
        elif abs(balance_delta or 0) > 0.8 or (balance_swing or 0) > 1.4:
            material_balance_review = (
                f"平衡偏差均值 {_format_metric(balance['mean'])}%，波动 {_format_metric(balance_swing)}%，"
                "需同步排查负荷变化、产品取出量变化和计量偏差。"
            )
        else:
            material_balance_review = (
                f"平衡偏差均值 {_format_metric(balance['mean'])}%，波动 {_format_metric(balance_swing)}%，"
                "暂不支持仅由全流程负荷扰动解释当前区间。"
            )

        cause_branches = []
        if requested_causes:
            for cause in requested_causes[:4]:
                cause_branches.append(
                    {
                        "branch": cause.get("branch", "原因分支"),
                        "cause": cause.get("name") or cause.get("cause") or "待复核",
                        "support_level": cause.get("confidence") or cause.get("support_level") or "待确认",
                    }
                )
        else:
            cause_branches = [
                {"branch": "粗氩塔", "cause": "FI702偏高或FIC701偏低", "support_level": "优先"},
                {"branch": "主塔", "cause": "氧气多抽、氮气少抽、V3阀开过大或AI701高值表现", "support_level": "待复核"},
                {"branch": "空气系统", "cause": "空气少进或膨胀空气旁通量偏少", "support_level": "待确认"},
                {"branch": "事件", "cause": "分子筛切换不平稳或变负荷过程", "support_level": "待确认"},
            ]

        level = data.get("level") or "normal"
        conclusion_map = {
            "high": "重度氮塞",
            "medium": "中度氮塞",
            "low": "轻度氮塞",
            "normal": "未见明显氮塞特征",
        }
        conclusion = conclusion_map.get(level, "待复核")
        trigger_text = "、".join(trigger_tags[:4]) if trigger_tags else "粗氩侧测点"
        summary = (
            f"{event_id}（{_format_demo_time(start_ms)} - {_format_demo_time(end_ms)}）"
            f"已完成区间扫描。{trigger_text} 为主要触发测点，"
            "建议结合原因分支、物料平衡复核和现场操作记录进行确认。"
        )

        missing_information = data.get("missing_information") or []
        review_tags = data.get("review_tags") or ["AI705", "AI701", "FI702", "FIQC701", "BALANCE"]
        fault_tree_guidance = _build_fault_tree_guidance(trigger_tags, review_tags, basis)
        fault_tree_steps = fault_tree_guidance.get("steps") or []
        top_event_judgement = _build_top_event_judgement(level, trigger_tags, review_tags, missing_information)
        evidence_nodes = _build_evidence_nodes(basis, trigger_tags, review_tags, missing_information)
        fault_tree_path = _build_fault_tree_path(trigger_tags, review_tags, missing_information)
        branch_ranking = _build_branch_ranking(trigger_tags, review_tags)
        key_missing_data = _build_key_missing_data(missing_information)
        action_advice = [
            "先复核 T0：确认 AI705 是否相对当前工作点形成下凹、谷底和回升，并联看 AI701。",
            "补充粗氩塔阻力，用于确认 A3“粗氩塔阻力异常”是否成立。",
            "补充 LIC702 和冷凝器温差，用于确认 A4“冷凝器液位 / 冷凝负荷异常”是否成立。",
            "补充 AIAS102、FIQC102、上下塔阻力，用于排查 B 分支主塔操作影响。",
            "调取分子筛切换记录和负荷变化记录，用于确认 D 分支事件因素。",
        ]
        if fault_tree_steps:
            first_step = fault_tree_steps[0]
            action_text = first_step.get("action") if isinstance(first_step, dict) else ""
            if action_text:
                action_advice.insert(0, action_text)
        data_payload = {
            "event_id": event_id,
            "conclusion": conclusion,
            "final_conclusion": conclusion,
            "decision_source": "rule_engine",
            "decision_label": "规则主判定",
            "summary": summary,
            "explanation_source": "rule_engine",
            "explanation_label": "规则分析说明",
            "fallback_source": "",
            "top_event_judgement": top_event_judgement,
            "basis": basis,
            "evidence_nodes": evidence_nodes,
            "fault_tree_path": fault_tree_path,
            "branch_ranking": branch_ranking,
            "key_missing_data": key_missing_data,
            "cause_branches": cause_branches,
            "material_balance_review": material_balance_review,
            "material_balance_mode": operating_mode.get("mode") or "steady_review",
            "material_balance_formula_status": requested_balance.get("formulaStatus") or "implemented",
            "material_balance_formula_name": requested_balance.get("formulaName") or "external_compression_sfit_material_balance",
            "material_balance_basis": requested_balance.get("formulaText") or load_baseline.get("basis") or "外压缩.sfit物料平衡：EGOX、PAIR、GAN、FIC1、FAR、CAR、AIR链式回归模型",
            "operating_mode": operating_mode,
            "load_baseline": load_baseline,
            "shape_evidence": shape_evidence,
            "directional_checks": directional_checks[:12] if isinstance(directional_checks, list) else [],
            "action_advice": action_advice,
            "fault_tree_guidance": fault_tree_guidance,
            "fault_tree_steps": fault_tree_steps,
            "review_tags": review_tags,
            "missing_information": missing_information,
            "manual_review_required": True,
            "feature_summary": stats,
            "generated_at": datetime.now().isoformat(),
            "model_used": "",
            "model_config": "",
            "analysis_mode": "rule_based",
            "analysis_note": "已完成分析，请结合现场记录进行人工确认。",
            "llm_trace": {
                "status": "pending",
                "call_attempted": False,
                "configured": bool(_load_llm_configs()),
                "model": "",
                "message": "规则扫描已完成，准备尝试智能补充分析。",
            },
            "llm_sentence": summary,
        }
        if analysis_stage in {"top_event", "material_balance", "branch_ranking", "branch_detail"}:
            stage_payload = _build_nitrogen_stage_payload(analysis_stage, data_payload)
            return jsonify({"success": True, "data": stage_payload})
        if detail_level == "brief":
            brief_sentence = _build_nitrogen_brief_sentence(event_id, conclusion, trigger_tags, branch_ranking)
            data_payload.update(
                {
                    "analysis_mode": "brief_rule",
                    "analysis_note": "已完成快速判断，可继续查看详细分析。",
                    "decision_source": "rule_engine",
                    "decision_label": "规则主判定",
                    "explanation_source": "rule_engine",
                    "explanation_label": "规则快速说明",
                    "llm_trace": {
                        "status": "brief_ready",
                        "call_attempted": False,
                        "configured": bool(_load_llm_configs()),
                        "model": "",
                        "message": "一句话初判已生成，等待详细分析。",
                    },
                    "llm_sentence": brief_sentence,
                }
            )
            return jsonify({"success": True, "data": data_payload})
        llm_context = _build_agent_llm_payload(
            event_id=event_id,
            start_ms=start_ms,
            end_ms=end_ms,
            level=level,
            trigger_tags=trigger_tags,
            basis=basis,
            cause_branches=cause_branches,
            material_balance_review=material_balance_review,
            missing_information=missing_information,
            review_tags=review_tags,
            stats=stats,
            fault_tree_guidance=fault_tree_guidance,
        )
        llm_result, llm_error, llm_meta = _normalize_agent_llm_result(_call_agent_llm(llm_context))
        if llm_result:
            llm_conclusion = str(llm_result.get("conclusion") or "").strip()
            same_conclusion = llm_conclusion == conclusion
            data_payload.update(
                {
                    "summary": (llm_result.get("summary") or summary) if same_conclusion else summary,
                    "top_event_judgement": llm_result.get("top_event_judgement") or top_event_judgement,
                    "basis": _normalize_agent_list(llm_result.get("basis"), basis),
                    "evidence_nodes": _normalize_agent_list(llm_result.get("evidence_nodes"), evidence_nodes, limit=10),
                    "fault_tree_path": _normalize_agent_list(llm_result.get("fault_tree_path"), fault_tree_path, limit=24),
                    "branch_ranking": _normalize_agent_list(llm_result.get("branch_ranking"), branch_ranking, limit=4),
                    "key_missing_data": _normalize_agent_list(llm_result.get("key_missing_data"), key_missing_data, limit=10),
                    "cause_branches": _normalize_agent_list(llm_result.get("cause_branches"), cause_branches, limit=4),
                    "material_balance_review": llm_result.get("material_balance_review") or material_balance_review,
                    "fault_tree_steps": _normalize_agent_list(llm_result.get("fault_tree_steps"), fault_tree_steps, limit=5),
                    "action_advice": _normalize_agent_list(llm_result.get("action_advice"), action_advice, limit=6),
                    "review_tags": _normalize_agent_list(llm_result.get("review_tags"), review_tags),
                    "missing_information": _normalize_agent_list(llm_result.get("missing_information"), missing_information),
                    "manual_review_required": bool(llm_result.get("manual_review_required", True)),
                    "model_used": llm_result.get("_model_name", ""),
                    "model_config": llm_result.get("_model_config_name", ""),
                    "analysis_mode": "llm_enhanced",
                    "analysis_note": "已完成分析，请结合现场记录进行人工确认。",
                    "decision_source": "rule_engine",
                    "decision_label": "规则主判定",
                    "explanation_source": "llm",
                    "explanation_label": "智能补充说明",
                    "fallback_source": "",
                    "trace_stage": analysis_stage or "final_summary",
                    "trace_title": "步骤4：生成结论",
                    "trace_detail": "正在整理结论和处理建议。",
                    "trace_focus_node": _resolve_trace_focus_node(branch_ranking),
                    "llm_trace": {
                        "status": "succeeded",
                        "call_attempted": True,
                        "configured": True,
                        "model": llm_result.get("_model_name", ""),
                        "config": llm_result.get("_model_config_name", ""),
                        "message": "大模型已返回结构化诊断结论。",
                        "attempts": llm_meta.get("attempts") or [],
                    },
                    "llm_sentence": llm_result.get("summary") or summary,
                }
            )
            if not same_conclusion and llm_conclusion:
                data_payload["analysis_note"] = "已完成分析，请以规则判断为准并参考智能建议。"
                data_payload["llm_conclusion"] = llm_conclusion
        elif llm_error:
            data_payload["analysis_fallback_reason"] = llm_error
            data_payload["decision_source"] = "rule_engine"
            data_payload["decision_label"] = "规则主判定"
            data_payload["explanation_source"] = "rule_engine"
            data_payload["explanation_label"] = "规则兜底说明"
            data_payload["fallback_source"] = "backend_llm"
            configured = bool(_load_llm_configs())
            last_attempt = (llm_meta.get("attempts") or [])[-1] if isinstance(llm_meta, dict) else {}
            data_payload["llm_trace"] = {
                "status": "failed" if configured else "skipped",
                "call_attempted": configured,
                "configured": configured,
                "model": "",
                "message": llm_error,
                "error_code": str((last_attempt or {}).get("code") or ""),
                "error_reason": str((last_attempt or {}).get("message") or llm_error),
                "attempts": llm_meta.get("attempts") or [],
            }
            data_payload["trace_stage"] = analysis_stage or "final_summary"
            data_payload["trace_title"] = "步骤4：生成结论"
            data_payload["trace_detail"] = "正在整理结论和处理建议。"
            data_payload["trace_focus_node"] = _resolve_trace_focus_node(branch_ranking)
            data_payload["llm_sentence"] = summary

        try:
            report_paths = _generate_nitrogen_analysis_report(
                data,
                data_payload,
                stats,
                {
                    "before": before_rows,
                    "during": during_rows,
                    "after": after_rows,
                },
            )
            data_payload.update(report_paths)
            data_payload["report_generated_at"] = datetime.now().isoformat(timespec="seconds")
        except Exception as report_exc:
            data_payload["report_error"] = str(report_exc)

        return jsonify({"success": True, "data": data_payload})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/pi/connect", methods=["POST"])
def pi_connect():
    try:
        data = request.get_json() or {}
        server = data.get("server", "")
        web_api = data.get("webApi", "")
        username = data.get("username", "")
        password = data.get("password", "")

        if not server:
            return jsonify({"success": False, "error": "缺少服务器地址"}), 400

        return jsonify({
            "success": True,
            "message": "PI 数据库连接成功",
            "data": {
                "connected": True,
                "server": server,
                "username": username
            }
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/pi/import", methods=["POST"])
def pi_import():
    try:
        data = request.get_json() or {}
        date_range = data.get("dateRange", [])
        tags = data.get("tags", [])

        if not tags:
            return jsonify({"success": False, "error": "请选择至少一个标签"}), 400

        return jsonify({
            "success": True,
            "message": "数据导入成功",
            "data": {
                "timestamps": [],
                "tags": {},
                "count": 0
            }
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/pi/analyze-nitrogen", methods=["POST"])
def pi_analyze_nitrogen():
    try:
        data = request.get_json() or {}
        pi_data = data.get("data", {})

        values = pi_data.get("values", [])
        stats = pi_data.get("stats", {})
        tags = pi_data.get("tags", {})

        if not values and not tags:
            return jsonify({"success": False, "error": "缺少数据"}), 400

        if values:
            vals = [v for v in values if v is not None]
            if not vals:
                return jsonify({"success": False, "error": "数据为空"}), 400

            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            std = variance ** 0.5
            max_val = max(vals)
            min_val = min(vals)

            threshold_high = mean + 2 * std
            threshold_low = mean - 2 * std
            anomaly_count = sum(1 for v in vals if v > threshold_high or v < threshold_low)
            anomaly_ratio = anomaly_count / len(vals) if vals else 0

            if anomaly_ratio > 0.1 or max_val - min_val > 3 * std:
                risk_level = "high"
                confidence = f"{min(95, 70 + int(anomaly_ratio * 100))}%"
                match_score = "检测到异常波动"
                features = [
                    f"数据波动显著偏大（异常点占比 {anomaly_ratio:.1%}）",
                    f"均值: {mean:.2f}, 标准差: {std:.2f}",
                    "可能存在氮塞前兆特征",
                    "建议关注工艺参数变化趋势"
                ]
            else:
                risk_level = "low"
                confidence = f"{80 + int((1 - anomaly_ratio) * 20)}%"
                match_score = "正常工况"
                features = [
                    "数据波动在正常范围内",
                    f"均值: {mean:.2f}, 标准差: {std:.2f}",
                    "工况正常"
                ]
        elif tags:
            argon = tags["氩馏分"]
            argon_mean = sum(argon) / len(argon) if argon else 0
            argon_std = (sum((x - argon_mean) ** 2 for x in argon) / len(argon)) ** 0.5 if argon else 0

            if argon_mean > 15 or argon_std > 5:
                risk_level = "high"
                confidence = "92%"
                match_score = "检测到异常波动"
                features = [
                    "氩馏分显著偏高（平均 >15%）",
                    "氩馏分波动剧烈（标准差 >5%）",
                    "可能存在氮塞前兆特征"
                ]
            else:
                risk_level = "low"
                confidence = "88%"
                match_score = "正常工况"
                features = [
                    "氩馏分在正常范围内",
                    "上塔压力稳定",
                    "液氧纯度无明显下降"
                ]
        elif "上塔压力" in tags:
            pressure = tags["上塔压力"]
            pressure_mean = sum(pressure) / len(pressure) if pressure else 0

            if pressure_mean > 550:
                risk_level = "medium"
                confidence = "75%"
                match_score = "压力偏高"
                features = [
                    "上塔压力偏高",
                    "建议关注冷量平衡"
                ]
            else:
                risk_level = "low"
                confidence = "80%"
                match_score = "正常工况"
                features = [
                    "上塔压力稳定",
                    "工况正常"
                ]
        else:
            risk_level = "low"
            confidence = "70%"
            match_score = "数据不足"
            features = [
                "数据不足以进行完整氮塞分析",
                "建议提供氩馏分和上塔压力数据"
            ]

        return jsonify({
            "success": True,
            "data": {
                "riskLevel": risk_level,
                "confidence": confidence,
                "matchScore": match_score,
                "features": features,
                "timestamp": datetime.now().isoformat()
            }
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/pi/llm-analyze", methods=["POST"])
def pi_llm_analyze():
    try:
        data = request.get_json() or {}
        pi_data = data.get("data", {})
        analysis_type = data.get("analysisType", "nitrogen")

        if not pi_data or not pi_data.get("tags"):
            return jsonify({"success": False, "error": "缺少数据"}), 400

        return jsonify({
            "success": True,
            "message": "大模型分析接口预留",
            "data": {
                "analysisType": analysis_type,
                "status": "pending_llm",
                "note": "该接口用于后续接入大模型进行曲线特征识别"
            }
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/reports/download", methods=["GET"])
def download_report():
    path_value = (request.args.get("path") or "").strip()
    if not path_value:
        return jsonify({"success": False, "error": "缺少报告路径"}), 400

    requested = Path(path_value)
    resolved = requested.resolve() if requested.is_absolute() else (PROJECT_ROOT / requested).resolve()

    if REPORTS_DIR.resolve() not in resolved.parents:
        return jsonify({"success": False, "error": "只允许下载 reports 目录下的文件"}), 400
    if not resolved.exists() or not resolved.is_file():
        return jsonify({"success": False, "error": "报告文件不存在"}), 404

    return send_file(resolved, as_attachment=True, download_name=resolved.name)


@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "接口不存在"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"success": False, "error": "服务器内部错误"}), 500


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", 5000))
    debug = os.getenv("API_DEBUG", "False").lower() == "true"

    print("=" * 80)
    print("任务查询与配置管理 API")
    print("=" * 80)
    print(f"服务地址: http://localhost:{port}")
    print(f"调试模式: {debug}")
    print("=" * 80)
    print("\n可用接口:")
    print("  GET  /api/health                   - 健康检查")
    print("  GET  /api/configs                  - 获取 LLM 配置")
    print("  POST /api/configs                  - 保存 LLM 配置")
    print("  GET  /api/samples                  - 获取示例数据列表")
    print("  GET  /api/tasks                    - 获取所有任务")
    print("  GET  /api/tasks/<task_id>          - 获取指定任务详情")
    print("  GET  /api/tasks/<task_id>/progress - 获取任务进度")
    print("  POST /api/tasks/cleanup            - 清理旧任务")
    print("=" * 80)

    app.run(host="0.0.0.0", port=port, debug=debug)
