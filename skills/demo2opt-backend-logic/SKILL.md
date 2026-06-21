---
name: demo2opt-backend-logic
description: Explain, debug, validate, or extend the backend of the demo2opt project. Use when Codex needs to understand the end-to-end analysis pipeline, WebSocket task flow, REST endpoints, task persistence, LLM reasoning, decision generation, report output, or the runtime relationship between frontend and backend in this repository.
---

# Demo2Opt Backend Logic

## Overview

Use this skill to build context for the `demo2opt` backend before changing code or explaining behavior. Focus on the WebSocket analysis pipeline first, then use REST and task persistence as supporting context.

Read [references/backend-map.md](references/backend-map.md) when you need concrete file locations, endpoint lists, result fields, or the startup topology.

## Working Order

Follow this order unless the user asks for a narrower slice:

1. Read [`src/api/ws/server.py`](../../src/api/ws/server.py) to understand the live analysis pipeline.
2. Read [`src/services/reasoning_engine_v2.py`](../../src/services/reasoning_engine_v2.py) and [`src/prompts/templates.py`](../../src/prompts/templates.py) to understand LLM execution, JSON normalization, and Chinese-output constraints.
3. Read [`src/services/decision_service.py`](../../src/services/decision_service.py) and [`src/utils/report_generator.py`](../../src/utils/report_generator.py) to understand recommendation and report generation.
4. Read [`src/core/task_manager.py`](../../src/core/task_manager.py) to understand persistence, stale-task repair, and task status transitions.
5. Read [`src/api/rest/server.py`](../../src/api/rest/server.py) only for config and task-query behavior.

## Backend Mental Model

Treat the backend as an asynchronous analysis engine, not a CRUD service.

- `REST` handles health, model preset retrieval, preset persistence, task listing, task detail lookup, and cleanup.
- `WebSocket` owns the actual analysis lifecycle: input file resolution, interaction prompts, semantic analysis, LLM reasoning, decision generation, progress events, monitor updates, and final result delivery.
- `TaskManager` is shared state and on-disk persistence under `task_progress/`.
- `reports/` stores generated Markdown and PDF output.

## Canonical Runtime Flow

Use this exact flow when explaining behavior or tracing bugs:

1. Frontend sends `start` over WebSocket with `mode`, optional file payload, and either `dify_config` or `llm_config`.
2. WebSocket creates a task and marks it `processing`.
3. `ExcelDataLoader` loads records. If no file is uploaded, the backend falls back to the first usable Excel file under `data/`.
4. Backend asks for a time-range confirmation.
5. `DataSemanticsService` computes semantic results and abnormal indicators from the latest timestamp slice.
6. Backend emits `monitor_update` with stage `semantic_ready`.
7. Backend asks whether to continue into AI diagnosis when abnormalities exist.
8. `ReasoningEngineV2` calls `DifyAPIClient` or `SimpleLLMClient`.
9. `ReasoningEngineV2` normalizes the LLM result into the required JSON schema. For `direct` mode, it also tries second-pass reformatting when the first response is not parseable JSON.
10. `DecisionService` converts the reasoning result into actionable steps, warnings, and case output.
11. Backend emits `monitor_update` with stage `decision_ready`.
12. `ReportGenerator` writes PDF and Markdown files.
13. Backend sends `result`, marks the task `completed`, and persists the task snapshot.

## Event Contract

When aligning frontend and backend, assume these WebSocket events matter:

- `log`
- `phase_update`
- `interaction`
- `monitor_update`
- `result`

Assume the frontend monitor panel should refresh from `monitor_update` before the final `result`. If the user says the monitor is not real-time, verify that the backend emitted `monitor_update` before debugging the UI.

## LLM Rules

Keep these rules in mind before changing prompts or model handling:

- The project no longer treats `mock` as a valid backend reasoning mode.
- `direct` mode uses OpenAI-compatible chat APIs and may need stream aggregation fallback.
- The prompt layer is expected to return structured JSON.
- Report-facing fields must be Chinese. Keep this requirement in `src/prompts/templates.py`.
- If model output fails JSON parsing, investigate `ReasoningEngineV2._parse_llm_response()` first.

## Safe Debug Workflow

Use this sequence for runtime verification:

1. Run `python -m compileall src main.py scripts`.
2. Build frontend with `npm run build` in `frontend/` when UI code changed.
3. Check REST health with `GET /api/health`.
4. Run a real WebSocket analysis and auto-answer interactions with `yes`.
5. Confirm `monitor_update` arrives before `result`.
6. Confirm `reasoning_result` contains Chinese text.

## Change Heuristics

Use these guardrails when modifying the backend:

- Change `src/api/ws/server.py` when the event flow, task lifecycle, monitor updates, or interaction sequence is wrong.
- Change `src/api/rest/server.py` when config persistence or task query behavior is wrong.
- Change `src/core/task_manager.py` when task status persistence, stale processing repair, or task listing behavior is wrong.
- Change `src/services/reasoning_engine_v2.py` or `src/prompts/templates.py` when LLM configuration, output parsing, stream handling, or language/JSON constraints are wrong.
- Change `src/services/decision_service.py` when suggestions or downstream action formatting are wrong.
- Change `src/utils/report_generator.py` when PDF/Markdown output structure is wrong.

## What To Avoid

- Do not describe the backend as a normal REST CRUD system.
- Do not remove the explicit failure path for missing model configuration.
- Do not silently reintroduce `mock` execution paths.
- Do not treat final report generation as the first point where monitoring data becomes available.
