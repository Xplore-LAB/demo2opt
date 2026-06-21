import html
import json
import os
import re
import ast
import copy
import math
import difflib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.utils.llm_json import repair_llm_text


@dataclass
class ResolvedReportFonts:
    title_font: str
    body_font: str
    title_path: str
    body_path: str
    source: str
    fallback_reason: str


def _register_font(alias: str, font_path: Path) -> bool:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont(alias, str(font_path)))
        pdfmetrics.registerFontFamily(alias, normal=alias, bold=alias, italic=alias, boldItalic=alias)
        return True
    except Exception:
        return False


def _resolve_font_candidates(project_root: Path) -> Dict[str, List[Path]]:
    project_fonts = project_root / "src" / "resets" / "fonts"
    windows_fonts = Path("C:/Windows/Fonts")

    return {
        "title": [
            project_fonts / "方正小标宋简体.ttf",
            windows_fonts / "FZXBSJW.TTF",
            windows_fonts / "STZHONGS.TTF",
            windows_fonts / "simsun.ttc",
        ],
        "body": [
            project_fonts / "仿宋_GB2312.ttf",
            windows_fonts / "simfang.ttf",
            windows_fonts / "simsun.ttc",
            windows_fonts / "msyh.ttc",
        ],
    }


def _pick_font(alias: str, candidates: Iterable[Path]) -> Tuple[str, str]:
    for candidate in candidates:
        if not candidate.exists():
            continue
        if _register_font(alias, candidate):
            return alias, str(candidate)
    return "Helvetica", ""


def _normalized_path(value: str) -> str:
    if not value:
        return ""
    return str(Path(value).resolve()).replace("\\", "/").lower()


def resolve_report_fonts() -> ResolvedReportFonts:
    project_root = Path(__file__).resolve().parents[2]
    candidates = _resolve_font_candidates(project_root)

    title_font, title_path = _pick_font("GovTitleFont", candidates["title"])
    body_font, body_path = _pick_font("GovBodyFont", candidates["body"])

    preferred_title = str((candidates.get("title") or [None])[0] or "")
    preferred_body = str((candidates.get("body") or [None])[0] or "")
    picked_project_fonts = (
        bool(title_path and body_path)
        and _normalized_path(title_path) == _normalized_path(preferred_title)
        and _normalized_path(body_path) == _normalized_path(preferred_body)
    )

    if picked_project_fonts:
        source = "项目字体"
        fallback_reason = ""
    elif title_path or body_path:
        source = "系统字体回退"
        fallback_reason = "项目字体缺失或不可加载，已回退至系统字体。"
    else:
        source = "内置回退"
        fallback_reason = "项目字体与系统字体均不可用，已回退到 Helvetica。"

    print(
        "[report-font] title=%s (%s), body=%s (%s), source=%s"
        % (title_font, title_path or "builtin", body_font, body_path or "builtin", source)
    )
    if fallback_reason:
        print(f"[report-font] fallback_reason={fallback_reason}")

    return ResolvedReportFonts(
        title_font=title_font,
        body_font=body_font,
        title_path=title_path,
        body_path=body_path,
        source=source,
        fallback_reason=fallback_reason,
    )


class ReportGenerator:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.fonts = resolve_report_fonts()
        self.pdf_styles: Dict[str, Any] = {}

    def generate_markdown_report(self, analysis_result: Dict[str, Any], filename: Optional[str] = None) -> str:
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_report_{timestamp}.md"

        report_payload = self._prepare_analysis_result_for_report(analysis_result)
        report_payload["_report_asset_dir"] = str((Path(self.output_dir) / "assets" / Path(filename).stem).resolve())
        report_payload["_report_asset_prefix"] = f"assets/{Path(filename).stem}"
        filepath = os.path.join(self.output_dir, filename)
        md_content = self._finalize_markdown_content(self._build_markdown_content(report_payload))

        with open(filepath, "w", encoding="utf-8") as file:
            file.write(md_content)

        print(f"Markdown 报告已生成: {filepath}")
        return filepath

    def generate_pdf_report(self, analysis_result: Dict[str, Any], filename: Optional[str] = None) -> str:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import Image as PlatypusImage, Paragraph, SimpleDocTemplate, Spacer
        except ImportError:
            print("警告: 未安装 reportlab，无法生成 PDF 报告")
            print("安装命令: pip install reportlab")
            return ""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_report_{timestamp}.pdf"
        report_payload = self._prepare_analysis_result_for_report(analysis_result)
        report_payload["_report_asset_dir"] = str((Path(self.output_dir) / "assets" / Path(filename).stem).resolve())
        report_payload["_report_asset_prefix"] = f"assets/{Path(filename).stem}"

        filepath = os.path.join(self.output_dir, filename)
        document = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=54,
            leftMargin=54,
            topMargin=52,
            bottomMargin=44,
        )

        styles = self._build_pdf_styles(
            getSampleStyleSheet(),
            self.fonts.title_font,
            self.fonts.body_font,
            colors,
            TA_CENTER,
            TA_JUSTIFY,
            TA_LEFT,
        )
        self.pdf_styles = styles

        section_index = 0
        story = [
            Paragraph("空分装置智能运行优化分析报告", styles["Title"]),
            Paragraph("（面向生产一线执行与工艺复核）", styles["SubTitle"]),
            Paragraph(
                (
                    f"生成时间：{html.escape(self._stringify(report_payload.get('timestamp'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))}"
                    f"　　分析状态：{self._get_status_badge(report_payload.get('status', 'unknown'))}"
                    f"　　异常指标数：{report_payload.get('abnormal_count', 0)}"
                ),
                styles["Meta"],
            ),
            Spacer(1, 0.10 * inch),
        ]

        def add_section_heading(title: str) -> None:
            nonlocal section_index
            section_index += 1
            numeral = self._section_numeral(section_index)
            story.append(Paragraph(f"{numeral}、{html.escape(title)}", styles["Heading2"]))

        add_section_heading("现场执行摘要")
        story.append(
            self._build_pdf_execution_summary_cards(
                self._execution_summary_items(report_payload),
                styles=styles,
                content_width=document.width,
            )
        )

        add_section_heading("时间对比可视化")
        self._append_pdf_visualization_section(
            story,
            styles=styles,
            visualization_cards=self._visualization_cards(report_payload),
            image_cls=PlatypusImage,
            inch=inch,
        )

        add_section_heading("装置总评")
        story.append(self._build_pdf_kv_table(self._device_overview_items(report_payload), self.fonts.body_font))

        dimension_items = self._dimension_status_items(report_payload)
        if dimension_items:
            add_section_heading("分项状态判断")
            story.append(self._build_pdf_kv_table(dimension_items, self.fonts.body_font))

        add_section_heading("任务概览")
        story.append(self._build_pdf_kv_table(self._overview_items(report_payload), self.fonts.body_font))

        target_definition_items = self._target_definition_items(report_payload)
        if target_definition_items:
            add_section_heading("目标定义")
            story.append(self._build_pdf_kv_table(target_definition_items, self.fonts.body_font))

        overall_judgement = report_payload.get("overall_judgement") or {}
        overall_review_lines = self._build_overall_review_lines(overall_judgement)
        if overall_review_lines:
            add_section_heading("工况复核摘要")
            self._append_pdf_bullets(
                story,
                [f"{label}：{text}" for label, text in overall_review_lines],
                styles["Bullet"],
            )

        transparency = self._build_transparency_view(report_payload)
        if any(transparency.values()):
            add_section_heading("证据分层与规则透明度")
            section_map = [
                ("基线与阈值来源", "baseline_refs", "当前未记录明确的基线或阈值来源。"),
                ("事实层", "facts", "当前未形成可直接引用的数据事实。"),
                ("规则层", "rules", "当前未形成显式规则推导输出。"),
                ("解释层", "explanations", "当前未补充候选解释，后续需结合知识检索与现场核查。"),
                ("行动层", "actions", "当前未形成闭环动作建议，请先完成关键点位复核。"),
                ("状态聚合规则", "state_rules", "当前未记录状态聚合规则说明。"),
            ]
            for title, key, fallback in section_map:
                story.append(Paragraph(title, styles["Heading3"]))
                self._append_pdf_bullets(
                    story,
                    transparency.get(key)[:6] or [fallback],
                    styles["Bullet"],
                )

        calculation_audit = self._calculation_audit_payload(report_payload)
        if calculation_audit:
            add_section_heading("中间计算审计")
            story.append(Paragraph("数据接入口径", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                self._format_calculation_data_intake_items(calculation_audit)[:7] or ["当前未记录数据接入口径说明。"],
                styles["Bullet"],
            )
            story.append(Paragraph("单指标审计表", styles["Heading3"]))
            indicator_rows = self._calculation_indicator_rows(calculation_audit)
            if indicator_rows:
                story.append(
                    self._build_pdf_table(
                        indicator_rows,
                        [2.0 * inch, 0.72 * inch, 0.72 * inch, 0.72 * inch, 0.72 * inch, 0.8 * inch, 0.7 * inch, 0.7 * inch],
                        self.fonts.body_font,
                    )
                )
            else:
                self._append_pdf_bullets(story, ["当前未生成单指标审计表。"], styles["Bullet"])
            story.append(Paragraph("历史统计判断", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                self._format_history_judgement_items(calculation_audit)[:8] or ["当前未记录历史统计判断。"],
                styles["Bullet"],
            )
            story.append(Paragraph("子系统与装置聚合输入", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                (self._format_subsystem_audit_items(calculation_audit) + self._format_plant_audit_items(calculation_audit))[:8]
                or ["当前未记录子系统与装置聚合输入。"],
                styles["Bullet"],
            )

        semantic_data = report_payload.get("semantic_data") or []
        abnormal_items = self._select_abnormal_items(semantic_data)
        abnormal_details = report_payload.get("abnormal_details") or report_payload.get("abnormal_indicators") or []
        if semantic_data:
            add_section_heading("状态识别与工况复核")
            self._append_pdf_paragraphs(
                story,
                f"本轮快照共纳入 {len(semantic_data)} 个指标，其中异常候选 {len(abnormal_items)} 个。",
                styles["Body"],
            )

            state_counts = self._build_state_counts(semantic_data)
            if state_counts:
                state_rows = [["状态", "数量", "占比"]]
                total = max(len(semantic_data), 1)
                for state, count in state_counts.items():
                    state_rows.append([state, str(count), f"{count / total:.1%}"])
                story.append(self._build_pdf_table(state_rows, [2.2 * inch, 1.0 * inch, 1.2 * inch], self.fonts.body_font))

            if abnormal_items:
                story.append(Paragraph("（一）重点异常候选", styles["Heading3"]))
                abnormal_rows = [["指标", "当前值", "偏差", "状态"]]
                for item in abnormal_items[:8]:
                    abnormal_rows.append(
                        [
                            self._stringify(item.get("name")),
                            self._format_number(item.get("current_value")),
                            self._format_number(item.get("diff")),
                            self._stringify(item.get("state_desc")),
                        ]
                    )
                story.append(self._build_pdf_table(abnormal_rows, [3.2 * inch, 1.0 * inch, 0.9 * inch, 0.8 * inch], self.fonts.body_font))

            if abnormal_details:
                story.append(Paragraph("（二）异常详情说明", styles["Heading3"]))
                for item in abnormal_details[:8]:
                    story.append(Paragraph(self._stringify(item.get("name")), styles["ItemTitle"]))
                    detail_lines = [
                        (
                            f"当前值：{self._format_number(item.get('current_value'))}；"
                            f"偏差：{self._format_number(item.get('diff'))}{self._format_diff_percent_text(item.get('diff_percent'))}；"
                            f"状态：{self._stringify(item.get('level') or item.get('state_desc'))}"
                        ),
                        f"时间窗口：{self._format_window_text(item)}",
                        f"规则原因：{self._stringify(item.get('rule_reason'))}",
                    ]
                    if item.get("ai_reason"):
                        detail_lines.append(f"{self._review_section_label()}：{self._stringify(item.get('ai_reason'))}")
                    self._append_pdf_bullets(story, detail_lines, styles["Bullet"])

        reasoning = report_payload.get("reasoning_result") or {}
        if reasoning:
            add_section_heading("诊断结论")
            for title, key in (
                ("候选原因与待核查假设", "root_cause"),
                ("操作建议", "operation_suggestion"),
                ("安全提示", "safety_warning"),
            ):
                if reasoning.get(key):
                    use_callout = key in {"operation_suggestion", "safety_warning"}
                    if not use_callout:
                        story.append(Paragraph(title, styles["Heading3"]))
                    if key == "root_cause":
                        boundary = self._single_line_text(
                            (report_payload.get("overall_judgement") or {}).get("explanation_boundary"),
                            "以下内容仅为候选原因与待核查假设，不构成已确认根因。",
                        ).strip()
                        if boundary:
                            self._append_pdf_paragraphs(story, boundary, styles["Body"])
                    rendered_text = (
                        self._soften_root_cause_text(reasoning.get(key))
                        if key == "root_cause"
                        else reasoning.get(key)
                    )
                    if use_callout:
                        self._append_pdf_callout_box(
                            story,
                            title=title,
                            text=rendered_text,
                            styles=styles,
                            content_width=document.width,
                            tone="warning" if key == "safety_warning" else "action",
                        )
                    else:
                        self._append_pdf_paragraphs(story, rendered_text, styles["Body"])

        confirmed_items, pending_items = self._build_conclusion_layers(report_payload)
        add_section_heading("结论分层（已确认/待核查）")
        story.append(Paragraph("已确认依据", styles["Heading3"]))
        self._append_pdf_bullets(story, confirmed_items[:6] or ["当前可确认依据不足，请先完成关键点位核查。"], styles["Bullet"])
        story.append(Paragraph("待现场核查项", styles["Heading3"]))
        self._append_pdf_bullets(
            story,
            pending_items[:8] or ["本轮未识别新增待核查项，建议按班组标准点检表执行复核。"],
            styles["Bullet"],
        )

        decision = report_payload.get("decision_result") or {}
        if decision:
            add_section_heading("决策验证与执行建议")
            for title, key in (
                ("执行步骤", "actionable_steps"),
                ("效果预估", "simulation_result"),
                ("风险评估", "risk_assessment"),
                ("回退策略", "rollback_strategy"),
            ):
                if decision.get(key):
                    use_callout = key in {"actionable_steps", "risk_assessment", "rollback_strategy"}
                    if not use_callout:
                        story.append(Paragraph(title, styles["Heading3"]))
                    if use_callout:
                        tone = "action"
                        if key == "risk_assessment":
                            tone = "warning"
                        elif key == "rollback_strategy":
                            tone = "rollback"
                        self._append_pdf_callout_box(
                            story,
                            title=title,
                            text=decision.get(key),
                            styles=styles,
                            content_width=document.width,
                            tone=tone,
                        )
                    else:
                        self._append_pdf_paragraphs(story, decision.get(key), styles["Body"])

            closed_loop = decision.get("closed_loop_validation") or report_payload.get("closed_loop_validation") or {}
            resolved_status = self._resolved_verification_status_code(report_payload)
            verification_text = f"验证状态：{self._get_verification_badge(resolved_status)}"
            if closed_loop:
                verification_text = (
                    f"验证状态：{self._get_verification_badge(resolved_status)}；"
                    f"闭环状态：{self._closed_loop_status_text(closed_loop.get('status', 'pending'))}"
                )
            story.append(Paragraph(verification_text, styles["BodyNoIndent"]))
            if closed_loop.get("summary"):
                self._append_pdf_paragraphs(story, f"闭环说明：{closed_loop.get('summary')}", styles["BodyNoIndent"])

        knowledge_retrieval = report_payload.get("knowledge_retrieval") or {}
        if knowledge_retrieval:
            knowledge_support = self._build_knowledge_support_view(report_payload)
            add_section_heading("知识证据链与动作边界")
            story.append(Paragraph("证据如何支撑当前判断", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                knowledge_support["judgement_support"][:5] or ["未检索到新增知识依据，本轮判断主要基于在线工况与规则结果。"],
                styles["Bullet"],
            )
            story.append(Paragraph("证据如何约束执行动作", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                knowledge_support["action_constraints"][:5] or ["执行前请对照现场 SOP、联锁边界和历史案例完成人工复核。"],
                styles["Bullet"],
            )
            if knowledge_support["evidence_refs"]:
                story.append(Paragraph("证据映射清单", styles["Heading3"]))
                self._append_pdf_bullets(story, knowledge_support["evidence_refs"][:6], styles["Bullet"])
            if knowledge_support.get("triads"):
                story.append(Paragraph("判断 / 依据 / 动作约束", styles["Heading3"]))
                self._append_pdf_bullets(story, knowledge_support["triads"][:6], styles["Bullet"])

        data_curve_sections = self._build_data_curve_overview_sections(report_payload)
        if data_curve_sections:
            add_section_heading("整体数据曲线关联总览")
            self._append_pdf_bullets(
                story,
                [
                    "以下图按业务主题将多指标统一换算为相对各自参考值的偏差百分比，用于观察同向 / 反向波动和整体相关性。",
                    "0% 表示贴近各自参考值；淡蓝带表示 ±10% 参考带；红色竖线表示本类指标中最早异常起点（如可定位）。",
                ],
                styles["Bullet"],
            )
            self._append_pdf_data_curve_overview_section(
                story,
                styles=styles,
                sections=data_curve_sections,
                image_cls=PlatypusImage,
                inch=inch,
            )

        analysis_steps = self._normalize_analysis_steps(report_payload)
        traceability = dict(report_payload.get("traceability") or {})
        traceability_data_source = self._first_non_placeholder(
            traceability.get("data_source"),
            report_payload.get("data_source"),
            "uploaded",
        )
        step_traces = self._normalize_step_traces(traceability.get("step_traces") or [], analysis_steps, report_payload)
        add_section_heading("附录：流程与追溯")
        story.append(Paragraph("分析流程步骤", styles["Heading3"]))
        for step in analysis_steps:
            step_no = step.get("step", "-")
            step_title = self._stringify(step.get("title"), "未记录（模板占位）")
            story.append(Paragraph(f"（{step_no}）{html.escape(step_title)}", styles["ItemTitle"]))
            summary_lines = self._format_step_summary_lines(step_title, step.get("summary"))
            self._append_pdf_paragraphs(story, "\n".join(summary_lines), styles["Body"])

        story.append(Paragraph("全流程可追溯记录", styles["Heading3"]))
        self._append_pdf_bullets(
            story,
            [
                f"数据来源：{self._normalize_data_source_label(traceability_data_source)}",
                "说明：以下步骤耗时与核验要点用于班组复盘，不包含调试信息。",
            ],
            styles["Bullet"],
        )
        for trace in step_traces:
            step_no = trace.get("step", "-")
            step_title = self._stringify(trace.get("title"), "未记录（模板占位）")
            duration = self._normalize_duration_ms(trace.get("duration_ms"))
            story.append(Paragraph(f"（{step_no}）{html.escape(step_title)}", styles["Heading3"]))
            self._append_pdf_bullets(
                story,
                [
                    f"耗时：{duration} ms",
                    f"结果摘要：{self._stringify_trace_output(trace.get('output_summary'), '未记录（模板占位）')}",
                    f"现场核验：{self._stringify(trace.get('manual_verification'), '未记录（模板占位）')}",
                ],
                styles["Bullet"],
            )

        story.append(Spacer(1, 0.16 * inch))
        story.append(
            Paragraph(
                "注：本报告为自动化辅助分析结果，执行前请结合现场工艺边界、联锁条件与操作规程完成人工复核。",
                styles["Note"],
            )
        )

        try:
            document.build(
                story,
                onFirstPage=lambda canvas, doc: self._draw_pdf_page_decor(canvas, doc, self.fonts.body_font),
                onLaterPages=lambda canvas, doc: self._draw_pdf_page_decor(canvas, doc, self.fonts.body_font),
            )
            print(f"PDF 报告已生成: {filepath}")
            return filepath
        except Exception as exc:
            print(f"PDF 生成失败: {exc}")
            return ""

    def _build_markdown_content(self, analysis_result: Dict[str, Any]) -> str:
        content: List[str] = [
            "# 空分装置智能运行优化分析报告\n\n",
            "## 报告信息\n",
            f"- 生成时间: {self._stringify(analysis_result.get('timestamp'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n",
            f"- 分析状态: {self._stringify(analysis_result.get('status'), 'unknown')}\n",
            f"- 异常指标数: {analysis_result.get('abnormal_count', 0)}\n",
            "\n",
            "## 装置总评\n",
        ]

        for label, value in self._device_overview_items(analysis_result):
            content.append(f"- **{label}**: {self._stringify(value)}\n")

        dimension_items = self._dimension_status_items(analysis_result)
        if dimension_items:
            content.extend(
                [
                    "\n",
                    "## 分项状态判断\n",
                ]
            )
            for label, value in dimension_items:
                content.append(f"- **{label}**: {self._stringify(value)}\n")

        content.extend(
            [
                "\n",
            "## 现场执行摘要\n",
            ]
        )

        for label, value in self._execution_summary_items(analysis_result):
            content.append(f"- **{label}**: {self._stringify(value)}\n")

        self._append_markdown_visualization_section(content, analysis_result)

        content.extend(
            [
                "\n",
            "## 任务概览\n",
            ]
        )

        for label, value in self._overview_items(analysis_result):
            content.append(f"- **{label}**: {self._stringify(value)}\n")

        target_definition_items = self._target_definition_items(analysis_result)
        if target_definition_items:
            content.extend(
                [
                    "\n",
                    "## 目标定义\n",
                ]
            )
            for label, value in target_definition_items:
                content.append(f"- **{label}**: {self._stringify(value)}\n")

        overall_judgement = analysis_result.get("overall_judgement") or {}
        overall_review_lines = self._build_overall_review_lines(overall_judgement)
        if overall_review_lines:
            content.append("\n## 工况复核摘要\n")
            for label, text in overall_review_lines:
                content.append(f"- {label}: {text}\n")

        transparency = self._build_transparency_view(analysis_result)
        if any(transparency.values()):
            content.append("\n## 证据分层与规则透明度\n")
            section_map = [
                ("基线与阈值来源", "baseline_refs", "当前未记录明确的基线或阈值来源。"),
                ("事实层", "facts", "当前未形成可直接引用的数据事实。"),
                ("规则层", "rules", "当前未形成显式规则推导输出。"),
                ("解释层", "explanations", "当前未补充候选解释，后续需结合知识检索与现场核查。"),
                ("行动层", "actions", "当前未形成闭环动作建议，请先完成关键点位复核。"),
                ("状态聚合规则", "state_rules", "当前未记录状态聚合规则说明。"),
            ]
            for title, key, fallback in section_map:
                content.append(f"\n### **{title}**\n")
                items = transparency.get(key) or []
                if items:
                    for idx, item in enumerate(items, start=1):
                        content.append(f"{idx}. {item}\n")
                else:
                    content.append(f"1. {fallback}\n")

        calculation_audit = self._calculation_audit_payload(analysis_result)
        if calculation_audit:
            content.append("\n## 中间计算审计\n")
            data_intake_items = self._format_calculation_data_intake_items(calculation_audit)
            content.append("\n### **数据接入口径**\n")
            if data_intake_items:
                for idx, item in enumerate(data_intake_items, start=1):
                    content.append(f"{idx}. {item}\n")
            else:
                content.append("1. 当前未记录数据接入口径说明。\n")

            content.append("\n### **单指标审计表**\n")
            indicator_rows = self._calculation_indicator_rows(calculation_audit)
            if indicator_rows:
                content.extend(self._build_markdown_table(indicator_rows))
            else:
                content.append("当前未生成单指标审计表。\n")

            content.append("\n### **历史统计判断**\n")
            history_judgement_items = self._format_history_judgement_items(calculation_audit)
            if history_judgement_items:
                for idx, item in enumerate(history_judgement_items, start=1):
                    content.append(f"{idx}. {item}\n")
            else:
                content.append("1. 当前未记录历史统计判断。\n")

            content.append("\n### **子系统与装置聚合输入**\n")
            aggregation_items = self._format_subsystem_audit_items(calculation_audit) + self._format_plant_audit_items(calculation_audit)
            if aggregation_items:
                for idx, item in enumerate(aggregation_items, start=1):
                    content.append(f"{idx}. {item}\n")
            else:
                content.append("1. 当前未记录子系统与装置聚合输入。\n")

        reasoning = analysis_result.get("reasoning_result")
        if not isinstance(reasoning, dict):
            reasoning = {}
        if reasoning:
            content.append("\n## 诊断结论\n")
            for title, key in (
                ("候选原因与待核查假设", "root_cause"),
                ("操作建议", "operation_suggestion"),
                ("安全提示", "safety_warning"),
            ):
                if reasoning.get(key):
                    content.append(f"\n### **{title}**\n")
                    if key == "root_cause":
                        boundary = self._single_line_text(
                            (analysis_result.get("overall_judgement") or {}).get("explanation_boundary"),
                            "以下内容仅为候选原因与待核查假设，不构成已确认根因。",
                        ).strip()
                        if boundary:
                            content.extend(self._build_markdown_text_block(boundary))
                    rendered_text = (
                        self._soften_root_cause_text(reasoning.get(key))
                        if key == "root_cause"
                        else reasoning.get(key)
                    )
                    content.extend(self._build_markdown_text_block(rendered_text))

        confirmed_items, pending_items = self._build_conclusion_layers(analysis_result)
        content.append("\n## 结论分层（已确认/待核查）\n")
        content.append("\n### **已确认依据**\n")
        if confirmed_items:
            for idx, item in enumerate(confirmed_items[:6], start=1):
                content.append(f"{idx}. {item}\n")
        else:
            content.append("1. 当前可确认依据不足，请先完成关键点位核查。\n")

        content.append("\n### **待现场核查项**\n")
        if pending_items:
            for idx, item in enumerate(pending_items[:8], start=1):
                content.append(f"{idx}. {item}\n")
        else:
            content.append("1. 本轮未识别新增待核查项，建议按班组标准点检表执行复核。\n")

        decision = analysis_result.get("decision_result")
        if not isinstance(decision, dict):
            decision = {}
        if decision:
            content.append("\n## 决策验证与执行建议\n")
            for title, key in (
                ("执行步骤", "actionable_steps"),
                ("效果预估", "simulation_result"),
                ("风险评估", "risk_assessment"),
                ("回退策略", "rollback_strategy"),
            ):
                if decision.get(key):
                    content.append(f"\n### **{title}**\n")
                    content.extend(self._build_markdown_text_block(decision.get(key)))

            closed_loop = decision.get("closed_loop_validation") or analysis_result.get("closed_loop_validation") or {}
            resolved_status = self._resolved_verification_status_code(analysis_result)
            content.append(f"\n- 验证状态: {self._verification_status_text(resolved_status)}\n")
            if closed_loop:
                content.append(f"- 闭环状态: {self._closed_loop_status_text(closed_loop.get('status', 'pending'))}\n")
                if closed_loop.get("summary"):
                    content.append(f"- 闭环说明: {self._stringify(closed_loop.get('summary'))}\n")

        knowledge_retrieval = analysis_result.get("knowledge_retrieval") or {}
        if knowledge_retrieval:
            knowledge_support = self._build_knowledge_support_view(analysis_result)
            content.append("\n## 知识证据链与动作边界\n")
            content.append("\n### **证据如何支撑当前判断**\n")
            if knowledge_support["judgement_support"]:
                for idx, item in enumerate(knowledge_support["judgement_support"][:5], start=1):
                    content.append(f"{idx}. {item}\n")
            else:
                content.append("1. 未检索到新增知识依据，本轮判断主要基于在线工况与规则结果。\n")

            content.append("\n### **证据如何约束执行动作**\n")
            if knowledge_support["action_constraints"]:
                for idx, item in enumerate(knowledge_support["action_constraints"][:5], start=1):
                    content.append(f"{idx}. {item}\n")
            else:
                content.append("1. 执行前请对照现场 SOP、联锁边界和历史案例完成人工复核。\n")

            if knowledge_support["evidence_refs"]:
                content.append("\n### **证据映射清单**\n")
                for idx, item in enumerate(knowledge_support["evidence_refs"][:6], start=1):
                    content.append(f"{idx}. {item}\n")
            if knowledge_support.get("triads"):
                content.append("\n### **判断 / 依据 / 动作约束**\n")
                for idx, item in enumerate(knowledge_support["triads"][:6], start=1):
                    content.append(f"{idx}. {item}\n")

        data_curve_sections = self._build_data_curve_overview_sections(analysis_result)
        if data_curve_sections:
            content.append("\n## 整体数据曲线关联总览\n")
            content.append("- 说明: 以下图按业务主题将多指标统一换算为相对各自参考值的偏差百分比，用于观察同向 / 反向波动和整体相关性。\n")
            content.append("- 说明: 0% 表示贴近各自参考值；淡蓝带表示 ±10% 参考带；红色竖线表示本类指标中最早异常起点（如可定位）。\n")
            for index, section in enumerate(data_curve_sections, start=1):
                title = self._stringify(section.get("title"), "未命名分类")
                content.append(f"\n### **{index}. {title}**\n")
                for line in section.get("summary_lines") or []:
                    content.append(f"- {line}\n")
                image_relative_path = self._stringify(section.get("image_relative_path"), "").strip()
                if image_relative_path:
                    content.append(f"![{title}]({image_relative_path})\n")
                else:
                    content.append("- 当前未生成整体数据曲线图像资产。\n")

        analysis_steps = self._normalize_analysis_steps(analysis_result)
        content.append("\n## 附录：流程与追溯\n")
        content.append("\n### 分析流程步骤\n")
        for step in analysis_steps:
            step_title = self._stringify(step.get("title"), "未记录（模板占位）")
            content.append(f"{step.get('step', '-')}. **{step_title}**\n")
            for line in self._format_step_summary_lines(step_title, step.get("summary")):
                content.append(f"   {line}\n")

        traceability = dict(analysis_result.get("traceability") or {})
        traceability_data_source = self._first_non_placeholder(
            traceability.get("data_source"),
            analysis_result.get("data_source"),
            "uploaded",
        )
        step_traces = self._normalize_step_traces(traceability.get("step_traces") or [], analysis_steps, analysis_result)
        content.append("\n### 全流程可追溯记录\n")
        content.append(f"- 数据来源: {self._normalize_data_source_label(traceability_data_source)}\n")
        content.append("- 说明: 以下步骤耗时与核验要点用于班组复盘，不包含调试信息。\n")
        for trace in step_traces:
            content.append(f"\n### 步骤 {trace.get('step', '-')}: {self._stringify(trace.get('title'), '未记录（模板占位）')}\n")
            content.append(f"- 耗时: {self._normalize_duration_ms(trace.get('duration_ms'))} ms\n")
            content.append(f"- 结果摘要: {self._stringify_trace_output(trace.get('output_summary'), '未记录（模板占位）')}\n")
            content.append(f"- 现场核验: {self._stringify(trace.get('manual_verification'), '未记录（模板占位）')}\n")

        content.append("\n---\n*本报告由系统自动生成，建议结合现场工艺边界和操作规程复核后执行。*\n")
        return "".join(content)

    def _prepare_analysis_result_for_report(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        payload = copy.deepcopy(analysis_result or {})
        return self._sanitize_payload_strings(payload)

    def _sanitize_payload_strings(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize_payload_strings(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_payload_strings(item) for item in value]
        if isinstance(value, str):
            return self._clean_business_text(self._normalize_report_text(value))
        return value

    def _finalize_markdown_content(self, text: str) -> str:
        lines: List[str] = []
        for line in text.splitlines():
            cleaned = self._clean_business_text(repair_llm_text(line))
            if self._is_text_noisy(cleaned):
                if cleaned.strip().startswith("- 结果摘要:"):
                    cleaned = "- 结果摘要: 已生成结构化结论，详见后续章节。"
                else:
                    cleaned = "（该段采用结构化结论呈现，详见后续章节。）"
            lines.append(cleaned.rstrip())
        output = "\n".join(lines)
        if text.endswith("\n"):
            output += "\n"
        return output

    def _clean_business_text(self, text: str) -> str:
        if not text:
            return text

        phrase_map = [
            ("语义 AI 复核", "语义复核"),
            ("语义AI复核", "语义复核"),
            ("AI 深度诊断", "深度诊断"),
            ("继续 深度诊断", "继续深度诊断"),
            ("AI 复核", "机理一致性复核"),
            ("AI复核", "机理一致性复核"),
            ("专家复核", "机理一致性复核"),
            ("语义复核命中", "语义复核确认"),
            ("主检索：", "知识检索："),
            ("校核检索：", "复核检索："),
            ("校核检索", "复核检索"),
            ("知识库检索手段", "知识依据与处置参考"),
            ("Dify 校核检索", "复核检索"),
            ("Dify 主检索", "知识检索"),
            ("Dify 检索", "知识检索"),
            ("Dify", ""),
            ("闭环=pending", "闭环=待现场闭环"),
            ("闭环=Pending", "闭环=待现场闭环"),
            ("优级", "优先级"),
            ("时切备用", "必要时切换备用"),
            ("时切换至", "必要时切换至"),
            ("时执行降负荷", "必要时执行降负荷"),
            ("置处于", "装置处于"),
            ("置由", "装置由"),
            ("置可", "装置可"),
            ("将置切", "将装置切"),
            ("将置按", "将装置按"),
            ("立即“可运行但受冷量牵制”模式", "立即进入“可运行但受冷量牵制”模式"),
            ("优恢复", "优先恢复"),
            ("优消除", "优先消除"),
            ("流量分不均", "流量分配不均"),
            ("流量分及", "流量分配及"),
            ("流量分、", "流量分配、"),
            ("换热负荷分。", "换热负荷分配。"),
            ("换热匹，", "换热匹配，"),
            ("换热匹。", "换热匹配。"),
            ("换热匹 ", "换热匹配 "),
            ("逐步优化换热匹配，一次性激进调整", "逐步优化换热匹配，避免一次性激进调整"),
            ("限制负荷波动，频繁大调节", "限制负荷波动，避免频繁大调节"),
            ("机械障", "机械故障"),
            ("限或机械降载", "限载或机械降载"),
            ("模型或测点偏差放大误判", "避免模型或测点偏差放大误判"),
            ("切换保守负荷络", "切换保守负荷策略"),
            ("置总", "装置总"),
            ("优保障置", "优先保障装置"),
            ("大度、单变量、快速调参", "大幅度单变量快速调参"),
            ("速、喘振", "防止超速、喘振"),
            ("稳冷量优", "稳冷量优先"),
            ("建议优导叶/阀位次压力", "建议优先导叶/阀位，其次压力"),
            ("冷量赤字继续向精馏侧传导。", "避免冷量赤字继续向精馏侧传导。"),
            ("下行且度扩大", "下行且幅度扩大"),
            ("存在硬障", "存在硬故障"),
            ("膨胀机乙", "膨胀机B"),
            ("补膨胀机B", "补充膨胀机B"),
            ("高于局负荷不足", "高于全局负荷不足"),
            ("优检查膨胀机B：条件、", "优先检查膨胀机B：运行条件、"),
            ("旁路漏。", "旁路泄漏。"),
            ("大度负荷扰动；时通过负荷再分", "避免大幅度负荷扰动；必要时通过负荷再分配"),
            ("置负荷变动记录", "装置负荷变动记录"),
            ("调节度<=", "调节幅度<="),
            ("设计络", "设计范围"),
            ("将测量偏差误判为工艺恶化", "避免将测量偏差误判为工艺恶化"),
            ("无新增设备障前提下", "在无新增设备故障前提下"),
            ("impact_path：", "影响路径："),
            ("confidence：", "置信度："),
            ("resulting_impact：", "结果影响："),
            ("secondary_cause：", "次因："),
            ("evidence：", "证据："),
            ("primary_cause：", "主因："),
            ("置整体", "装置整体"),
            ("温差匹", "温差匹配"),
            ("换热负荷分", "换热负荷分配"),
            ("，时分步", "，必要时分步"),
            ("优保", "优先保障"),
            ("冷量优", "冷量优先"),
            ("优先保障障主分离流程", "优先保障主分离流程"),
            ("误操作叠加风险", "防止误操作叠加风险"),
            ("因果后", "因果先后"),
            ("优处置", "优先处置"),
            ("跟踪不激进调产", "跟踪，不激进调产"),
            ("置状态", "装置状态"),
            ("边收益有限", "边际收益有限"),
            ("联调“单变量", "联调，按“单变量"),
            ("后再微调主换操作点，耦合放大。", "后再微调主换操作点，避免耦合放大。"),
            ("调参保留保安操作", "调参，保留保安操作"),
            ("流量分数据", "流量分配数据"),
            ("导叶与负荷匹，", "导叶与负荷匹配，"),
            ("保守负荷策略与产品结构优化，强行提产；", "保守负荷策略与产品结构优化，禁止强行提产；"),
            ("时执行分步降负荷", "必要时执行分步降负荷"),
            ("应及必要时执行降负荷或受控切换预案，系统性失稳", "必要时执行降负荷或受控切换预案，防止系统性失稳"),
            ("应及必要时执行", "必要时执行"),
            ("，系统性失稳", "，防止系统性失稳"),
            ("边裕度", "边界裕度"),
            ("每步不当前设定的", "每步不超过当前设定的"),
            ("转障排查", "转入故障排查"),
            ("纳同屏预警", "纳入同屏预警"),
            ("程记录时间戳", "全程记录时间戳"),
            ("（程）", "（全程）"),
            ("装装置", "装置"),
            ("冷量失为主", "冷量失衡为主"),
            ("景推演", "情景推演"),
            ("-景", "- 情景"),
            ("障结论", "故障结论"),
            ("建议复核检索", "复核检索"),
            ("联锁状态于工艺优化", "联锁状态优先于工艺优化"),
            ("大单点拉升", "单点大幅拉升"),
            ("优核查", "优先核查"),
            ("，时小步调整", "，必要时小步调整"),
            ("直接追产引发波动放大", "避免直接追产引发波动放大"),
            ("高权重持续失。", "高权重持续失衡。"),
            ("），温度场突变。", "），避免温度场突变。"),
            ("时序：/出口", "时序：进/出口"),
            ("程边界监控", "全程边界监控"),
            ("快+分级回退", "快照+分级回退"),
            ("时执行检修切换预案", "必要时执行检修切换预案"),
            ("检修命", "检修流程"),
            ("数据偏差驱动误操作", "避免数据偏差驱动误操作"),
            ("链条晰", "链条清晰"),
        ]

        cleaned = text
        for source, target in phrase_map:
            cleaned = cleaned.replace(source, target)
        cleaned = re.sub(r"(?<=[\u4e00-\u9fffA-Za-z0-9#])\s*[￾�]+\s*(?=[\u4e00-\u9fffA-Za-z0-9#])", "-", cleaned)
        cleaned = re.sub(r"[（(]?\s*置信度[:：]?\s*\d+(?:\.\d+)?%?\s*[)）]?", "", cleaned)
        cleaned = cleaned.replace("机理一致性复核：机理一致性复核：", "机理一致性复核：")
        cleaned = cleaned.replace("应及必要时", "必要时")
        cleaned = re.sub("\u5e94\u53ca\u5fc5\u8981\u65f6", "\u5fc5\u8981\u65f6", cleaned)

        cleaned = re.sub(r"\bstable\b", "稳定", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bconstrained\b", "受限", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bsuboptimal\b", "欠优", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\battention\b", "关注", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\boptimizable\b", "可优化", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\boptimal\b", "最优", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\babnormal_unstable\b", "异常失稳态", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\brisk_rising\b", "风险上升态", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bcritical\b", "高风险", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bwarning\b", "预警", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\btarget_reference\b", "目标参考值", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhistory_baseline\b", "历史运行基线", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\boptimal_reference\b", "优态基线", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\babnormal_ratio\b", "异常占比", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bavg_severity\b", "平均严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bmax_severity\b", "最大严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bcurrent_max_severity\b", "当前最大严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bseverity_score\b", "严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhybrid_severity\b", "混合严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhybrid_max_severity\b", "混合最大严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhybrid_avg_severity\b", "混合平均严重度", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bavg_optimal_gap\b", "平均优态偏离", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhistory_warning_count\b", "历史预警数", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bconflict_indicator_count\b", "规则/历史冲突指标数", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\brisk_upgrade_applied\b", "是否触发统计升级", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bselected_regime\b", "工况档位", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bprofile_source\b", "画像来源", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\banchor_tag\b", "锚点指标", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bglobal_fallback_used\b", "是否回退全局基线", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bstatistical_state\b", "历史统计状态", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bstatistical_score\b", "统计异常分数", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bagreement_flag\b", "规则/历史一致性", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\blow\b", "低负荷", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bnominal\b", "常规负荷", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhigh\b", "高负荷", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bcache\b", "缓存", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bruntime\b", "在线生成", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bincreasing\b", "上升", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bdecreasing\b", "下降", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bagree\b", "一致", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\brule_only\b", "仅规则命中", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhistory_only\b", "仅历史命中", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bconflict\b", "规则/历史冲突", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\btraceable_unvalidated\b", "可追溯待标定", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bPassed\b", "通过", cleaned)
        cleaned = re.sub(r"\bFailed\b", "未通过", cleaned)
        cleaned = re.sub(r"\bPending\b", "待现场验证", cleaned)
        cleaned = re.sub(r"\bpending\b", "待现场验证", cleaned)
        cleaned = re.sub(r"\babnormal\b", "异常", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bhealthy\b", "正常", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\berror\b", "错误", cleaned, flags=re.IGNORECASE)

        out_chars: List[str] = []
        for ch in cleaned:
            code = ord(ch)
            if ch in ("\n", "\r", "\t"):
                out_chars.append(ch)
                continue
            if code < 32 or (0x7F <= code <= 0x9F):
                out_chars.append(" ")
                continue
            if (0xFDD0 <= code <= 0xFDEF) or (code & 0xFFFE) == 0xFFFE:
                out_chars.append(" ")
                continue
            out_chars.append(ch)

        cleaned = "".join(out_chars)
        cleaned = re.sub(r"([\u4e00-\u9fff])\1{2,}", r"\1", cleaned)
        cleaned = re.sub(r"([\u4e00-\u9fff]{2,4})\1{2,}", r"\1", cleaned)
        cleaned = re.sub(r"(必要)+时", "必要时", cleaned)
        normalized_lines = []
        for line in cleaned.splitlines():
            leading_spaces = len(line) - len(line.lstrip(" "))
            prefix = line[:leading_spaces]
            core = re.sub(r"[ \t]{2,}", " ", line[leading_spaces:]).strip()
            normalized_lines.append(f"{prefix}{core}" if core else "")
        result = "\n".join(normalized_lines)
        result = result.replace("应及必要时", "必要时")
        if cleaned.endswith("\n"):
            result += "\n"
        return result

    def _clean_retrieval_summary(self, value: Any) -> str:
        text = self._stringify(value, "未返回检索结论。")
        text = text.replace("知识检索：", "检索结论：").replace("复核检索：", "复核结论：")
        text = re.sub(r"^检索结论[:：]\s*", "", text)
        text = re.sub(r"^复核结论[:：]\s*", "", text)
        if len(text) > 360:
            return f"{text[:360].rstrip()}..."
        return text

    def _localize_report_text(self, value: Any) -> str:
        return self._single_line_text(value, "").strip()

    def _localize_report_value(self, value: Any, default: str = "-") -> str:
        text = self._stringify(value, "").strip()
        if not text:
            return default
        localized = self._localize_report_text(text)
        return localized or default

    def _format_bool_zh(self, value: Any) -> str:
        return "是" if bool(value) else "否"

    def _normalize_knowledge_references(self, references: List[Any]) -> List[str]:
        normalized: List[str] = []
        for item in references or []:
            if isinstance(item, dict):
                source = self._stringify(item.get("source") or item.get("title"), "未标注来源")
                locator = self._stringify(item.get("page") or item.get("section") or item.get("chapter"), "")
                snippet = self._stringify(
                    item.get("content")
                    or item.get("snippet")
                    or item.get("summary")
                    or item.get("quote")
                    or item.get("matched_text"),
                    "",
                )
                ref_id = self._stringify(
                    item.get("clause_id")
                    or item.get("case_id")
                    or item.get("reference_id")
                    or item.get("doc_id")
                    or "",
                    "",
                )
                if not ref_id:
                    ref_id = self._extract_reference_id(source)
                if not snippet:
                    snippet = "命中片段未返回，请补充原文摘录。"

                fields: List[str] = [
                    f"来源：{source}",
                    f"条款/案例编号：{ref_id or '未标注'}",
                ]
                if locator:
                    fields.append(f"位置：{locator}")
                fields.append(f"命中片段：{snippet}")
                normalized.append("；".join(fields))
                continue
            if item is None:
                continue
            source = self._stringify(item)
            ref_id = self._extract_reference_id(source)
            normalized.append(
                f"来源：{source}；条款/案例编号：{ref_id or '未标注'}；命中片段：命中片段未返回，请补充原文摘录。"
            )
        return [item for item in normalized if item]

    def _extract_reference_id(self, text: str) -> str:
        value = self._stringify(text, "").strip()
        if not value:
            return ""

        patterns = [
            r"(SOP[-_ ]?\d+(?:\.\d+)*)",
            r"(CASE[-_ ]?[A-Za-z0-9]+)",
            r"(案例[-_ ]?[A-Za-z0-9]+)",
            r"(第\s*\d+(?:\.\d+){0,3}\s*条)",
            r"([A-Za-z]{2,}[-_ ]?\d{2,}(?:\.\d+)*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                return re.sub(r"\s+", "", match.group(1))
        return ""

    def _measure_signature(self, measure: Dict[str, Any]) -> Tuple[str, str, str]:
        title = self._stringify(measure.get("title"), "")
        issue = self._stringify(measure.get("target_issue"), "")
        steps = self._single_line_text(measure.get("steps"), "")
        combined = f"{title}|{issue}|{steps[:120]}"
        normalize_pattern = r"[\s，。；;:：、,()（）\[\]【】\-_/]+"
        stopwords = r"(立即|马上|启动|执行|流程|处置|检查|排查|处理|优化|建议|措施)"
        normalized = re.sub(normalize_pattern, "", combined)
        normalized = re.sub(stopwords, "", normalized)
        issue_key = re.sub(normalize_pattern, "", issue).lower()
        title_key = re.sub(stopwords, "", re.sub(normalize_pattern, "", title)).lower()
        return normalized.lower(), issue_key, title_key

    def _dedupe_recommended_measures(self, measures: List[Any]) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        signatures: List[Tuple[str, str, str]] = []
        seen_issue_signatures = set()
        seen_theme_keys = set()
        for raw in measures or []:
            if not isinstance(raw, dict):
                continue
            signature, issue_signature, title_signature = self._measure_signature(raw)
            if not signature:
                continue
            title_text = self._stringify(raw.get("title"), "")
            steps_text = self._single_line_text(raw.get("steps"), "")
            theme_key = ""
            if "高风险处置流程" in title_text or "高风险处置流程" in steps_text:
                theme_key = "high_risk_disposal"
            if theme_key and theme_key in seen_theme_keys:
                continue
            if issue_signature and issue_signature in seen_issue_signatures:
                continue

            duplicated = False
            for prev_signature, prev_issue, prev_title in signatures:
                similarity = difflib.SequenceMatcher(None, signature, prev_signature).ratio()
                same_issue = bool(issue_signature and prev_issue and issue_signature == prev_issue)
                same_title = bool(title_signature and prev_title and title_signature == prev_title)
                if (
                    similarity >= 0.92
                    or (same_issue and similarity >= 0.70)
                    or same_title
                ):
                    duplicated = True
                    break
            if duplicated:
                continue

            kept.append(raw)
            signatures.append((signature, issue_signature, title_signature))
            if issue_signature:
                seen_issue_signatures.add(issue_signature)
            if theme_key:
                seen_theme_keys.add(theme_key)
        return kept

    def _first_compact_clause(self, value: Any, fallback: str = "") -> str:
        text = self._single_line_text(value, "").replace("|", "；").strip()
        if not text:
            return fallback
        fragments = [part.strip() for part in re.split(r"[\n；;]", text) if part.strip()]
        if not fragments:
            return fallback
        selected = re.sub(r"^[•\-–—\s\d\.\)\(（）、]+", "", fragments[0]).strip()
        return selected or fallback

    def _soften_root_cause_text(self, value: Any) -> str:
        # Root-cause wording must be downgraded upstream. The report generator only renders.
        return self._stringify(value, "").strip()

    def _is_low_signal_evidence_snippet(self, value: Any) -> bool:
        text = self._single_line_text(value, "").strip()
        if not text:
            return True
        low_signal_patterns = (
            "编辑性修改",
            "全部控制合格",
            "操作中失误造成",
            "粗实线为改造后新增部分",
            "细实线为改造前",
            "图中粗实线",
            "图中细实线",
            "对原标准做了编辑性修改",
        )
        return any(pattern in text for pattern in low_signal_patterns)

    def _find_clause_by_keywords(self, values: Iterable[Any], keywords: Iterable[str], fallback: str = "") -> str:
        keyword_list = [str(item) for item in keywords if str(item).strip()]
        for value in values:
            text = self._expand_escaped_newlines(self._render_operator_text(value, "")).replace("\r\n", "\n")
            for raw_line in re.split(r"[\n；;]", text):
                line = re.sub(r"^[•\-–—\s\d\.\)\(（）、]+", "", self._clean_business_text(raw_line)).strip()
                if line and any(keyword in line for keyword in keyword_list):
                    return line
        return fallback

    def _compact_knowledge_reference(self, item: Any) -> str:
        if isinstance(item, dict):
            source = self._stringify(item.get("source") or item.get("title"), "未标注来源")
            locator = self._stringify(item.get("page") or item.get("section") or item.get("chapter"), "").strip()
            snippet = self._short_text(
                self._single_line_text(
                    item.get("content")
                    or item.get("snippet")
                    or item.get("summary")
                    or item.get("quote")
                    or item.get("matched_text"),
                    "未返回依据摘录",
                ),
                "未返回依据摘录",
                limit=88,
            )
            if locator:
                return f"{source} {locator}：{snippet}"
            return f"{source}：{snippet}"
        source, locator, snippet = self._reference_context(item)
        locator_text = f" {locator}" if locator else ""
        return f"{source}{locator_text}：{snippet}"

    def _review_section_label(self) -> str:
        return "机理一致性复核"

    def _dedupe_text_items(self, items: Iterable[str], limit: Optional[int] = None) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in items:
            text = self._stringify(raw, "").strip()
            if not text:
                continue
            normalized = re.sub(r"\s+", "", text)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(text)
            if limit is not None and len(deduped) >= limit:
                break
        return deduped

    def _reference_context(self, item: Any) -> Tuple[str, str, str]:
        if isinstance(item, dict):
            source = self._stringify(item.get("source") or item.get("title"), "未标注来源")
            locator = self._stringify(item.get("page") or item.get("section") or item.get("chapter"), "").strip()
            snippet = self._single_line_text(
                item.get("content")
                or item.get("snippet")
                or item.get("summary")
                or item.get("quote")
                or item.get("matched_text"),
                "未返回依据摘录",
            )
            return source, locator, snippet

        text = self._stringify(item, "").strip()
        if not text:
            return "未标注来源", "", "未返回依据摘录"
        compact = self._single_line_text(text, text).strip("。 ")
        match = re.match(r"^(?P<source>.+?)[（(](?P<snippet>.+?)[)）]$", compact)
        if match:
            source = match.group("source").strip("：: ")
            snippet = match.group("snippet").strip("。 ")
            return source or compact, "", snippet or compact
        return compact, "", compact

    def _map_reference_to_support(self, item: Any) -> Dict[str, Any]:
        source, locator, snippet = self._reference_context(item)
        text = f"{source} {snippet}"
        judgement: List[str] = []
        actions: List[str] = []

        if any(keyword in text for keyword in ("过滤器", "堵塞", "入口压力", "入口阀门", "阀门未全开")):
            judgement.append("支持“膨胀机B入口受阻或过滤器堵塞”判断")
            actions.append("约束“先查入口过滤器压差与阀门开度，再决定切换备用或停车清理”")
        if any(keyword in text for keyword in ("主换", "温差", "冷损")):
            judgement.append("支持“主换冷损升高是冷量缺口放大的次生表现”判断")
        if any(keyword in text for keyword in ("液氩", "精馏", "提取率", "分离效率")):
            judgement.append("支持“液氩产量下降是冷量不足向分离侧传导的结果”判断")
        if "液体产量比例" in text or "3%" in text:
            actions.append("约束“单机运行或冷量受限时，将液体产量比例压至3%以下”")
        if any(keyword in text for keyword in ("主冷液位", "液位", "液氧罐", "反送液氧", "液面达到正常值")):
            actions.append("约束“主冷液位必须优先守住，必要时启动液氧反送”")
        if any(keyword in text for keyword in ("联锁", "审批", "授权", "边界")):
            actions.append("约束“所有调整动作必须先校验联锁边界与审批条件”")
        if any(keyword in text for keyword in ("先稳负荷", "后调优", "小步调整", "单变量")):
            actions.append("约束“先稳负荷后调优，按单变量小步调整执行”")

        snippet_text = self._short_text(snippet, "未返回依据摘录", limit=88)
        if self._is_text_noisy(snippet_text):
            snippet_text = "原文含公式或符号噪声，报告中仅保留与当前诊断相关的结论映射"

        return {
            "source": source,
            "locator": locator,
            "snippet": snippet_text,
            "judgement": self._dedupe_text_items(judgement, limit=2),
            "actions": self._dedupe_text_items(actions, limit=2),
        }

    def _build_overall_review_lines(self, overall_judgement: Dict[str, Any]) -> List[Tuple[str, str]]:
        if not overall_judgement:
            return []

        summary_text = self._stringify(overall_judgement.get("summary"), "").strip()
        summary_sections = self._split_pipe_sections(summary_text) if summary_text else []
        lines: List[Tuple[str, str]] = []
        if summary_sections:
            lines.append(("总体结论", summary_sections[0]))
            review_texts = self._dedupe_text_items(
                [
                    self._normalize_expert_review_text(part)
                    for part in summary_sections[1:]
                    if self._normalize_expert_review_text(part)
                ],
                limit=2,
            )
            if review_texts:
                lines.append((self._review_section_label(), "；".join(review_texts)))

        highlights = self._dedupe_text_items(
            [
                self._short_text(self._normalize_expert_review_text(line), "", limit=90)
                for line in (overall_judgement.get("highlights") or [])[:3]
                if self._short_text(self._normalize_expert_review_text(line), "", limit=90)
            ],
            limit=2,
        )
        if highlights:
            lines.append(("关键偏离", "；".join(highlights)))

        return lines

    def _extract_text_clauses(self, text: Any, *, limit: int = 4) -> List[str]:
        normalized = self._stringify(text, "").strip()
        if not normalized:
            return []
        normalized = self._expand_escaped_newlines(normalized)
        parts = [
            re.sub(r"^\d+[\).\s、]+", "", part).strip("；。 ")
            for part in re.split(r"[\n；;。]", normalized)
            if part and part.strip("；。 ")
        ]
        return self._dedupe_text_items([part for part in parts if part], limit=limit)

    def _format_baseline_reference_item(self, item: Any) -> str:
        if not isinstance(item, dict):
            return self._stringify(item, "").strip()
        prebuilt = self._stringify(item.get("text"), "").strip()
        if prebuilt:
            return prebuilt
        indicator = self._stringify(item.get("indicator"), "未命名指标")
        source = self._stringify(item.get("target_reference_label") or item.get("reference_source_label"), "未标注参考")
        value = self._safe_float(item.get("reference_value"))
        history_baseline = self._safe_float(item.get("history_baseline"))
        optimal_reference = self._safe_float(item.get("optimal_reference"))
        final_grade_basis = self._stringify(item.get("final_grade_basis_label"), "").strip()
        scope = self._stringify(item.get("reference_scope"), "未标注适用范围")
        comparison = self._stringify(item.get("comparison_method"), "未标注比较口径")
        value_text = f"（{self._format_number(value)}）" if value is not None else ""
        parts = [f"{indicator}：目标参考值={source}{value_text}"]
        if history_baseline is not None:
            parts.append(f"历史运行基线={self._format_number(history_baseline)}")
        if optimal_reference is not None:
            parts.append(f"优态基线={self._format_number(optimal_reference)}")
        if final_grade_basis:
            parts.append(f"最终判级依据={final_grade_basis}")
        parts.append(f"适用范围={scope}")
        parts.append(f"比较口径={comparison}")
        return "；".join(parts)

    def _format_reference_provenance_item(self, item: Any) -> str:
        if not isinstance(item, dict):
            return self._stringify(item, "").strip()
        prebuilt = self._stringify(item.get("text"), "").strip()
        if prebuilt:
            return prebuilt
        indicator = self._stringify(item.get("indicator_name") or item.get("indicator"), "未命名指标")
        reference_value = self._safe_float(item.get("reference_value"))
        basis_kind = self._stringify(item.get("reference_basis_kind_label") or item.get("reference_basis_kind"), "未声明来源性质")
        basis_text = self._stringify(item.get("reference_basis_text"), "未声明来源性质，仅按当前配置参考值执行；该参考值当前用于工程规则判级，不代表已完成统计标定。")
        scope = self._stringify(item.get("applicable_scope"), "未标注适用范围")
        conditions = self._stringify(item.get("applicable_conditions"), "未声明")
        comparison_basis = self._stringify(item.get("comparison_basis"), "未标注比较口径")
        final_basis = self._stringify(item.get("final_grading_basis"), "目标参考值")
        validation = self._localize_report_value(item.get("validation_status_label") or item.get("validation_status"), "可追溯待标定")
        parts = [
            f"{indicator}：参考值={self._format_number(reference_value) if reference_value is not None else '-'}",
            f"来源性质={basis_kind}",
            f"来源说明={basis_text}",
            f"适用范围={scope}",
            f"适用边界={conditions}",
            f"比较口径={comparison_basis}",
            f"最终判级依据={final_basis}",
            f"成熟度={validation}",
        ]
        owner = self._stringify(item.get("reference_owner"), "").strip()
        reviewed_at = self._stringify(item.get("last_reviewed_at"), "").strip()
        if owner:
            parts.append(f"维护责任={owner}")
        if reviewed_at:
            parts.append(f"最近复核={reviewed_at}")
        return "；".join(parts)

    def _format_reference_framework_item(self, item: Any) -> str:
        if not isinstance(item, dict):
            return self._stringify(item, "").strip()
        name = self._stringify(item.get("name"), "未命名基准")
        purpose = self._stringify(item.get("purpose"), "").strip()
        priority = self._stringify(item.get("priority"), "").strip()
        drives_grading = bool(item.get("drives_grading"))
        suffix = "作为最终判级依据" if drives_grading else "不直接决定异常级别"
        if suffix and suffix in purpose:
            suffix = ""
        if priority and purpose:
            return f"{name}（优先级 {priority}）：{purpose}{suffix and f'；{suffix}'}"
        if purpose:
            return f"{name}：{purpose}{suffix and f'；{suffix}'}"
        return name

    def _format_state_rule_item(self, item: Any) -> str:
        if not isinstance(item, dict):
            return self._stringify(item, "").strip()
        stage = self._localize_report_value(item.get("stage"), "规则")
        description = self._localize_report_text(item.get("description"))
        rule_id = self._localize_report_text(item.get("rule_id"))
        if rule_id and description:
            return f"{stage}（{rule_id}）：{description}"
        if description:
            return f"{stage}：{description}"
        return stage

    def _format_rule_parameter_explanation_item(self, item: Any) -> str:
        if not isinstance(item, dict):
            return self._stringify(item, "").strip()
        prebuilt = self._stringify(item.get("text"), "").strip()
        if prebuilt:
            return prebuilt
        title = self._localize_report_value(item.get("title"), "规则说明")
        rule_name = self._localize_report_text(item.get("rule_name"))
        rule_version = self._stringify(item.get("rule_version"), "").strip()
        matched_branch = self._localize_report_text(item.get("matched_branch"))
        output = self._localize_report_text(item.get("output"))
        title_suffix = f"{rule_name}@{rule_version}" if rule_name and rule_version else rule_name or rule_version
        head = f"{title}：{title_suffix}" if title_suffix else title
        parts = [head]
        if matched_branch:
            parts.append(f"命中分支={matched_branch}")
        current_inputs = self._localize_report_text(item.get("current_inputs"))
        if current_inputs:
            parts.append(f"当前输入={current_inputs}")
        thresholds = self._localize_report_text(item.get("thresholds") or item.get("weights"))
        if thresholds:
            parts.append(f"规则参数={thresholds}")
        if output:
            parts.append(f"输出结果={output}")
        origin = self._localize_report_text(item.get("origin_statement"))
        if origin:
            parts.append(origin)
        return "；".join(parts)

    def _format_dominant_anomaly_explanation_items(self, item: Any) -> List[str]:
        if not isinstance(item, dict):
            text = self._stringify(item, "").strip()
            return [text] if text else []
        sections: List[str] = []
        candidate_label = self._stringify(item.get("candidate_label"), "").strip()
        if candidate_label:
            sections.append(f"主导异常判读：{candidate_label}")
        mapping = (
            ("rank_explanation", "排序依据"),
            ("duration_explanation", "持续性依据"),
            ("subsystem_impact_explanation", "子系统影响"),
            ("coupling_consistency_explanation", "耦合一致性"),
            ("temporal_precedence_explanation", "时间先后性"),
            ("exclusion_boundary_explanation", "边界说明"),
        )
        for key, label in mapping:
            text = self._stringify(item.get(key), "").strip()
            if text:
                sections.append(f"{label}：{text}")
        text_sections = item.get("text_sections")
        if not sections and isinstance(text_sections, list):
            sections.extend(self._dedupe_text_items([self._stringify(value, "").strip() for value in text_sections if self._stringify(value, "").strip()], limit=7))
        return sections

    def _format_verification_loop_items(self, verification_loop: Dict[str, Any]) -> List[str]:
        if not isinstance(verification_loop, dict):
            return []
        section_labels = {
            "check_first": "先核查",
            "observe": "观察",
            "success_criteria": "验收",
            "rollback_triggers": "回退",
        }
        rendered: List[str] = []
        for key, label in section_labels.items():
            values = verification_loop.get(key)
            if not values:
                continue
            if not isinstance(values, list):
                values = [values]
            cleaned = [self._single_line_text(item, "").strip() for item in values if self._single_line_text(item, "").strip()]
            if cleaned:
                rendered.append(f"{label}：{'；'.join(cleaned[:3])}")
        return rendered

    def _calculation_audit_payload(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        audit = analysis_result.get("calculation_audit")
        if isinstance(audit, dict) and audit:
            return audit
        overall = analysis_result.get("overall_judgement") or {}
        audit = overall.get("calculation_audit")
        return audit if isinstance(audit, dict) else {}

    def _format_calculation_data_intake_items(self, audit: Dict[str, Any]) -> List[str]:
        intake = audit.get("data_intake") or {}
        if not isinstance(intake, dict) or not intake:
            return []
        items = [
            f"布局识别={self._stringify(intake.get('layout_detected'), '未记录')}",
            f"数据起始行={self._stringify(intake.get('data_start_row'), '未记录')}",
            f"设计参考值行={self._stringify(intake.get('design_ref_row'), '未识别')}",
            (
                f"纳入时间范围={self._stringify(intake.get('first_included_timestamp'), '未记录')} 至 "
                f"{self._stringify(intake.get('last_included_timestamp'), '未记录')}"
            ),
            f"记录数：门禁前={self._stringify(intake.get('record_count_before_gate'), '未记录')}，门禁后={self._stringify(intake.get('record_count_after_gate'), '未记录')}",
            f"时间点数：门禁前={self._stringify(intake.get('timepoint_count_before_gate'), '未记录')}，门禁后={self._stringify(intake.get('timepoint_count_after_gate'), '未记录')}",
            self._stringify(intake.get("count_change_reason"), "").strip(),
        ]
        dropped_rows = intake.get("dropped_rows") or []
        if isinstance(dropped_rows, list) and dropped_rows:
            rendered = []
            for row in dropped_rows[:6]:
                if isinstance(row, dict):
                    rendered.append(f"row={self._stringify(row.get('row_index'), '-')}, reason={self._stringify(row.get('reason'), '-')}")
                else:
                    rendered.append(self._stringify(row, "").strip())
            if rendered:
                items.append(f"排除行：{'；'.join(rendered)}")
        return [item for item in items if item]

    def _calculation_indicator_rows(self, audit: Dict[str, Any]) -> List[List[str]]:
        indicators = audit.get("indicators") or []
        if not isinstance(indicators, list) or not indicators:
            return []
        rows: List[List[str]] = [["指标", "当前值", "目标参考", "历史中位", "优态基线", "判级依据", "状态", "严重度"]]
        for item in indicators:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    self._stringify(item.get("name"), "未命名指标"),
                    self._format_number(self._safe_float(item.get("current_value"))),
                    self._format_number(self._safe_float(item.get("target_reference"))),
                    self._format_number(self._safe_float(item.get("history_baseline"))),
                    self._format_number(self._safe_float(item.get("optimal_reference"))),
                    self._stringify(item.get("final_grade_basis_label"), "-"),
                    self._stringify(item.get("state_label"), "-"),
                    self._format_number(self._safe_float(item.get("severity_score")), digits=3),
                ]
            )
        return rows

    def _format_history_judgement_items(self, audit: Dict[str, Any]) -> List[str]:
        items: List[str] = []
        metadata = audit.get("history_model_metadata") or {}
        if isinstance(metadata, dict) and metadata:
            regime = self._localize_report_value(metadata.get("selected_regime"), "未记录")
            source = self._localize_report_value(metadata.get("profile_source"), "未记录")
            anchor_tag = self._stringify(metadata.get("anchor_tag"), "未记录")
            fallback = self._format_bool_zh(metadata.get("global_fallback_used"))
            items.append(f"历史画像：画像来源={source}；工况档位={regime}；锚点指标={anchor_tag}；是否回退全局基线={fallback}")
        indicators = audit.get("indicators") or []
        ranked = []
        for item in indicators:
            if not isinstance(item, dict):
                continue
            score = self._safe_float(item.get("statistical_anomaly_score"))
            ranked.append((score if score is not None else -1.0, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        for _, item in ranked[:6]:
            statistical_state = self._localize_report_text(item.get("statistical_state"))
            agreement_flag = self._localize_report_text(item.get("agreement_flag"))
            if not statistical_state and not agreement_flag:
                continue
            items.append(
                f"{self._stringify(item.get('name'), '未命名指标')}：工况档位={self._localize_report_value(item.get('selected_regime'), '-')}"
                f"；历史统计状态={statistical_state or '-'}"
                f"；统计异常分数={self._format_number(self._safe_float(item.get('statistical_anomaly_score')), digits=3)}"
                f"；规则/历史一致性={agreement_flag or '-'}"
                f"；混合严重度={self._format_number(self._safe_float(item.get('hybrid_severity_score')), digits=3)}"
            )
        return items

    def _build_markdown_table(self, rows: List[List[str]]) -> List[str]:
        if not rows:
            return []
        header = rows[0]
        content = [
            "|" + "|".join(header) + "|\n",
            "|" + "|".join(["---"] * len(header)) + "|\n",
        ]
        for row in rows[1:]:
            content.append("|" + "|".join(self._stringify(cell, "-").replace("|", "/") for cell in row) + "|\n")
        return content

    def _format_subsystem_audit_items(self, audit: Dict[str, Any]) -> List[str]:
        subsystems = audit.get("subsystems") or []
        rendered: List[str] = []
        for item in subsystems:
            if not isinstance(item, dict):
                continue
            members = item.get("members") or []
            members_text = "、".join(str(member) for member in members[:8]) if members else "未记录成员"
            triggers = "；".join(str(trigger) for trigger in (item.get("triggered_by") or [])[:3]) or "未触发显式阈值"
            rendered.append(
                f"{self._stringify(item.get('name'), '未命名子系统')}：成员={members_text}；"
                f"异常数={self._stringify(item.get('abnormal_count'), 0)}/{self._stringify(item.get('total_count'), 0)}；"
                f"异常占比={self._format_percent(self._safe_float(item.get('abnormal_ratio')))}；"
                f"平均严重度={self._format_number(self._safe_float(item.get('avg_severity')), digits=3)}；"
                f"混合平均严重度={self._format_number(self._safe_float(item.get('hybrid_avg_severity')), digits=3)}；"
                f"历史预警数={self._stringify(item.get('history_warning_count'), 0)}；"
                f"规则/历史冲突指标数={self._stringify(item.get('conflict_indicator_count'), 0)}；"
                f"状态={self._localize_report_value(item.get('state'), '未标注')}；"
                f"命中分支={self._localize_report_text(triggers)}"
            )
        return rendered

    def _format_plant_audit_items(self, audit: Dict[str, Any]) -> List[str]:
        plant = audit.get("plant") or {}
        if not isinstance(plant, dict) or not plant:
            return []
        dominant = plant.get("dominant_anomaly") or {}
        items = [
            (
                f"装置层：异常占比={self._format_percent(self._safe_float(plant.get('abnormal_ratio')))}；"
                f"最大严重度={self._format_number(self._safe_float(plant.get('max_severity')), digits=3)}；"
                f"混合最大严重度={self._format_number(self._safe_float(plant.get('hybrid_max_severity')), digits=3)}；"
                f"平均优态偏离={self._format_percent(self._safe_float(plant.get('avg_optimal_gap')))}；"
                f"风险等级={self._stringify(plant.get('risk_level_label'), '-')}（分支={self._localize_report_value(plant.get('risk_branch'), '-')})；"
                f"装置状态={self._stringify(plant.get('plant_state_label'), '-')}（分支={self._localize_report_value(plant.get('plant_state_branch'), '-')})；"
                f"历史预警数={self._stringify(plant.get('history_warning_count'), 0)}；"
                f"规则/历史冲突指标数={self._stringify(plant.get('conflict_indicator_count'), 0)}；"
                f"是否触发统计升级={self._format_bool_zh(plant.get('risk_upgrade_applied'))}"
            ),
            f"主导异常：{self._stringify(dominant.get('indicator_name'), '未识别')}；{self._stringify(dominant.get('candidate_label'), '未识别候选')}",
            f"时间先后性：{self._stringify(dominant.get('temporal_precedence_explanation'), '未记录')}",
        ]
        main_contradiction = self._stringify(plant.get("main_contradiction"), "").strip()
        if main_contradiction:
            items.append(f"主导矛盾：{main_contradiction}")
        boundary = self._stringify(dominant.get("boundary"), "").strip()
        if boundary:
            items.append(f"边界说明：{boundary}")
        return [item for item in items if item]

    def _visualization_cards(self, analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        context = analysis_result.get("visualization_context") or {}
        cards = context.get("top_indicator_cards") or []
        return [item for item in cards if isinstance(item, dict)]

    def _data_curve_overview_payload(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        context = analysis_result.get("visualization_context") or {}
        payload = context.get("data_curve_overview") or {}
        return payload if isinstance(payload, dict) else {}

    def _build_data_curve_overview_sections(self, analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        overview = self._data_curve_overview_payload(analysis_result)
        categories = overview.get("categories") or []
        if not isinstance(categories, list):
            return []
        asset_dir = Path(str(analysis_result.get("_report_asset_dir") or Path(self.output_dir) / "assets" / "report"))
        asset_prefix = str(analysis_result.get("_report_asset_prefix") or "assets/report").strip()
        sections: List[Dict[str, Any]] = []
        for category in categories:
            if not isinstance(category, dict):
                continue
            image_info = self._render_data_curve_category_image(category=category, asset_dir=asset_dir, asset_prefix=asset_prefix)
            sections.append(
                {
                    "title": self._stringify(category.get("title"), "未命名分类"),
                    "summary_lines": self._format_data_curve_category_summary(category),
                    **image_info,
                }
            )
        return sections

    def _format_visualization_metric(self, value: Any, unit: str = "") -> str:
        number = self._safe_float(value)
        if number is None:
            return "-"
        unit_suffix = f" {unit}" if unit else ""
        return f"{self._format_number(number)}{unit_suffix}"

    def _format_visualization_percent(self, value: Any) -> str:
        number = self._safe_float(value)
        if number is None:
            return "-"
        return f"{number:+.1f}%"

    def _format_percentile_rank_text(self, value: Any) -> str:
        number = self._safe_float(value)
        if number is None:
            return "-"
        return f"{number:.1f}%位"

    def _format_visualization_card_summary(self, card: Dict[str, Any]) -> List[str]:
        references = card.get("references") or {}
        history_stats = card.get("history_stats") or {}
        deltas = card.get("comparison_deltas") or {}
        unit = self._stringify(card.get("unit"), "").strip()
        lines = [
            (
                f"当前值={self._format_visualization_metric(card.get('current_value'), unit)}；"
                f"历史中位={self._format_visualization_metric(history_stats.get('median'), unit)}；"
                f"目标参考={self._format_visualization_metric(references.get('target_reference'), unit)}；"
                f"优态参考={self._format_visualization_metric(references.get('optimal_reference'), unit)}；"
                f"历史百分位={self._format_percentile_rank_text(history_stats.get('percentile_rank'))}"
            )
        ]
        if (card.get("recent_trend") or {}).get("abnormal_start_outside_window"):
            lines.append("异常开始早于当前图窗。")
        insight_text = self._stringify(card.get("insight_text"), "").strip()
        if insight_text:
            lines.append(insight_text)
        history_delta = ((deltas.get("vs_history_median") or {}).get("percent"))
        target_delta = ((deltas.get("vs_target") or {}).get("percent"))
        optimal_delta = ((deltas.get("vs_optimal") or {}).get("percent"))
        delta_parts = []
        if history_delta is not None:
            delta_parts.append(f"相对历史中位={self._format_visualization_percent(history_delta)}")
        if target_delta is not None:
            delta_parts.append(f"相对目标参考={self._format_visualization_percent(target_delta)}")
        if optimal_delta is not None:
            delta_parts.append(f"相对优态参考={self._format_visualization_percent(optimal_delta)}")
        if delta_parts:
            lines.append("；".join(delta_parts))
        return lines

    def _append_markdown_visualization_section(self, content: List[str], analysis_result: Dict[str, Any]) -> None:
        cards = self._visualization_cards(analysis_result)
        content.append("\n## 时间对比可视化\n")
        content.append("- 说明: 以下图卡仅展示当前值、历史位置和目标/优态参考的对比关系，不等于根因确认。\n")
        if not cards:
            content.append("- 当前未生成可用的历史对比图。\n")
            return
        for index, card in enumerate(cards, start=1):
            title = self._stringify(card.get("indicator_name") or card.get("tag_id"), "未命名指标")
            content.append(f"\n### **{index}. {title}**\n")
            for line in self._format_visualization_card_summary(card):
                content.append(f"- {line}\n")
            image_relative_path = self._stringify(card.get("image_relative_path"), "").strip()
            if image_relative_path:
                content.append(f"![{title}]({image_relative_path})\n")
            else:
                content.append("- 当前未生成静态图像资产。\n")

    def _append_pdf_visualization_section(
        self,
        story: List[Any],
        *,
        styles: Dict[str, Any],
        visualization_cards: List[Dict[str, Any]],
        image_cls: Any,
        inch: Any,
    ) -> None:
        from reportlab.platypus import Paragraph, Spacer

        self._append_pdf_bullets(
            story,
            ["以下图卡仅展示当前值、历史位置和目标/优态参考的对比关系，不等于根因确认。"],
            styles["Bullet"],
        )
        if not visualization_cards:
            self._append_pdf_bullets(story, ["当前未生成可用的历史对比图。"], styles["Bullet"])
            return
        for index, card in enumerate(visualization_cards, start=1):
            title = self._stringify(card.get("indicator_name") or card.get("tag_id"), "未命名指标")
            story.append(Paragraph(f"{index}. {title}", styles["Heading3"]))
            self._append_pdf_bullets(story, self._format_visualization_card_summary(card), styles["Bullet"])
            image_path = self._stringify(card.get("image_path"), "").strip()
            if image_path and os.path.exists(image_path):
                story.append(image_cls(image_path, width=6.5 * inch, height=3.5 * inch))
                story.append(Spacer(1, 0.08 * inch))
            else:
                self._append_pdf_bullets(story, ["当前未生成静态图像资产。"], styles["Bullet"])

    def _append_pdf_data_curve_overview_section(
        self,
        story: List[Any],
        *,
        styles: Dict[str, Any],
        sections: List[Dict[str, Any]],
        image_cls: Any,
        inch: Any,
    ) -> None:
        from reportlab.platypus import Paragraph, Spacer

        if not sections:
            self._append_pdf_bullets(story, ["当前未生成整体数据曲线图。"], styles["Bullet"])
            return
        for index, section in enumerate(sections, start=1):
            title = self._stringify(section.get("title"), "未命名分类")
            story.append(Paragraph(f"{index}. {title}", styles["Heading3"]))
            self._append_pdf_bullets(story, section.get("summary_lines") or ["当前未记录该分类的摘要说明。"], styles["Bullet"])
            image_path = self._stringify(section.get("image_path"), "").strip()
            if image_path and os.path.exists(image_path):
                story.append(image_cls(image_path, width=6.6 * inch, height=3.8 * inch))
                story.append(Spacer(1, 0.08 * inch))
            else:
                self._append_pdf_bullets(story, ["当前未生成整体数据曲线图像资产。"], styles["Bullet"])

    def _format_data_curve_category_summary(self, category: Dict[str, Any]) -> List[str]:
        title = self._stringify(category.get("title"), "未命名分类")
        items = category.get("items") or []
        load_context_items = [item for item in (category.get("load_context_items") or []) if isinstance(item, dict)]
        indicator_count = self._stringify(category.get("indicator_count"), 0)
        abnormal_count = self._stringify(category.get("abnormal_count"), 0)
        time_range = self._extract_curve_category_time_range(items)
        summary = [
            f"{title}：纳入曲线 {indicator_count} 条，异常 {abnormal_count} 条，时间范围 {time_range}。",
            "同图曲线已统一换算为相对各自参考值的偏差百分比；多条曲线若同向波动，说明该分类内部相关性更强。",
            "图中包含 0% 基线、±10% 参考带和最早异常起点，便于同时判断偏离幅度与联动关系。",
        ]
        if load_context_items:
            summary.append(f"本图额外叠加 {len(load_context_items)} 条负荷参照曲线，用于观察该分类与装置负荷的联动关系。")
        correlation_text = self._curve_category_correlation_text(items, load_context_items=load_context_items)
        if correlation_text:
            summary.append(correlation_text)
        return summary

    def _extract_curve_category_time_range(self, items: List[Dict[str, Any]]) -> str:
        starts: List[str] = []
        ends: List[str] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            start = self._stringify(item.get("time_range_start"), "").strip()
            end = self._stringify(item.get("time_range_end"), "").strip()
            if start:
                starts.append(start)
            if end:
                ends.append(end)
        if not starts or not ends:
            return "未记录"
        return f"{min(starts)} -> {max(ends)}"

    def _curve_category_correlation_text(self, items: List[Dict[str, Any]], load_context_items: Optional[List[Dict[str, Any]]] = None) -> str:
        best_pair: Optional[Tuple[str, str, float]] = None
        prepared: List[Tuple[str, Dict[str, float]]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            label = self._compact_curve_label(item)
            timestamps = list(((item.get("chart") or {}).get("timestamps") or []))
            values = list(((item.get("chart") or {}).get("values") or []))
            if not timestamps or not values:
                continue
            reference = self._curve_normalization_reference(item)
            value_map: Dict[str, float] = {}
            for index in range(min(len(timestamps), len(values))):
                percent = self._relative_percent_for_curve(values[index], reference)
                if percent is not None:
                    value_map[str(timestamps[index])] = percent
            if len(value_map) >= 6:
                prepared.append((label, value_map))
        for left_index in range(len(prepared)):
            for right_index in range(left_index + 1, len(prepared)):
                left_label, left_map = prepared[left_index]
                right_label, right_map = prepared[right_index]
                common_keys = sorted(set(left_map.keys()) & set(right_map.keys()))
                if len(common_keys) < 6:
                    continue
                corr = self._pearson_correlation([left_map[key] for key in common_keys], [right_map[key] for key in common_keys])
                if corr is None:
                    continue
                if best_pair is None or abs(corr) > abs(best_pair[2]):
                    best_pair = (left_label, right_label, corr)
        messages: List[str] = []
        if best_pair:
            relation = "同向" if best_pair[2] >= 0 else "反向"
            messages.append(f"分类内相关性提示：{best_pair[0]} 与 {best_pair[1]} 的{relation}联动最明显（r={best_pair[2]:.2f}）。")

        load_pair = self._best_load_correlation(items, load_context_items or [])
        if load_pair:
            left_label, right_label, corr = load_pair
            relation = "同向" if corr >= 0 else "反向"
            messages.append(f"负荷相关性提示：{left_label} 与 {right_label} 的{relation}联动最明显（r={corr:.2f}）。")
        return " ".join(messages)

    def _best_load_correlation(self, items: List[Dict[str, Any]], load_context_items: List[Dict[str, Any]]) -> Optional[Tuple[str, str, float]]:
        if not items or not load_context_items:
            return None
        prepared_items = self._prepare_curve_value_maps(items)
        prepared_loads = self._prepare_curve_value_maps(load_context_items)
        best_pair: Optional[Tuple[str, str, float]] = None
        for left_label, left_map in prepared_items:
            for right_label, right_map in prepared_loads:
                common_keys = sorted(set(left_map.keys()) & set(right_map.keys()))
                if len(common_keys) < 6:
                    continue
                corr = self._pearson_correlation([left_map[key] for key in common_keys], [right_map[key] for key in common_keys])
                if corr is None:
                    continue
                if best_pair is None or abs(corr) > abs(best_pair[2]):
                    best_pair = (left_label, right_label, corr)
        return best_pair

    def _prepare_curve_value_maps(self, items: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, float]]]:
        prepared: List[Tuple[str, Dict[str, float]]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            label = self._compact_curve_label(item)
            timestamps = list(((item.get("chart") or {}).get("timestamps") or []))
            values = list(((item.get("chart") or {}).get("values") or []))
            if not timestamps or not values:
                continue
            reference = self._curve_normalization_reference(item)
            value_map: Dict[str, float] = {}
            for index in range(min(len(timestamps), len(values))):
                percent = self._relative_percent_for_curve(values[index], reference)
                if percent is not None:
                    value_map[str(timestamps[index])] = percent
            if len(value_map) >= 6:
                prepared.append((label, value_map))
        return prepared

    def _compact_curve_label(self, item: Dict[str, Any]) -> str:
        name = self._stringify(item.get("indicator_name"), "未命名指标").strip()
        if len(name) <= 18:
            return name
        parts = [part for part in re.split(r"[-/]", name) if part.strip()]
        return parts[-1].strip() if parts else name[-18:]

    def _curve_normalization_reference(self, item: Dict[str, Any]) -> float:
        reference = self._safe_float(item.get("reference_value"))
        if reference is not None and abs(reference) > 1e-6:
            return reference
        median = self._safe_float(((item.get("summary") or {}).get("median")))
        if median is not None and abs(median) > 1e-6:
            return median
        current = self._safe_float(item.get("current_value"))
        if current is not None and abs(current) > 1e-6:
            return current
        return 1.0

    def _relative_percent_for_curve(self, value: Any, reference: Optional[float]) -> Optional[float]:
        current = self._safe_float(value)
        if current is None or reference is None or abs(reference) <= 1e-6:
            return None
        return ((current - reference) / abs(reference)) * 100.0

    def _pearson_correlation(self, left: List[float], right: List[float]) -> Optional[float]:
        if len(left) != len(right) or len(left) < 2:
            return None
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        numerator = sum((l - left_mean) * (r - right_mean) for l, r in zip(left, right))
        left_den = math.sqrt(sum((l - left_mean) ** 2 for l in left))
        right_den = math.sqrt(sum((r - right_mean) ** 2 for r in right))
        if left_den <= 1e-9 or right_den <= 1e-9:
            return None
        return numerator / (left_den * right_den)

    def _render_data_curve_category_image(self, *, category: Dict[str, Any], asset_dir: Path, asset_prefix: str) -> Dict[str, Any]:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.font_manager import FontProperties
        except Exception:
            return {"image_path": "", "image_relative_path": "", "image_status": "matplotlib_unavailable"}

        asset_dir.mkdir(parents=True, exist_ok=True)
        safe_key = self._slugify(category.get("key") or category.get("title") or "category")
        filename = f"{safe_key}_overall_curve.png"
        image_path = asset_dir / filename
        font_prop = self._resolve_report_plot_font(FontProperties)

        fig, ax = plt.subplots(figsize=(11.2, 5.6), dpi=150)
        fig.patch.set_facecolor("#f8fafc")
        ax.set_facecolor("#ffffff")

        items = [item for item in (category.get("items") or []) if isinstance(item, dict)]
        load_context_items = [item for item in (category.get("load_context_items") or []) if isinstance(item, dict)]
        all_values: List[float] = [0.0, -10.0, 10.0]
        earliest_abnormal: Optional[str] = None
        max_length = 0
        for index, item in enumerate(items):
            timestamps = list(((item.get("chart") or {}).get("timestamps") or []))
            values = list(((item.get("chart") or {}).get("values") or []))
            if not timestamps or not values:
                continue
            max_length = max(max_length, len(timestamps))
            reference = self._curve_normalization_reference(item)
            rel_values = [self._relative_percent_for_curve(value, reference) for value in values]
            valid_pairs = [(idx, value) for idx, value in enumerate(rel_values) if value is not None]
            if not valid_pairs:
                continue
            xs = [pair[0] for pair in valid_pairs]
            ys = [pair[1] for pair in valid_pairs]
            all_values.extend(ys)
            ax.plot(xs, ys, linewidth=1.8, alpha=0.92, label=self._compact_curve_label(item))
            abnormal_start = self._stringify(item.get("abnormal_start"), "").strip()
            if abnormal_start and (earliest_abnormal is None or abnormal_start < earliest_abnormal):
                earliest_abnormal = abnormal_start

        for load_item in load_context_items:
            timestamps = list(((load_item.get("chart") or {}).get("timestamps") or []))
            values = list(((load_item.get("chart") or {}).get("values") or []))
            if not timestamps or not values:
                continue
            max_length = max(max_length, len(timestamps))
            reference = self._curve_normalization_reference(load_item)
            rel_values = [self._relative_percent_for_curve(value, reference) for value in values]
            valid_pairs = [(idx, value) for idx, value in enumerate(rel_values) if value is not None]
            if not valid_pairs:
                continue
            xs = [pair[0] for pair in valid_pairs]
            ys = [pair[1] for pair in valid_pairs]
            all_values.extend(ys)
            ax.plot(
                xs,
                ys,
                linewidth=1.5,
                alpha=0.8,
                linestyle="--",
                color="#0f172a",
                label=f"负荷参照·{self._compact_curve_label(load_item)}",
            )

        ax.axhspan(-10.0, 10.0, color="#dbeafe", alpha=0.35, zorder=0)
        ax.axhline(0.0, color="#475569", linestyle="--", linewidth=1.1, alpha=0.9)
        ax.axhline(10.0, color="#93c5fd", linestyle=":", linewidth=1.0, alpha=0.9)
        ax.axhline(-10.0, color="#93c5fd", linestyle=":", linewidth=1.0, alpha=0.9)

        if earliest_abnormal:
            first_item = items[0] if items else {}
            timestamps = list(((first_item.get("chart") or {}).get("timestamps") or []))
            if earliest_abnormal in timestamps:
                ax.axvline(timestamps.index(earliest_abnormal), color="#dc2626", linestyle="--", linewidth=1.2, alpha=0.85)

        ymin = min(all_values) if all_values else -20.0
        ymax = max(all_values) if all_values else 20.0
        spread = max(ymax - ymin, 20.0)
        ax.set_ylim(ymin - spread * 0.12, ymax + spread * 0.18)
        ax.set_xlim(0, max(1, max_length - 1))
        ax.grid(axis="y", linestyle="--", alpha=0.22)
        ax.set_ylabel("相对参考偏差 (%)", fontproperties=font_prop, fontsize=9)
        ax.set_title(self._stringify(category.get("title"), "整体数据曲线"), fontproperties=font_prop, fontsize=13, loc="left", pad=8)
        ax.text(
            0.0,
            1.02,
            "同图曲线已统一换算为相对各自参考值的偏差百分比；虚线表示负荷参照曲线。",
            transform=ax.transAxes,
            fontproperties=font_prop,
            fontsize=8.2,
            color="#475569",
            ha="left",
            va="bottom",
        )
        tick_positions = [0, max(0, max_length // 2), max(0, max_length - 1)]
        tick_positions = sorted(set(position for position in tick_positions if position < max_length))
        first_source = items[0] if items else (load_context_items[0] if load_context_items else {})
        first_timestamps = list(((first_source.get("chart") or {}).get("timestamps") or []))
        if tick_positions and first_timestamps:
            tick_labels = [self._compact_timestamp(first_timestamps[position]) for position in tick_positions]
            ax.set_xticks(tick_positions)
            ax.set_xticklabels(tick_labels, fontproperties=font_prop, fontsize=8)
        legend_count = len(items) + len(load_context_items)
        legend = ax.legend(loc="upper left", fontsize=8, ncol=max(1, min(3, legend_count)), frameon=False)
        if legend and font_prop:
            for text in legend.get_texts():
                text.set_fontproperties(font_prop)
        fig.tight_layout()
        fig.savefig(image_path, bbox_inches="tight")
        plt.close(fig)
        relative_path = str(Path(asset_prefix) / filename).replace("\\", "/") if asset_prefix else filename
        return {
            "image_path": str(image_path.resolve()).replace("\\", "/"),
            "image_relative_path": relative_path,
            "image_status": "generated",
        }

    def _resolve_report_plot_font(self, font_properties_cls: Any) -> Optional[Any]:
        candidates = [Path(self.fonts.body_path)] if self.fonts.body_path else []
        candidates.extend(
            [
                Path(__file__).resolve().parents[1] / "resets" / "fonts" / "仿宋_GB2312.ttf",
                Path("C:/Windows/Fonts/msyh.ttc"),
                Path("C:/Windows/Fonts/simsun.ttc"),
            ]
        )
        for candidate in candidates:
            if candidate and candidate.exists():
                return font_properties_cls(fname=str(candidate))
        return None

    def _slugify(self, value: Any) -> str:
        text = self._stringify(value, "item").strip().lower()
        text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text)
        text = text.strip("_")
        return text or "item"

    def _compact_timestamp(self, value: Any) -> str:
        text = self._stringify(value, "-").strip()
        if "T" in text:
            date_part, time_part = text.split("T", 1)
            return f"{date_part} {time_part[:5]}"
        return text[:16]

    def _section_numeral(self, value: int) -> str:
        numerals = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        number = int(value or 0)
        if number <= 0:
            return str(value)
        if number < 10:
            return numerals[number]
        if number == 10:
            return "十"
        if number < 20:
            return f"十{numerals[number % 10]}"
        if number < 100:
            tens, ones = divmod(number, 10)
            return f"{numerals[tens]}十{numerals[ones] if ones else ''}"
        return str(value)

    def _build_transparency_view(self, analysis_result: Dict[str, Any]) -> Dict[str, List[str]]:
        overall = analysis_result.get("overall_judgement") or {}
        reasoning = analysis_result.get("reasoning_result")
        if not isinstance(reasoning, dict):
            reasoning = {}
        decision = analysis_result.get("decision_result")
        if not isinstance(decision, dict):
            decision = {}
        evidence_layers = overall.get("evidence_layers") or {}
        explainability = overall.get("explainability") or {}
        reference_framework = overall.get("reference_framework") or []
        baseline_references = overall.get("baseline_references") or []
        state_rules = overall.get("state_aggregation_rules") or []
        triggered_rules = overall.get("triggered_rules") or []
        verification_loop = overall.get("verification_loop") or {}
        reference_provenance = explainability.get("reference_provenance") or []
        rule_parameter_explanations = explainability.get("rule_parameter_explanations") or []
        dominant_anomaly_explanation = explainability.get("dominant_anomaly_explanation") or {}

        facts = self._dedupe_text_items(
            [self._single_line_text(item, "").strip() for item in (evidence_layers.get("facts") or []) if self._single_line_text(item, "").strip()],
            limit=6,
        )
        rules = self._dedupe_text_items(
            [self._format_rule_parameter_explanation_item(item) for item in rule_parameter_explanations if self._format_rule_parameter_explanation_item(item)]
            + [self._single_line_text(item, "").strip() for item in (evidence_layers.get("rules") or []) if self._single_line_text(item, "").strip()]
            + [self._single_line_text(item, "").strip() for item in triggered_rules if self._single_line_text(item, "").strip()],
            limit=8,
        )

        explanations: List[str] = self._format_dominant_anomaly_explanation_items(dominant_anomaly_explanation)
        if reasoning.get("root_cause"):
            explanations.append("以下内容仅为候选原因与待核查假设，不构成已确认根因。")
        for clause in self._extract_text_clauses(reasoning.get("root_cause"), limit=3):
            explanations.append(f"待核查假设：{clause}")
        for clause in self._extract_text_clauses(reasoning.get("coupling_analysis"), limit=2):
            explanations.append(f"机理补充：{clause}")
        boundary = self._single_line_text(overall.get("explanation_boundary"), "").strip()
        if boundary:
            explanations.append(boundary)
        explanations = self._dedupe_text_items(explanations, limit=12)

        actions = self._dedupe_text_items(
            [self._single_line_text(item, "").strip() for item in (evidence_layers.get("actions") or []) if self._single_line_text(item, "").strip()]
            + self._format_verification_loop_items(verification_loop)
            + ([f"执行建议：{self._first_compact_clause(decision.get('actionable_steps'))}"] if self._first_compact_clause(decision.get("actionable_steps")) else [])
            + ([f"回退策略：{self._first_compact_clause(decision.get('rollback_strategy'))}"] if self._first_compact_clause(decision.get("rollback_strategy")) else []),
            limit=6,
        )

        return {
            "baseline_refs": self._dedupe_text_items(
                [self._format_reference_framework_item(item) for item in reference_framework if self._format_reference_framework_item(item)]
                + [self._format_reference_provenance_item(item) for item in reference_provenance if self._format_reference_provenance_item(item)]
                + [self._format_baseline_reference_item(item) for item in baseline_references if self._format_baseline_reference_item(item)],
                limit=8,
            ),
            "facts": facts,
            "rules": rules,
            "explanations": explanations,
            "actions": actions,
            "state_rules": self._dedupe_text_items(
                [self._format_state_rule_item(item) for item in state_rules if self._format_state_rule_item(item)],
                limit=6,
            ),
        }

    def _build_knowledge_support_view(self, analysis_result: Dict[str, Any]) -> Dict[str, List[str]]:
        knowledge_retrieval = analysis_result.get("knowledge_retrieval") or {}
        reasoning = analysis_result.get("reasoning_result") or {}
        overall = analysis_result.get("overall_judgement") or {}
        measures = self._dedupe_recommended_measures(knowledge_retrieval.get("recommended_measures") or [])

        judgement_support: List[str] = []
        softened_root_cause = self._soften_root_cause_text(reasoning.get("root_cause"))
        main_judgement = self._first_compact_clause(softened_root_cause) or self._first_compact_clause(overall.get("summary"))
        if main_judgement:
            judgement_support.append(f"当前判断聚焦：{main_judgement}")

        retrieval_summary = self._clean_retrieval_summary(knowledge_retrieval.get("retrieval_summary"))
        if retrieval_summary and retrieval_summary != "未返回检索结论。":
            judgement_support.append(f"检索结论：{self._short_text(retrieval_summary, '未返回检索结论。', limit=120)}")

        evidence_refs: List[str] = []
        triads: List[str] = []
        mapped_refs: List[Dict[str, Any]] = []
        for item in (knowledge_retrieval.get("knowledge_references") or [])[:8]:
            mapped = self._map_reference_to_support(item)
            snippet = self._stringify(mapped.get("snippet"), "").strip()
            if self._is_low_signal_evidence_snippet(snippet):
                continue
            if not (mapped.get("judgement") or mapped.get("actions")):
                continue
            mapped_refs.append(mapped)
            if len(mapped_refs) >= 4:
                break
        if (knowledge_retrieval.get("knowledge_references") or []) and not mapped_refs:
            judgement_support.append("知识库已检索到资料，但当前未命中能直接支撑本轮判断的高相关证据。")
        for mapped in mapped_refs:
            source = self._stringify(mapped.get("source"), "未标注来源")
            locator = self._stringify(mapped.get("locator"), "").strip()
            snippet = self._stringify(mapped.get("snippet"), "未返回依据摘录")
            locator_text = f" {locator}" if locator else ""
            mapped_judgement = list(mapped.get("judgement") or [])
            mapped_actions = list(mapped.get("actions") or [])
            if mapped_judgement:
                judgement_support.extend(f"{source}{locator_text}：{item}" for item in mapped_judgement)
            triad_judgement = "；".join(mapped_judgement) if mapped_judgement else (main_judgement or "用于对照当前判断")
            triad_action = "；".join(mapped_actions) if mapped_actions else "执行前需结合SOP、联锁边界和班组复核结果确认动作边界"
            evidence_refs.append(
                f"判断：{triad_judgement}；依据：{source}{locator_text} - {snippet}；动作约束：{triad_action}"
            )
            triads.append(
                f"判断：{triad_judgement}；依据：{source}{locator_text} - {snippet}；动作约束：{triad_action}"
            )

        action_constraints: List[str] = []
        for tip in knowledge_retrieval.get("risk_tips") or []:
            text = self._single_line_text(tip, "").strip()
            if text:
                action_constraints.append(text)
        for measure in measures[:4]:
            safety = self._single_line_text(measure.get("safety_note"), "").strip()
            if safety:
                action_constraints.append(f"执行边界：{safety}")
            steps = self._single_line_text(measure.get("steps"), "").strip()
            if steps and any(token in steps for token in ("先", "小步", "单变量", "稳负荷", "联锁")):
                action_constraints.append(f"执行顺序：{steps}")

        for mapped in mapped_refs:
            action_constraints.extend(mapped.get("actions") or [])
        if (knowledge_retrieval.get("knowledge_references") or []) and not mapped_refs:
            action_constraints.append("知识证据未形成硬支撑时，现场动作以在线工况、SOP 和人工复核结果为准。")

        judgement_support = self._dedupe_text_items(judgement_support, limit=5)
        deduped_constraints = self._dedupe_text_items(action_constraints, limit=5)
        evidence_refs = self._dedupe_text_items(evidence_refs, limit=4)
        triads = self._dedupe_text_items(triads, limit=4)

        return {
            "judgement_support": judgement_support,
            "action_constraints": deduped_constraints,
            "evidence_refs": evidence_refs,
            "triads": triads,
        }

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_core_indicators(self, analysis_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        core = analysis_result.get("core_indicators") or {}
        if hasattr(core, "model_dump"):
            core = core.model_dump()
        elif hasattr(core, "dict"):
            core = core.dict()
        return core if isinstance(core, dict) else {}

    def _semantic_name_map(self, analysis_result: Dict[str, Any]) -> Dict[str, str]:
        name_map: Dict[str, str] = {}
        for item in analysis_result.get("semantic_data") or []:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag_id") or "").strip()
            name = self._stringify(item.get("name"), "").strip()
            if tag and name:
                name_map[tag] = name
        return name_map

    def _format_state_count_summary(self, counts: Dict[str, int]) -> str:
        ordered = []
        for state, count in counts.items():
            if count <= 0:
                continue
            ordered.append(f"{state}{count}项")
        return "，".join(ordered)

    def _summarize_core_dimension(
        self,
        *,
        label: str,
        indicators: Dict[str, Dict[str, Any]],
        name_map: Dict[str, str],
    ) -> str:
        normalized: List[Dict[str, Any]] = []
        for tag_id, payload in (indicators or {}).items():
            if not isinstance(payload, dict):
                continue
            state = self._stringify(payload.get("state"), "未标注").strip()
            membership = self._safe_float(payload.get("membership"))
            normalized.append(
                {
                    "tag_id": str(tag_id or "").strip(),
                    "name": name_map.get(str(tag_id or "").strip()) or str(tag_id or "未命名指标"),
                    "state": state,
                    "membership": membership,
                }
            )

        if not normalized:
            return ""

        state_counts: Dict[str, int] = {}
        weak_items: List[Dict[str, Any]] = []
        weak_states = {
            "一般",
            "较差",
            "差",
            "异常",
            "偏差较大",
            "偏离显著",
            "偏高",
            "偏低",
            "严重偏高",
            "严重偏低",
            "Unknown",
        }
        for item in normalized:
            state_counts[item["state"]] = state_counts.get(item["state"], 0) + 1
            membership = item.get("membership")
            if item["state"] in weak_states or (membership is not None and membership < 0.8):
                weak_items.append(item)

        weak_items.sort(key=lambda x: ((x.get("membership") if x.get("membership") is not None else 9.9), x.get("name", "")))
        count_text = self._format_state_count_summary(state_counts)
        weak_name = weak_items[0]["name"] if weak_items else ""

        if label == "提取率":
            if weak_name:
                return f"提取率共 {len(normalized)} 项，当前为{count_text}，需继续关注 {weak_name}。"
            return f"提取率共 {len(normalized)} 项，当前为{count_text}，未见提取率异常候选。"
        if label == "稳定性":
            if weak_name:
                return f"稳定性共 {len(normalized)} 项，当前为{count_text}，主要承压点为 {weak_name}。"
            return f"稳定性共 {len(normalized)} 项，当前为{count_text}，整体保持可控。"
        if weak_name:
            return f"单耗/能耗共 {len(normalized)} 项，当前为{count_text}，主要承压点为 {weak_name}，但尚未成为本轮主导矛盾。"
        return f"单耗/能耗共 {len(normalized)} 项，当前为{count_text}，整体处于可控范围。"

    def _device_overview_items(self, analysis_result: Dict[str, Any]) -> List[Tuple[str, str]]:
        overall = analysis_result.get("overall_judgement") or {}
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []
        baseline_profile = analysis_result.get("baseline_profile") or {}
        three_level = overall.get("three_level_state_engine") or {}
        subsystem_states = overall.get("subsystem_states") or three_level.get("subsystem_states") or []

        total_count = int(overall.get("total_count") or len(analysis_result.get("semantic_data") or []))
        abnormal_count = int(overall.get("abnormal_count") or len(abnormal_details))
        plant_state_label = self._stringify(
            overall.get("plant_state_label") or three_level.get("plant_state_label"),
            "未知状态",
        )
        status_text = self._stringify(overall.get("status_text"), "需关注")
        main_contradiction = self._stringify(overall.get("main_contradiction") or three_level.get("main_contradiction"), "").strip()

        if abnormal_count > 0:
            overall_text = (
                f"当前装置整体处于{plant_state_label}，本轮共评估 {total_count} 项指标，"
                f"其中异常 {abnormal_count} 项，整体风险等级为「{status_text}」。"
            )
        else:
            overall_text = (
                f"当前装置整体处于{plant_state_label}，本轮共评估 {total_count} 项指标，"
                f"未识别到异常候选，整体风险等级为「{status_text}」。"
            )

        baseline_count = int(baseline_profile.get("tag_count") or 0)
        avg_optimal_gap = self._safe_float(three_level.get("avg_optimal_gap"))
        top_subsystem = subsystem_states[0]["name"] if subsystem_states else "当前快照"
        baseline_method = self._stringify(
            baseline_profile.get("method_label") or baseline_profile.get("method"),
            "",
        ).strip()
        if baseline_count > 0 and avg_optimal_gap is not None:
            history_text = (
                f"对照历史/优态基线（覆盖 {baseline_count} 项指标），本轮偏离主要集中在{top_subsystem}，"
                f"整体优态偏离约 {avg_optimal_gap:.1%}。"
            )
        elif baseline_count > 0:
            history_text = f"已接入历史/优态基线（覆盖 {baseline_count} 项指标），本轮偏离主要集中在{top_subsystem}。"
        else:
            history_text = "本轮未接入可用历史/优态基线，对比判断以当前快照和规则结果为主。"
        if baseline_method and baseline_count > 0:
            history_text = f"{history_text} 基线方法：{baseline_method}。"
        if baseline_count > 0:
            history_text = f"{history_text} 异常判级按目标参考值执行，历史基线只用于常态对比，优态基线只用于衡量优化空间。"

        if abnormal_details:
            top_items = []
            for item in abnormal_details[:2]:
                name = self._stringify(item.get("name"), "未命名指标")
                state = self._stringify(item.get("level") or item.get("state_desc"), "异常")
                diff_percent = self._format_diff_percent_text(item.get("diff_percent"))
                top_items.append(f"{name}{state}{diff_percent}")
            event_text = f"当前主要表现为{'、'.join(top_items)}。"
            contradiction_core = re.sub(r"^(主导偏离|主导矛盾)[:：]\s*", "", main_contradiction).strip("。 ")
            if contradiction_core and contradiction_core not in event_text:
                event_text = f"{event_text}当前主导偏离集中在{contradiction_core}。"
        else:
            event_text = "当前未见异常扩散，主要指标整体处于可控范围。"

        return [
            ("总体判断", overall_text),
            ("当前与历史", history_text),
            ("当前发生了什么", event_text),
        ]

    def _dimension_status_items(self, analysis_result: Dict[str, Any]) -> List[Tuple[str, str]]:
        overall = analysis_result.get("overall_judgement") or {}
        three_level = overall.get("three_level_state_engine") or {}
        subsystem_states = overall.get("subsystem_states") or three_level.get("subsystem_states") or []
        main_contradiction = self._stringify(overall.get("main_contradiction") or three_level.get("main_contradiction"), "").strip()
        subsystem_text = "、".join(
            f"{self._stringify(item.get('name'), '未命名系统')}={self._stringify(item.get('state'), 'unknown')}"
            for item in subsystem_states[:3]
        )
        overall_text = subsystem_text or self._first_compact_clause(overall.get("summary"), "当前未形成子系统分项判断。")
        if main_contradiction:
            overall_text = f"{overall_text}。主导矛盾：{main_contradiction}"

        name_map = self._semantic_name_map(analysis_result)
        core = self._normalize_core_indicators(analysis_result)
        items: List[Tuple[str, str]] = [("装置整体", overall_text)]

        extraction_text = self._summarize_core_dimension(
            label="提取率",
            indicators=core.get("extraction_rate") or {},
            name_map=name_map,
        )
        if extraction_text:
            items.append(("提取率", extraction_text))

        stability_text = self._summarize_core_dimension(
            label="稳定性",
            indicators=core.get("stability") or {},
            name_map=name_map,
        )
        if stability_text:
            items.append(("稳定性", stability_text))

        energy_text = self._summarize_core_dimension(
            label="单耗/能耗",
            indicators=core.get("energy_consumption") or {},
            name_map=name_map,
        )
        if energy_text:
            items.append(("单耗/能耗", energy_text))

        return items

    def _direction_text(self, detail: Dict[str, Any]) -> str:
        direction = str(detail.get("optimization_direction") or "").strip().lower()
        if direction == "increase":
            return "回升"
        if direction == "decrease":
            return "回落"
        state = self._stringify(detail.get("level") or detail.get("state_desc"), "").strip()
        if "低" in state:
            return "回升"
        if "高" in state:
            return "回落"
        return "改善"

    def _abnormal_summary_phrase(self, detail: Dict[str, Any]) -> str:
        name = self._stringify(detail.get("name"), "未命名指标")
        state = self._stringify(detail.get("level") or detail.get("state_desc"), "异常")
        diff_percent = self._format_diff_percent_text(detail.get("diff_percent"))
        return f"{name}{state}{diff_percent}"

    def _abnormal_shift_card_phrase(self, detail: Dict[str, Any]) -> str:
        name = self._stringify(detail.get("name"), "未命名指标")
        state = self._stringify(detail.get("level") or detail.get("state_desc"), "异常").strip()
        duration_points = int(self._safe_float(((detail.get("window") or {}).get("duration_points"))) or 0)
        duration_prefix = "长期" if duration_points >= 8 else "持续" if duration_points >= 2 else ""
        return f"{name}{duration_prefix}{state}"

    def _primary_summary_action(self, abnormal_details: List[Dict[str, Any]]) -> str:
        if abnormal_details:
            top = abnormal_details[0]
            follow = abnormal_details[1] if len(abnormal_details) > 1 else None
            top_name = self._stringify(top.get("name"), "首要异常指标")
            action_target = top_name.replace("制冷量", "").replace("冷损", "").replace("产量", "").strip()
            if not action_target:
                action_target = top_name
            follow_name = self._stringify(follow.get("name"), "次级异常指标") if follow else ""
            if "膨胀机" in top_name:
                action = f"先核{action_target}入口温压，再查导叶/旁通/振动"
            elif "主换" in top_name:
                action = f"先核{action_target}冷端温差与压降，再查冷量分配"
            elif "液氩" in top_name or "提取率" in top_name:
                action = f"先核冷量侧是否恢复，再查{action_target}对应回流/塔压/精馏负荷"
            else:
                action = f"先核{action_target}测点与设备状态，再做小步微调"
            if follow_name:
                action = f"{action}；同步盯{follow_name}"
            return f"{action}。"
        return "先稳工况，再按单变量、小步原则执行处置。"

    def _primary_acceptance_gate(self, abnormal_details: List[Dict[str, Any]], core: Dict[str, Dict[str, Any]]) -> str:
        if abnormal_details:
            clauses = [
                f"{self._stringify(abnormal_details[0].get('name'), '首要异常指标')}{self._direction_text(abnormal_details[0])}"
            ]
            if len(abnormal_details) > 1:
                clauses.append(
                    f"{self._stringify(abnormal_details[1].get('name'), '次级异常指标')}{self._direction_text(abnormal_details[1])}"
                )
            if core.get("extraction_rate"):
                clauses.append("提取率或主产品质量不恶化")
            return f"{'；'.join(clauses)}；连续保持至少 2 个观察窗口。"
        return "关键指标连续改善，且未触发联锁、质量和安全边界。"

    def _primary_rollback_condition(self, abnormal_details: List[Dict[str, Any]], core: Dict[str, Dict[str, Any]]) -> str:
        if abnormal_details:
            clauses = [f"{self._stringify(abnormal_details[0].get('name'), '首要异常指标')}未改善或继续恶化"]
            if len(abnormal_details) > 1:
                clauses.append(f"{self._stringify(abnormal_details[1].get('name'), '次级异常指标')}继续恶化")
            if core.get("extraction_rate"):
                clauses.append("提取率或主产品质量连续恶化")
            return f"{'；'.join(clauses)}；立即回退至上一稳定工况。"
        return "若关键指标继续恶化或逼近联锁边界，立即降负荷并升级处置。"

    def _execution_summary_items(self, analysis_result: Dict[str, Any]) -> List[Tuple[str, str]]:
        overall = analysis_result.get("overall_judgement") or {}
        reasoning = analysis_result.get("reasoning_result")
        if not isinstance(reasoning, dict):
            reasoning = {}
        confirmed_items, pending_items = self._build_conclusion_layers(analysis_result)
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []
        core = self._normalize_core_indicators(analysis_result)

        status_text = self._stringify(overall.get("status_text"), "").strip()
        plant_state_label = self._stringify(overall.get("plant_state_label"), "").strip()
        abnormal_count = int(analysis_result.get("abnormal_count", 0) or len(abnormal_details))
        if status_text and plant_state_label:
            current_status = f"{status_text} / {plant_state_label}"
        elif plant_state_label:
            current_status = plant_state_label
        else:
            current_status = self._first_compact_clause(overall.get("summary"))
        if current_status and abnormal_count > 0:
            current_status = f"{current_status}（异常{abnormal_count}项）"
        if not current_status:
            current_status = f"分析状态为{self._stringify(analysis_result.get('status'), '未知')}，异常指标{abnormal_count}个。"

        if abnormal_details:
            main_problem = "；".join(self._abnormal_shift_card_phrase(item) for item in abnormal_details[:2]) + "。"
        else:
            main_problem = ""
        if not main_problem:
            main_problem = self._first_compact_clause(self._soften_root_cause_text(reasoning.get("root_cause"))) or self._first_compact_clause(confirmed_items[0] if confirmed_items else "")
        if not main_problem:
            main_problem = "当前未识别到明确主问题，请结合工艺总览与异常详情复核。"

        immediate_action = self._primary_summary_action(abnormal_details)

        must_check = "；".join(item for item in pending_items[:2] if item.strip())
        if not must_check:
            must_check = "按班组点检表完成设备侧、仪表侧和联锁边界复核。"

        acceptance_gate = self._primary_acceptance_gate(abnormal_details, core)
        rollback_condition = self._primary_rollback_condition(abnormal_details, core)

        return [
            ("当前状态", current_status),
            ("主问题", main_problem),
            ("立即动作", immediate_action),
            ("必查项", must_check),
            ("验收门槛", acceptance_gate),
            ("回退条件", rollback_condition),
        ]

    def _build_conclusion_layers(self, analysis_result: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        confirmed: List[str] = []
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []
        for item in abnormal_details[:3]:
            name = self._stringify(item.get("name"), "未命名指标")
            level = self._stringify(item.get("level") or item.get("state_desc"), "状态未标注")
            diff = self._format_number(item.get("diff"))
            diff_percent = self._format_diff_percent_text(item.get("diff_percent"))
            window = self._format_window_text(item)
            confirmed.append(f"{name}：状态{level}，偏差{diff}{diff_percent}，持续区间{window}。")

        if not confirmed:
            overall = analysis_result.get("overall_judgement") or {}
            summary = self._stringify(overall.get("summary"), "")
            if summary:
                summary_sections = self._split_pipe_sections(summary)
                if summary_sections:
                    confirmed.append(summary_sections[0])
                    for part in summary_sections[1:2]:
                        confirmed.append(f"{self._review_section_label()}：{self._normalize_expert_review_text(part)}")
                else:
                    confirmed.append(summary)

        reasoning = analysis_result.get("reasoning_result")
        if not isinstance(reasoning, dict):
            reasoning = {}
        decision = analysis_result.get("decision_result")
        if not isinstance(decision, dict):
            decision = {}
        pending = self._extract_pending_checks(reasoning=reasoning, decision=decision, analysis_result=analysis_result)
        return confirmed, pending

    def _extract_pending_checks(
        self,
        *,
        reasoning: Dict[str, Any],
        decision: Dict[str, Any],
        analysis_result: Dict[str, Any],
    ) -> List[str]:
        pending: List[str] = []
        missing = reasoning.get("missing_data_request")
        if isinstance(missing, dict):
            list_like_keys = {"items", "required_items", "required_data", "data_items", "check_items"}
            blocked_keys = {"needed", "need", "required", "purpose", "goal", "reason", "summary", "description", "status"}

            for key in list_like_keys:
                if key not in missing:
                    continue
                value = missing.get(key)
                if value in (None, "", [], {}):
                    continue
                if isinstance(value, list):
                    for entry in value:
                        entry_text = self._stringify(entry, "").strip()
                        if entry_text:
                            pending.append(entry_text)
                    continue
                value_text = self._stringify(value, "")
                fragments = [fragment.strip() for fragment in re.split(r"[;\n；]", value_text) if fragment.strip()]
                pending.extend(fragments)

            if not pending:
                for key, value in missing.items():
                    normalized_key = str(key or "").strip().lower()
                    if normalized_key in list_like_keys or normalized_key in blocked_keys:
                        continue
                    if isinstance(value, bool):
                        continue
                    if value in (None, "", [], {}):
                        continue
                    key_text = self._stringify(key)
                    if isinstance(value, list):
                        for entry in value:
                            entry_text = self._stringify(entry, "").strip()
                            if entry_text:
                                pending.append(entry_text)
                        continue
                    value_text = self._stringify(value, "")
                    fragments = [fragment.strip() for fragment in re.split(r"[;\n；]", value_text) if fragment.strip()]
                    if fragments:
                        pending.extend([f"{key_text}：{fragment}" for fragment in fragments])
                    elif value_text.strip():
                        pending.append(f"{key_text}：{value_text}")
        elif isinstance(missing, list):
            for item in missing:
                text = self._stringify(item, "").strip()
                if text:
                    pending.append(text)
        elif missing:
            for block in re.split(r"[;\n；]", self._stringify(missing)):
                text = block.strip()
                if text:
                    pending.append(text)

        joined_text = " ".join(
            [
                self._stringify(reasoning.get("operation_suggestion"), ""),
                self._stringify(decision.get("actionable_steps"), ""),
                self._stringify(decision.get("risk_assessment"), ""),
            ]
        )
        keyword_map = {
            "振动": "设备振动趋势（含报警记录）",
            "轴温": "轴承温度变化",
            "阀位": "关键阀位反馈与执行一致性",
            "防喘": "防喘振动作记录",
            "联锁": "联锁动作与保护状态日志",
            "转速": "膨胀机转速及转速波动",
            "压降": "主换压降实时曲线",
            "温差": "主换冷热端温差曲线",
        }
        for key, desc in keyword_map.items():
            if key in joined_text and not any(desc in item for item in pending):
                pending.append(f"{desc}（当前报告未直接给出在线证据，需现场补采核对）")

        if not pending:
            pending.append("本轮结论主要基于在线工况数据，执行前请按班组点检表完成设备侧复核。")

        deduped: List[str] = []
        seen = set()
        blocked_tokens = ("乱码", "编码修复", "原始数据编码", "字符编码")
        for item in pending:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            if any(token in normalized for token in blocked_tokens):
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _verification_status_text(self, status: Any) -> str:
        value = str(status or "").strip().lower()
        if value == "passed":
            return "通过"
        if value == "failed":
            return "未通过"
        return "待现场验证"

    def _closed_loop_status_text(self, status: Any) -> str:
        value = str(status or "").strip().lower()
        if value in {"done", "completed", "closed", "passed"}:
            return "已闭环"
        if value in {"failed", "error"}:
            return "闭环未完成"
        return "待现场闭环"

    def _build_pdf_kv_table(self, items: Iterable[Tuple[str, Any]], body_font_name: str):
        from reportlab.platypus import Paragraph

        rows = [
            [
                Paragraph("<b>项目</b>", self.pdf_styles["TableHeader"]),
                Paragraph("<b>内容</b>", self.pdf_styles["TableHeader"]),
            ]
        ]
        for label, value in items:
            rows.append(
                [
                    Paragraph(self._pdf_rich_text(label), self.pdf_styles["TableLabel"]),
                    Paragraph(self._pdf_rich_text(value), self.pdf_styles["TableValue"]),
                ]
            )
        return self._build_pdf_table(rows, [1.5 * 72, 4.6 * 72], body_font_name)

    def _build_pdf_table(self, rows: List[List[str]], col_widths: List[float], body_font_name: str):
        from reportlab.lib import colors
        from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

        normalized_rows: List[List[Any]] = []
        for row_index, row in enumerate(rows):
            normalized_row: List[Any] = []
            for cell in row:
                if isinstance(cell, Flowable):
                    normalized_row.append(cell)
                    continue
                if isinstance(cell, list):
                    normalized_items: List[Any] = []
                    for item in cell:
                        if isinstance(item, Flowable):
                            normalized_items.append(item)
                        else:
                            style_name = "TableHeader" if row_index == 0 else "TableValue"
                            normalized_items.append(Paragraph(self._pdf_rich_text(item, ""), self.pdf_styles[style_name]))
                    normalized_row.append(normalized_items)
                    continue
                style_name = "TableHeader" if row_index == 0 else "TableValue"
                normalized_row.append(Paragraph(self._pdf_rich_text(cell, ""), self.pdf_styles[style_name]))
            normalized_rows.append(normalized_row)

        table = Table(normalized_rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("FONTNAME", (0, 0), (-1, -1), body_font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("LEADING", (0, 0), (-1, -1), 17),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]
        for row_index in range(1, len(rows)):
            if row_index % 2 == 0:
                style.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f8fafc")))
        table.setStyle(TableStyle(style))
        return table

    def _build_pdf_execution_summary_cards(self, items: Iterable[Tuple[str, Any]], *, styles: Dict[str, Any], content_width: float):
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        cards = []
        for label, value in items:
            cards.append(
                [
                    Paragraph(self._pdf_rich_text(label), styles["SummaryCardLabel"]),
                    Spacer(1, 3),
                    Paragraph(self._pdf_rich_text(value), styles["SummaryCardValue"]),
                ]
            )

        if not cards:
            cards = [[Paragraph("未生成现场执行摘要。", styles["SummaryCardValue"])]]

        row_count = max(1, int(math.ceil(len(cards) / 2)))
        rows: List[List[Any]] = []
        for row_index in range(row_count):
            row_cards = []
            for col_index in range(2):
                item_index = row_index * 2 + col_index
                row_cards.append(cards[item_index] if item_index < len(cards) else "")
            rows.append(row_cards)

        table = Table(rows, colWidths=[content_width / 2 - 6, content_width / 2 - 6], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 10, colors.white),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ]
            )
        )
        return table

    def _append_pdf_callout_box(
        self,
        story,
        *,
        title: str,
        text: Any,
        styles: Dict[str, Any],
        content_width: float,
        tone: str = "action",
    ) -> None:
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        palette = {
            "action": {
                "bg": colors.HexColor("#eff6ff"),
                "border": colors.HexColor("#93c5fd"),
                "title": colors.HexColor("#1d4ed8"),
            },
            "warning": {
                "bg": colors.HexColor("#fff7ed"),
                "border": colors.HexColor("#fdba74"),
                "title": colors.HexColor("#c2410c"),
            },
            "rollback": {
                "bg": colors.HexColor("#f8fafc"),
                "border": colors.HexColor("#cbd5e1"),
                "title": colors.HexColor("#334155"),
            },
        }.get(tone, {
            "bg": colors.HexColor("#eff6ff"),
            "border": colors.HexColor("#93c5fd"),
            "title": colors.HexColor("#1d4ed8"),
        })

        line_text = self._expand_escaped_newlines(self._render_operator_text(text, "")).replace("\r\n", "\n")
        lines = [line.strip() for line in line_text.split("\n") if line.strip()]
        if not lines:
            return

        title_style = copy.deepcopy(styles["CalloutTitle"])
        title_style.textColor = palette["title"]
        content = [Paragraph(self._pdf_rich_text(title), title_style)]
        for line in lines:
            content.append(Spacer(1, 3))
            content.append(Paragraph(self._pdf_rich_text(line), styles["CalloutBody"]))

        table = Table([[content]], colWidths=[content_width], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), palette["bg"]),
                    ("BOX", (0, 0), (-1, -1), 0.75, palette["border"]),
                    ("LINEBEFORE", (0, 0), (0, -1), 3.0, palette["border"]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 4))

    def _build_pdf_styles(self, styles, title_font_name, body_font_name, colors, ta_center, ta_justify, ta_left):
        from reportlab.lib.styles import ParagraphStyle

        return {
            "Title": ParagraphStyle(
                "GovTitle",
                parent=styles["Heading1"],
                fontName=title_font_name,
                fontSize=22,
                leading=34,
                alignment=ta_center,
                textColor=colors.HexColor("#0f172a"),
                spaceBefore=2,
                spaceAfter=6,
                wordWrap="CJK",
            ),
            "SubTitle": ParagraphStyle(
                "GovSubTitle",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11,
                leading=18,
                alignment=ta_center,
                textColor=colors.HexColor("#334155"),
                spaceAfter=6,
                wordWrap="CJK",
            ),
            "Meta": ParagraphStyle(
                "GovMeta",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.5,
                leading=17,
                alignment=ta_center,
                textColor=colors.HexColor("#1f2937"),
                spaceAfter=2,
                wordWrap="CJK",
            ),
            "MetaSmall": ParagraphStyle(
                "GovMetaSmall",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=9,
                leading=15,
                alignment=ta_center,
                textColor=colors.HexColor("#475569"),
                spaceAfter=6,
                wordWrap="CJK",
            ),
            "Heading2": ParagraphStyle(
                "GovHeading2",
                parent=styles["Heading2"],
                fontName=body_font_name,
                fontSize=14,
                leading=24,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                spaceBefore=14,
                spaceAfter=8,
                wordWrap="CJK",
            ),
            "Heading3": ParagraphStyle(
                "GovHeading3",
                parent=styles["Heading3"],
                fontName=body_font_name,
                fontSize=12,
                leading=20,
                alignment=ta_left,
                textColor=colors.HexColor("#1e293b"),
                spaceBefore=8,
                spaceAfter=4,
                wordWrap="CJK",
            ),
            "TableHeader": ParagraphStyle(
                "GovTableHeader",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.6,
                leading=16,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                wordWrap="CJK",
            ),
            "TableLabel": ParagraphStyle(
                "GovTableLabel",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.6,
                leading=16,
                alignment=ta_left,
                textColor=colors.HexColor("#334155"),
                wordWrap="CJK",
            ),
            "TableValue": ParagraphStyle(
                "GovTableValue",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.8,
                leading=17,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                wordWrap="CJK",
            ),
            "ItemTitle": ParagraphStyle(
                "GovItemTitle",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11.5,
                leading=20,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                spaceBefore=6,
                spaceAfter=2,
                wordWrap="CJK",
            ),
            "Body": ParagraphStyle(
                "GovBody",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11.5,
                leading=21,
                alignment=ta_justify,
                firstLineIndent=24,
                textColor=colors.HexColor("#0f172a"),
                spaceAfter=6,
                wordWrap="CJK",
            ),
            "BodyNoIndent": ParagraphStyle(
                "GovBodyNoIndent",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11.5,
                leading=21,
                alignment=ta_justify,
                firstLineIndent=0,
                textColor=colors.HexColor("#0f172a"),
                spaceAfter=6,
                wordWrap="CJK",
            ),
            "SummaryCardLabel": ParagraphStyle(
                "GovSummaryCardLabel",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.2,
                leading=15,
                alignment=ta_left,
                textColor=colors.HexColor("#64748b"),
                wordWrap="CJK",
            ),
            "SummaryCardValue": ParagraphStyle(
                "GovSummaryCardValue",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=13.2,
                leading=20,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                wordWrap="CJK",
            ),
            "CalloutTitle": ParagraphStyle(
                "GovCalloutTitle",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11.4,
                leading=18,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                wordWrap="CJK",
            ),
            "CalloutBody": ParagraphStyle(
                "GovCalloutBody",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=11.0,
                leading=18,
                alignment=ta_left,
                textColor=colors.HexColor("#0f172a"),
                wordWrap="CJK",
            ),
            "Bullet": ParagraphStyle(
                "GovBullet",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=10.8,
                leading=18,
                alignment=ta_left,
                leftIndent=16,
                textColor=colors.HexColor("#1f2937"),
                spaceAfter=3,
                wordWrap="CJK",
            ),
            "Note": ParagraphStyle(
                "GovNote",
                parent=styles["Normal"],
                fontName=body_font_name,
                fontSize=9.5,
                leading=15,
                alignment=ta_left,
                textColor=colors.HexColor("#475569"),
                spaceBefore=6,
                spaceAfter=0,
                wordWrap="CJK",
            ),
        }

    def _append_pdf_paragraphs(self, story, text: Any, style):
        from reportlab.platypus import Paragraph

        text_value = self._expand_escaped_newlines(self._render_operator_text(text, "")).replace("\r\n", "\n")
        lines = [line.strip() for line in text_value.split("\n") if line.strip()]
        for line in lines:
            story.append(Paragraph(self._pdf_rich_text(line), style))

    def _append_pdf_bullets(self, story, lines: Iterable[Any], style):
        from reportlab.platypus import Paragraph

        for line in lines:
            text = self._render_operator_text(line, "").strip()
            if not text:
                continue
            story.append(Paragraph(f"• {self._pdf_rich_text(text)}", style))

    def _draw_pdf_page_decor(self, canvas, doc, body_font_name: str):
        from reportlab.lib import colors

        canvas.saveState()
        page_width, _ = doc.pagesize
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, doc.bottomMargin - 10, page_width - doc.rightMargin, doc.bottomMargin - 10)
        canvas.setFont(body_font_name, 9)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawCentredString(page_width / 2, doc.bottomMargin - 24, f"第 {canvas.getPageNumber()} 页")
        canvas.restoreState()

    def _overview_items(self, analysis_result: Dict[str, Any]) -> List[Tuple[str, Any]]:
        overview = self._derive_data_overview(analysis_result)
        traceability = analysis_result.get("traceability") or {}
        data_source = self._first_non_placeholder(
            traceability.get("data_source"),
            analysis_result.get("data_source"),
            "uploaded",
        )
        items: List[Tuple[str, Any]] = [
            ("数据来源", self._normalize_data_source_label(data_source)),
            ("数据文件", overview.get("file_name")),
            ("时间点数", overview.get("timepoint_count")),
            ("监测点数", overview.get("sensor_count")),
            ("有效记录数", overview.get("effective_record_count")),
            (
                "时间范围",
                f"{overview.get('time_range_start')} 至 {overview.get('time_range_end')}",
            ),
            ("最新快照时刻", overview.get("latest_timestamp")),
            ("快照指标数", overview.get("latest_record_count")),
        ]
        return items

    def _target_definition_items(self, analysis_result: Dict[str, Any]) -> List[Tuple[str, Any]]:
        overview = self._derive_data_overview(analysis_result)
        overall = analysis_result.get("overall_judgement") or {}
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []
        task_note = self._stringify(overview.get("task_note"), "").strip()

        if task_note:
            goal = task_note
            source = "用户任务备注 + 当前装置工况"
        else:
            goal = "异常诊断与状态复核" if abnormal_details else "装置运行状态复核"
            source = "系统按当前工况自动归纳"

        focus_names: List[str] = []
        for item in abnormal_details[:3]:
            if not isinstance(item, dict):
                continue
            name = self._stringify(item.get("name"), "").strip()
            if name:
                focus_names.append(name)

        focus_scope = "；".join(focus_names)
        if not focus_scope:
            focus_scope = self._first_non_placeholder(
                overall.get("main_contradiction"),
                overall.get("summary"),
                "围绕当前装置主导矛盾与重点偏离指标开展复核。",
            )

        judgement_standard = (
            "单指标最终判级按目标参考值执行；历史运行基线用于判断是否偏离常态；"
            "优态基线用于衡量优化空间。"
        )

        return [
            ("本轮目标", goal),
            ("目标来源", source),
            ("判断标准", judgement_standard),
            ("重点关注范围", focus_scope),
        ]

    def _normalize_data_source_label(self, value: Any) -> str:
        source = self._stringify(value, "未记录").strip()
        if not source:
            return "未记录"
        lowered = source.lower()
        if lowered == "sample":
            return "生产现场数据（示例）"
        if lowered in {"uploaded", "upload", "excel", "xlsx"}:
            return "生产现场数据（上传文件）"
        return source

    def _is_placeholder_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return True
            normalized = text.replace("？", "?").replace(" ", "")
            normalized_placeholder = re.sub(r"[?/／、,，;；:：|｜\\\-_()（）\[\]【】]+", "", normalized)
            if normalized_placeholder and set(normalized_placeholder) == {"?"}:
                return True
            lowered = text.lower()
            if lowered in {"-", "--", "n/a", "na", "none", "null", "unknown"}:
                return True
            if "未记录" in text or "模板占位" in text or "未提供" in text:
                return True
        return False

    def _first_non_placeholder(self, *values: Any) -> Any:
        for value in values:
            if not self._is_placeholder_value(value):
                return value
        return values[-1] if values else ""

    def _short_text(self, value: Any, fallback: str, limit: int = 180) -> str:
        text = self._stringify(value, fallback).replace("\r\n", "\n")
        text = " ".join(text.split()).strip()
        if len(text) > limit:
            return f"{text[:limit].rstrip()}..."
        return text

    def _derive_data_overview(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        overview = dict(analysis_result.get("data_overview") or {})
        quality_gate = analysis_result.get("quality_gate") or {}
        semantic_data = analysis_result.get("semantic_data") or []
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []

        file_name = self._first_non_placeholder(
            overview.get("file_name"),
            analysis_result.get("file_name"),
            quality_gate.get("file_name"),
            "当前运行入口未透出文件名",
        )

        latest_candidates: List[str] = []
        for item in abnormal_details:
            if not isinstance(item, dict):
                continue
            snapshot_timestamp = item.get("snapshot_timestamp")
            if not self._is_placeholder_value(snapshot_timestamp):
                latest_candidates.append(str(snapshot_timestamp))
        for item in semantic_data:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("timestamp")
            if not self._is_placeholder_value(timestamp):
                latest_candidates.append(str(timestamp))
        inferred_latest_timestamp = max(latest_candidates) if latest_candidates else "当前入口未注入该字段"

        range_start_candidates: List[str] = []
        range_end_candidates: List[str] = []
        for item in abnormal_details:
            if not isinstance(item, dict):
                continue
            window = item.get("window") or {}
            if not isinstance(window, dict):
                continue
            start = window.get("start")
            end = window.get("end")
            if not self._is_placeholder_value(start):
                range_start_candidates.append(str(start))
            if not self._is_placeholder_value(end):
                range_end_candidates.append(str(end))

        inferred_range_start = min(range_start_candidates) if range_start_candidates else "当前入口未注入该字段"
        inferred_range_end = max(range_end_candidates) if range_end_candidates else inferred_latest_timestamp

        return {
            "file_name": file_name,
            "timepoint_count": self._first_non_placeholder(
                overview.get("timepoint_count"),
                quality_gate.get("timepoint_count"),
                "当前入口未注入该字段",
            ),
            "sensor_count": self._first_non_placeholder(
                overview.get("sensor_count"),
                len(semantic_data),
            ),
            "effective_record_count": self._first_non_placeholder(
                overview.get("effective_record_count"),
                quality_gate.get("output_count"),
                quality_gate.get("input_count"),
                len(semantic_data),
            ),
            "time_range_start": self._first_non_placeholder(
                overview.get("time_range_start"),
                inferred_range_start,
            ),
            "time_range_end": self._first_non_placeholder(
                overview.get("time_range_end"),
                inferred_range_end,
            ),
            "latest_timestamp": self._first_non_placeholder(
                overview.get("latest_timestamp"),
                inferred_latest_timestamp,
            ),
            "latest_record_count": self._first_non_placeholder(
                overview.get("latest_record_count"),
                len(semantic_data),
            ),
            "task_note": self._first_non_placeholder(
                overview.get("task_note"),
                analysis_result.get("task_note"),
                "",
            ),
        }

    def _resolved_verification_status_code(self, analysis_result: Dict[str, Any]) -> str:
        def _normalize_status(raw: Any) -> str:
            text = str(raw or "").strip().lower()
            if text in {"passed", "pass", "success", "done", "completed", "通过", "已通过"}:
                return "passed"
            if text in {"failed", "error", "未通过", "失败"}:
                return "failed"
            if text in {"pending", "待现场验证", "待验证", "待确认"}:
                return "pending"
            return ""

        decision = analysis_result.get("decision_result") or {}
        closed_loop = decision.get("closed_loop_validation") or analysis_result.get("closed_loop_validation") or {}
        verification_raw = _normalize_status(decision.get("verification_status"))
        closed_raw = _normalize_status(closed_loop.get("status"))

        if verification_raw == "failed" or closed_raw == "failed":
            return "Failed"
        if verification_raw == "passed":
            return "Passed"
        if not verification_raw and closed_raw == "passed":
            return "Passed"
        return "Pending"

    def _normalize_step8_step_summary(self, summary: Any, analysis_result: Dict[str, Any]) -> str:
        text = self._stringify(summary, "未记录（模板占位）")
        status_text = self._verification_status_text(self._resolved_verification_status_code(analysis_result))
        normalized = re.sub(
            r"验证状态(?:为|是|=|:|：)\s*[^；;，,。\n]+",
            f"验证状态为 {status_text}",
            text,
        )
        if "验证状态" not in normalized:
            normalized = f"验证状态为 {status_text}。"
        return normalized

    def _normalize_step8_trace_output(self, output_summary: Any, analysis_result: Dict[str, Any]) -> str:
        text = self._stringify(output_summary, "未记录（模板占位）")
        status_text = self._verification_status_text(self._resolved_verification_status_code(analysis_result))
        normalized = re.sub(
            r"验证状态(?:为|是|=|:|：)\s*[^；;，,。\n]+",
            f"验证状态={status_text}",
            text,
        )
        if "验证状态" not in normalized:
            normalized = f"验证状态={status_text}；{normalized}"
        return normalized

    def _build_markdown_text_block(self, text: Any) -> List[str]:
        value = self._expand_escaped_newlines(self._render_operator_text(text, "未提供"))
        value = value.replace("。；", "；").replace("；。", "；")
        value = re.sub(r"[；;]{2,}", "；", value)
        value = re.sub(r"(?<!^)(?<!\n)\s*(\d+\))\s*", r"\n\1 ", value)
        value = re.sub(r"；(?=(?:[A-Za-z_]+：|主因：|次因：|结果影响：|证据：))", "\n", value)
        lines = [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]
        if not lines:
            return ["未提供\n"]
        return [f"{line}\n" for line in lines]

    def _split_pipe_sections(self, text: str) -> List[str]:
        value = self._stringify(text, "").strip()
        if not value:
            return []
        sections = [part.strip() for part in value.split("|") if part and part.strip()]
        return sections or [value]

    def _normalize_expert_review_text(self, text: str) -> str:
        value = self._stringify(text, "").strip()
        for prefix in (
            "专家复核：",
            "专家复核:",
            "机理一致性复核：",
            "机理一致性复核:",
            "AI复核：",
            "AI复核:",
            "复核检索：",
            "复核检索:",
        ):
            if value.startswith(prefix):
                value = value[len(prefix) :].strip()
                break
        return self._soften_root_cause_text(value)

    def _format_step_summary_lines(self, step_title: str, summary: Any) -> List[str]:
        text = self._stringify(summary, "未记录（模板占位）")
        sections = self._split_pipe_sections(text)
        if not sections:
            return ["未记录（模板占位）"]
        if len(sections) == 1:
            return [sections[0]]

        lines: List[str] = [sections[0]]
        for section in sections[1:]:
            review_text = self._normalize_expert_review_text(section)
            if review_text:
                label = self._review_section_label()
                if section.startswith("知识检索") or section.startswith("检索结论"):
                    label = "知识检索结论"
                elif section.startswith("复核检索") or section.startswith("复核结论"):
                    label = "知识校核结论"
                lines.append(f"{label}：{self._short_text(review_text, review_text, limit=140)}")
        return self._dedupe_text_items(lines) or ["未记录（模板占位）"]

    def _normalize_inline_measure_text(self, text: str) -> str:
        value = self._stringify(text, "").strip()
        if not value:
            return ""

        # Clean connector punctuation first, then split numbered fragments.
        value = value.replace("。；", "；").replace("；。", "；")
        value = re.sub(r"[；;]{2,}", "；", value)
        value = re.sub(r"\s*[；;]\s*", "；", value).strip("； ")

        numbered_chunks: List[str]
        if re.search(r"\d+\)", value):
            numbered_chunks = [chunk.strip() for chunk in re.split(r"(?=\d+\))", value) if chunk.strip()]
        else:
            numbered_chunks = [chunk.strip() for chunk in re.split(r"[；;]", value) if chunk.strip()]

        normalized: List[str] = []
        for chunk in numbered_chunks:
            cleaned = re.sub(r"[；;]+$", "", chunk).strip()
            cleaned = re.sub(r"。+$", "", cleaned).strip()
            if cleaned:
                normalized.append(cleaned)

        return "；".join(normalized) if normalized else value

    def _single_line_text(self, value: Any, fallback: str = "未说明") -> str:
        value_text = self._expand_escaped_newlines(self._render_operator_text(value, fallback))
        lines = [line.strip() for line in value_text.replace("\r\n", "\n").split("\n") if line.strip()]
        if not lines:
            return fallback
        normalized = [self._normalize_inline_measure_text(line) for line in lines]
        normalized = [line for line in normalized if line]
        return "；".join(normalized) if normalized else fallback

    def _expand_escaped_newlines(self, text: str) -> str:
        if "\\n" not in text and "\\r" not in text:
            return text
        return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")

    def _default_step_templates(self) -> List[Dict[str, Any]]:
        return [
            {"step": 1, "title": "数据加载与范围确认", "summary": "未记录（模板占位）"},
            {"step": 2, "title": "最新时刻快照提取", "summary": "未记录（模板占位）"},
            {"step": 3, "title": "状态识别与工况复核", "summary": "未记录（模板占位）"},
            {"step": 4, "title": "工况总览判断", "summary": "未记录（模板占位）"},
            {"step": 5, "title": "趋势特征与候选复核", "summary": "未记录（模板占位）"},
            {"step": 6, "title": "知识依据与处置参考", "summary": "未记录（模板占位）"},
            {"step": 7, "title": "根因诊断", "summary": "未记录（模板占位）"},
            {"step": 8, "title": "决策验证与报告生成", "summary": "未记录（模板占位）"},
        ]

    def _normalize_analysis_steps(self, analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_steps = analysis_result.get("analysis_steps") or []
        derived_summaries = self._derive_step_summaries(analysis_result)
        raw_map: Dict[int, Dict[str, Any]] = {}
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            step_value = item.get("step")
            try:
                step_id = int(step_value)
            except (TypeError, ValueError):
                continue
            raw_map[step_id] = item

        normalized: List[Dict[str, Any]] = []
        for default in self._default_step_templates():
            step_id = int(default["step"])
            raw = raw_map.get(step_id) or {}
            summary_text = raw.get("summary")
            if self._is_placeholder_value(summary_text):
                summary_text = derived_summaries.get(step_id) or default["summary"]
            if step_id == 8:
                summary_text = self._normalize_step8_step_summary(summary_text, analysis_result)
            normalized.append(
                {
                    "step": step_id,
                    "title": self._clean_step_title(raw.get("title") or default["title"]),
                    "summary": summary_text,
                }
            )
        return normalized

    def _derive_step_summaries(self, analysis_result: Dict[str, Any]) -> Dict[int, str]:
        overview = self._derive_data_overview(analysis_result)
        quality_gate = analysis_result.get("quality_gate") or {}
        baseline_profile = analysis_result.get("baseline_profile") or {}
        overall_judgement = analysis_result.get("overall_judgement") or {}
        knowledge_retrieval = analysis_result.get("knowledge_retrieval") or {}
        reasoning_result = analysis_result.get("reasoning_result") or {}
        abnormal_details = analysis_result.get("abnormal_details") or analysis_result.get("abnormal_indicators") or []

        abnormal_count = analysis_result.get("abnormal_count")
        if self._is_placeholder_value(abnormal_count):
            abnormal_count = len(abnormal_details)

        quality_status = self._first_non_placeholder(quality_gate.get("status"), analysis_result.get("status"), "UNKNOWN")
        overall_summary = self._short_text(
            overall_judgement.get("summary"),
            f"工况总览未单独输出；当前异常候选 {abnormal_count} 个。",
            limit=180,
        )
        retrieval_summary = self._short_text(
            self._clean_retrieval_summary(knowledge_retrieval.get("retrieval_summary")),
            "本轮未检索到可追溯知识条目。",
            limit=180,
        )
        diagnosis_summary = self._short_text(
            self._soften_root_cause_text(reasoning_result.get("root_cause")) or reasoning_result.get("thought_process"),
            "本轮未执行根因诊断。",
            limit=180,
        )
        verification_status = self._verification_status_text(self._resolved_verification_status_code(analysis_result))

        return {
            1: (
                f"完成数据加载并通过质量门禁（状态={quality_status}），"
                f"有效记录={overview.get('effective_record_count')}。"
            ),
            2: (
                f"提取最新快照时刻={overview.get('latest_timestamp')}，"
                f"快照指标数={overview.get('latest_record_count')}。"
            ),
            3: f"语义分析完成，异常候选={abnormal_count} 个。",
            4: overall_summary,
            5: f"历史基线覆盖指标={baseline_profile.get('tag_count', 0)} 个，完成趋势特征复核。",
            6: retrieval_summary,
            7: diagnosis_summary,
            8: f"验证状态为 {verification_status}。",
        }

    def _normalize_duration_ms(self, value: Any) -> int:
        try:
            parsed = int(float(value))
            return parsed if parsed > 0 else 1
        except (TypeError, ValueError):
            return 1

    def _normalize_step_traces(
        self,
        raw_step_traces: List[Dict[str, Any]],
        analysis_steps: List[Dict[str, Any]],
        analysis_result: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        fallback_traces = self._derive_step_trace_defaults(analysis_steps, analysis_result or {})
        trace_map: Dict[int, Dict[str, Any]] = {}
        for item in raw_step_traces or []:
            if not isinstance(item, dict):
                continue
            try:
                step_id = int(item.get("step"))
            except (TypeError, ValueError):
                continue
            trace_map[step_id] = item

        normalized: List[Dict[str, Any]] = []
        for step in analysis_steps:
            step_id = int(step.get("step", 0))
            raw = trace_map.get(step_id) or {}
            fallback = fallback_traces.get(step_id) or {}

            def _pick(raw_value: Any, fallback_value: Any, default: str = "未记录（模板占位）") -> Any:
                if not self._is_placeholder_value(raw_value):
                    return raw_value
                if not self._is_placeholder_value(fallback_value):
                    return fallback_value
                return default

            output_summary = _pick(raw.get("output_summary"), fallback.get("output_summary"))
            if step_id == 8 and analysis_result is not None:
                output_summary = self._normalize_step8_trace_output(output_summary, analysis_result)
            normalized.append(
                {
                    "step": step_id,
                    "title": self._clean_step_title(_pick(raw.get("title"), step.get("title"), "未记录（模板占位）")),
                    "started_at": _pick(raw.get("started_at"), fallback.get("started_at")),
                    "ended_at": _pick(raw.get("ended_at"), fallback.get("ended_at")),
                    "duration_ms": self._normalize_duration_ms(_pick(raw.get("duration_ms"), fallback.get("duration_ms"), 1)),
                    "input_summary": _pick(raw.get("input_summary"), fallback.get("input_summary")),
                    "processing_summary": _pick(raw.get("processing_summary"), fallback.get("processing_summary")),
                    "output_summary": output_summary,
                    "manual_verification": _pick(raw.get("manual_verification"), fallback.get("manual_verification")),
                    "interaction_checkpoint": raw.get("interaction_checkpoint") or "",
                    "interaction_response": _pick(raw.get("interaction_response"), fallback.get("interaction_response"), "未触发"),
                    "llm_tasks": raw.get("llm_tasks") if isinstance(raw.get("llm_tasks"), list) else [],
                }
            )
        return normalized

    def _derive_step_trace_defaults(
        self,
        analysis_steps: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
    ) -> Dict[int, Dict[str, Any]]:
        traceability = analysis_result.get("traceability") or {}
        generated_at = self._first_non_placeholder(
            traceability.get("generated_at"),
            analysis_result.get("timestamp"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        overview = self._derive_data_overview(analysis_result)
        derived_summaries = self._derive_step_summaries(analysis_result)

        default_input = {
            1: f"输入文件={overview.get('file_name')}。",
            2: f"上一阶段有效记录={overview.get('effective_record_count')}。",
            3: f"快照指标数={overview.get('latest_record_count')}。",
            4: "语义分析结果与异常详情。",
            5: "异常候选与历史基线。",
            6: "工况总览、异常候选与任务备注。",
            7: "语义异常、知识检索结果与工况判断。",
            8: "根因结论、知识检索结论与决策验证输入。",
        }
        default_processing = {
            1: "完成数据加载、标准化与质量门禁校验。",
            2: "提取最新时刻快照并确认指标覆盖。",
            3: "执行规则判定与语义复核，定位异常候选。",
            4: "汇总系统风险等级并形成工况总览。",
            5: "结合历史基线进行趋势识别与候选复核。",
            6: "执行外挂知识库 API 检索并汇总依据。",
            7: "执行根因诊断与安全边界推断。",
            8: "执行决策验证并生成执行建议报告。",
        }
        default_manual = {
            1: "核对文件来源、时间范围与质量门禁结论。",
            2: "确认最新快照时刻与快照指标覆盖。",
            3: "抽检重点异常指标与判定原因一致性。",
            4: "确认总览风险等级与现场观测一致。",
            5: "确认持续偏离与短时波动区分结果。",
            6: "核对检索依据是否匹配现场工况边界。",
            7: "确认根因链路与关键证据匹配。",
            8: "执行前复核操作步骤、风险与回退策略。",
        }

        fallback: Dict[int, Dict[str, Any]] = {}
        for step in analysis_steps:
            step_id = int(step.get("step") or 0)
            if step_id <= 0:
                continue
            fallback[step_id] = {
                "step": step_id,
                "title": self._clean_step_title(step.get("title") or ""),
                "started_at": generated_at,
                "ended_at": generated_at,
                "duration_ms": 1,
                "input_summary": default_input.get(step_id, "本步骤输入已记录在主流程日志。"),
                "processing_summary": default_processing.get(step_id, "本步骤处理过程见主流程日志。"),
                "output_summary": derived_summaries.get(step_id, "本步骤完成，详见对应章节。"),
                "manual_verification": default_manual.get(step_id, "请按现场标准流程完成核验。"),
                "interaction_response": "未触发",
            }
        return fallback

    def _clean_step_title(self, title: Any) -> str:
        text = self._stringify(title, "未记录（模板占位）")
        lowered = text.lower()
        if "dify" in lowered:
            return "知识依据与处置参考"
        if "ai" in lowered and "根因" in text:
            return "根因诊断"
        if "direct" in lowered:
            text = re.sub(r"(?i)\bdirect\b", "", text).strip(" -_")
        text = text.replace("知识库检索手段", "知识依据与处置参考")
        text = text.replace("知识检索与候选措施整理", "知识依据与处置参考")
        text = text.replace("规则预筛与语义复核", "状态识别与工况复核")
        text = text.replace("时序特征提取与候选复核", "趋势特征与候选复核")
        return text or "未记录（模板占位）"

    def _build_state_counts(self, semantic_data: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in semantic_data:
            state = item.get("state_desc", "Unknown")
            counts[state] = counts.get(state, 0) + 1
        return counts

    def _select_abnormal_items(self, semantic_data: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        abnormal_states = {"异常", "较差", "差", "偏差较大", "偏离显著", "偏高", "偏低", "严重偏高", "严重偏低"}
        items = [item for item in semantic_data if item.get("state_desc") in abnormal_states]
        return sorted(items, key=lambda item: abs(item.get("diff", 0.0)), reverse=True)

    def _normalize_report_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._normalize_report_text(value)
        if isinstance(value, list):
            return [self._normalize_report_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._normalize_report_value(item) for key, item in value.items()}
        return value

    def _normalize_report_text(self, text: str) -> str:
        if not text:
            return text
        text = repair_llm_text(text)
        mojibake_hint_chars = (
            "ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞß"
            "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
            ""
        )
        mojibake_hint_re = re.compile(f"[{re.escape(mojibake_hint_chars)}]")

        def decode_whole_latin1_if_better(line: str) -> str:
            if any("\u4e00" <= ch <= "\u9fff" for ch in line):
                return line
            try:
                raw = line.encode("latin1", errors="strict")
                decoded = raw.decode("utf-8", errors="strict")
            except Exception:
                return line
            return decoded if self._noise_score(decoded) < self._noise_score(line) else line

        def decode_mixed_hex_escape(line: str) -> str:
            if "\\x" not in line:
                return line

            def repl(match: re.Match[str]) -> str:
                segment = match.group(0)
                buf: List[int] = []
                i = 0
                while i < len(segment):
                    if (
                        i + 3 < len(segment)
                        and segment[i] == "\\"
                        and segment[i + 1] == "x"
                        and all(c in "0123456789abcdefABCDEF" for c in segment[i + 2 : i + 4])
                    ):
                        buf.append(int(segment[i + 2 : i + 4], 16))
                        i += 4
                        continue
                    ch = segment[i]
                    if ord(ch) > 255:
                        return segment
                    buf.append(ord(ch))
                    i += 1
                raw = bytes(buf)
                for enc in ("utf-8", "gb18030", "gbk"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return segment

            return re.sub(r"(?:\\x[0-9A-Fa-f]{2}|[ -~\x80-\xff]){8,}", repl, line)

        def decode_latin1_segments(line: str) -> str:
            if not any(ord(ch) >= 128 for ch in line):
                return line
            if not mojibake_hint_re.search(line):
                return line

            def repl(match: re.Match[str]) -> str:
                segment = match.group(0)
                try:
                    return segment.encode("latin1", errors="strict").decode("utf-8", errors="strict")
                except Exception:
                    return segment

            repaired = re.sub(r"[\x80-\xff]{2,}", repl, line)
            return re.sub(r"[\x80-\xff]{2,}", repl, repaired)

        repaired_lines = []
        for raw_line in text.splitlines():
            fixed = repair_llm_text(raw_line)
            fixed = decode_whole_latin1_if_better(fixed)
            fixed = decode_mixed_hex_escape(fixed)
            fixed = decode_latin1_segments(fixed)
            repaired_lines.append(fixed)

        repaired = "\n".join(repaired_lines)
        if text.endswith("\n"):
            repaired += "\n"
        return self._clean_business_text(repaired)

    def _noise_score(self, text: str) -> int:
        mojibake_chars = set(
            "ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞß"
            "àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ"
            ""
        )
        score = len(re.findall(r"\\x[0-9A-Fa-f]{2}", text))
        score += len(re.findall(r"[ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]{4,}", text))
        score += sum(1 for ch in text if ch in mojibake_chars or ch == "\ufffd")
        score += text.count("\ufffe") + text.count("\uffff")
        return score

    def _contains_mojibake_marker(self, text: str) -> bool:
        if not text:
            return False
        if any(token in text for token in ("\ufffd", "\ufffe", "\uffff")):
            return True
        if re.search(r"\\x[0-9A-Fa-f]{2}", text):
            return True
        return bool(re.search(r"[ÃÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]", text))

    def _is_text_noisy(self, text: str) -> bool:
        score = self._noise_score(text)
        if score >= 8:
            return True
        return score >= 2 and self._contains_mojibake_marker(text)

    def _stringify_trace_output(self, value: Any, fallback: str) -> str:
        text = self._expand_escaped_newlines(self._stringify(value, fallback)).replace("\r\n", "\n")
        text = " ".join(text.split()).strip()
        if self._is_text_noisy(text):
            return "该步骤采用结构化结论呈现，详见下方“诊断结论/执行建议”章节。"
        text = self._soften_root_cause_text(text)
        if ("{" in text or "[" in text) and ("..." in text or len(text) > 220):
            return "已生成结构化诊断结果，详见下方“诊断结论/执行建议”章节。"
        if len(text) > 220:
            return f"{text[:220].rstrip()}..."
        return self._clean_business_text(text)

    def _render_operator_text(self, value: Any, fallback: str = "未提供") -> str:
        if value is None:
            return fallback

        normalized = self._normalize_report_value(value)
        if isinstance(normalized, (dict, list)):
            return self._format_structured_payload(normalized, fallback)

        text = self._normalize_report_text(str(normalized)).strip()
        parsed_literal = self._try_parse_literal_payload(text)
        if parsed_literal is not None:
            return self._format_structured_payload(parsed_literal, fallback)
        return text or fallback

    def _try_parse_literal_payload(self, text: str) -> Optional[Any]:
        stripped = text.strip()
        if len(stripped) < 2 or stripped[0] not in "[{":
            return None
        try:
            payload = json.loads(stripped)
            if isinstance(payload, (dict, list)):
                return payload
        except Exception:
            pass
        try:
            payload = ast.literal_eval(stripped)
        except Exception:
            return None
        return payload if isinstance(payload, (dict, list)) else None

    def _format_structured_payload(self, payload: Any, fallback: str = "未提供") -> str:
        if isinstance(payload, dict):
            line = self._format_structured_item(payload)
            return line or fallback

        if isinstance(payload, list):
            lines: List[str] = []
            for idx, item in enumerate(payload, start=1):
                rendered = self._format_structured_item(item)
                if rendered:
                    lines.append(f"{idx}) {rendered}")
            return "\n".join(lines) if lines else fallback

        return self._stringify(payload, fallback)

    def _format_structured_item(self, item: Any) -> str:
        if isinstance(item, dict):
            key_alias = {
                "primary_cause": "主因",
                "secondary_causes": "次因",
                "resulting_effects": "结果影响",
                "risk_level_judgement": "风险判定",
                "priority": "优先级",
                "target_issue": "针对问题",
                "steps": "操作要点",
                "expected_effect": "预期效果",
                "safety_note": "安全边界",
                "source": "来源",
                "title": "标题",
                "content": "要点",
                "snippet": "要点",
                "summary": "要点",
                "page": "位置",
                "section": "位置",
                "chapter": "位置",
                "relevance_score": "相关度",
            }
            ordered_keys = [
                "根因级别",
                "根因描述",
                "证据",
                "优级",
                "建议",
                "操作要点",
                "目标问题",
                "针对问题",
                "预期效果",
                "安全提示",
                "primary_cause",
                "secondary_causes",
                "resulting_effects",
                "risk_level_judgement",
            ]
            remaining_keys = [key for key in item.keys() if key not in ordered_keys]
            keys = [key for key in ordered_keys if key in item] + remaining_keys
            parts: List[str] = []
            for key in keys:
                if key in {"confidence", "confidence_score", "unit_confidence"}:
                    continue
                rendered = self._render_structured_value(item.get(key))
                if rendered:
                    display_key = key_alias.get(key, key)
                    parts.append(f"{display_key}：{rendered}")
            return "；".join(parts)

        return self._render_structured_value(item)

    def _render_structured_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            values = [self._render_structured_value(v) for v in value]
            compact = [v for v in values if v]
            return "；".join(compact)
        if isinstance(value, dict):
            return self._format_structured_item(value)
        return self._clean_business_text(self._normalize_report_text(str(value))).strip()

    def _stringify(self, value: Any, fallback: str = "未提供") -> str:
        if value is None:
            return fallback
        value = self._normalize_report_value(value)
        if isinstance(value, list):
            if all(not isinstance(item, (dict, list)) for item in value):
                value = "\n".join(str(item) for item in value if item is not None)
            else:
                value = json.dumps(value, ensure_ascii=False, indent=2)
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        text = self._clean_business_text(self._normalize_report_text(str(value))).strip()
        return text or fallback

    def _to_pdf_html(self, value: Any, fallback: str = "未提供") -> str:
        return html.escape(self._stringify(value, fallback)).replace("\n", "<br/>")

    def _pdf_rich_text(self, value: Any, fallback: str = "未提供") -> str:
        text = self._stringify(value, fallback)
        return self._apply_pdf_emphasis(text)

    def _apply_pdf_emphasis(self, text: str) -> str:
        if not text:
            return ""

        spans: List[Tuple[int, int]] = []
        literal_terms = sorted(
            {
                "高风险",
                "中风险",
                "低风险",
                "异常失稳态",
                "风险上升态",
                "优先核查对象",
                "疑似根因链起点",
                "不等于已确认根因",
                "需现场确认",
                "严重偏高",
                "严重偏低",
                "偏高",
                "偏低",
                "先核",
                "先查",
                "复核",
                "确认",
                "回退",
                "降负荷",
            },
            key=len,
            reverse=True,
        )
        if literal_terms:
            literal_pattern = re.compile("|".join(re.escape(term) for term in literal_terms))
            spans.extend((match.start(), match.end()) for match in literal_pattern.finditer(text))

        label_pattern = re.compile(
            r"(当前状态|主问题|立即动作|必查项|验收门槛|回退条件|总体判断|当前与历史|当前发生了什么|"
            r"当前值|偏差|状态|时间窗口|异常起点|持续时长|执行步骤|风险评估|回退策略|"
            r"安全提示|操作建议|已确认依据|待现场核查项)(?=[：:])"
        )
        spans.extend((match.start(), match.end()) for match in label_pattern.finditer(text))

        percent_pattern = re.compile(r"[+-]?\d+(?:\.\d+)?[%％]")
        spans.extend((match.start(), match.end()) for match in percent_pattern.finditer(text))

        count_pattern = re.compile(r"\d+(?:\.\d+)?\s*(?:项|个|点|次|ms|小时|分钟)")
        spans.extend((match.start(), match.end()) for match in count_pattern.finditer(text))

        metric_value_pattern = re.compile(
            r"([：:]\s*)([+-]?\d+(?:\.\d+)?(?:\s?(?:kW|MPa|bar|℃|%|Nm3/h|m3/h|kg/h|t/h|A|V))?)"
        )
        for match in metric_value_pattern.finditer(text):
            spans.append(match.span(2))

        if not spans:
            return html.escape(text).replace("\n", "<br/>")

        merged: List[List[int]] = []
        for start, end in sorted(spans, key=lambda item: (item[0], item[1])):
            if start >= end:
                continue
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        parts: List[str] = []
        cursor = 0
        for start, end in merged:
            if cursor < start:
                parts.append(html.escape(text[cursor:start]).replace("\n", "<br/>"))
            parts.append(f"<b>{html.escape(text[start:end]).replace('\n', '<br/>')}</b>")
            cursor = end
        if cursor < len(text):
            parts.append(html.escape(text[cursor:]).replace("\n", "<br/>"))
        return "".join(parts)

    def _format_number(self, value: Any, digits: int = 2) -> str:
        try:
            precision = max(int(digits), 0)
            return f"{float(value):.{precision}f}"
        except (TypeError, ValueError):
            return "-"

    def _format_percent(self, value: Any) -> str:
        try:
            return f"{float(value):.1%}"
        except (TypeError, ValueError):
            return "-"

    def _format_diff_percent_text(self, value: Any) -> str:
        try:
            percent = float(value)
        except (TypeError, ValueError):
            return ""
        sign = "+" if percent >= 0 else ""
        return f" ({sign}{percent:.1f}%)"

    def _format_window_text(self, item: Dict[str, Any]) -> str:
        window = item.get("window") or {}
        start = self._stringify(window.get("start"), "时间窗口未识别")
        end = self._stringify(window.get("end"), "时间窗口未识别")
        if start == "时间窗口未识别" or end == "时间窗口未识别":
            return "时间窗口未识别"
        if window.get("is_ongoing"):
            return f"{start} 至当前快照"
        return f"{start} 至 {end}"

    def _get_status_badge(self, status: str) -> str:
        badges = {
            "healthy": '<font color="#15803d">正常</font>',
            "abnormal": '<font color="#b91c1c">异常</font>',
            "error": '<font color="#b45309">错误</font>',
        }
        return badges.get(status, html.escape(self._stringify(status)))

    def _get_verification_badge(self, status: str) -> str:
        badges = {
            "Passed": '<font color="#15803d">通过</font>',
            "Failed": '<font color="#b91c1c">失败</font>',
            "Pending": '<font color="#b45309">待现场验证</font>',
        }
        return badges.get(status, html.escape(self._stringify(status)))

    def generate_both_formats(self, analysis_result: Dict[str, Any], base_filename: Optional[str] = None) -> Tuple[str, str]:
        if not base_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"analysis_report_{timestamp}"

        pdf_path = self.generate_pdf_report(analysis_result, f"{base_filename}.pdf")
        md_path = self.generate_markdown_report(analysis_result, f"{base_filename}.md")
        return pdf_path, md_path
