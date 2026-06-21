# Demo2Opt Backend Map

## Entrypoints

- `main.py`
  Legacy local orchestration entry. Useful for understanding the original single-process flow.
- `scripts/start_web.py`
  Starts REST on port `5000` and WebSocket on port `8001`.
- `src/api/rest/server.py`
  Flask server for health, config, and task queries.
- `src/api/ws/server.py`
  WebSocket server for the live analysis pipeline.

## Runtime Data Flow

1. Frontend sends `start`.
2. WebSocket resolves file input.
3. `src/services/data_loader.py` loads and standardizes Excel records.
4. `src/services/data_semantics.py` converts latest records into semantic state and abnormal indicators.
5. `src/services/reasoning_engine_v2.py` invokes:
   - `src/prompts/templates.py` `SimpleLLMClient` for direct LLM
   - `src/prompts/templates.py` `DifyAPIClient` for Dify
6. `src/services/decision_service.py` generates downstream recommendations.
7. `src/utils/report_generator.py` generates Markdown and PDF reports.
8. `src/core/task_manager.py` persists task state under `task_progress/`.

## REST Endpoints

- `GET /api/health`
- `GET /api/configs`
- `POST /api/configs`
- `GET /api/tasks`
- `GET /api/tasks/<task_id>`
- `GET /api/tasks/<task_id>/progress`
- `POST /api/tasks/cleanup`

Use REST for:

- model preset retrieval and persistence
- task list and task detail lookup
- health checks
- stale task cleanup

Do not use REST to start the analysis pipeline.

## WebSocket Events

### Client to server

- `start`
- `interaction_response`

### Server to client

- `log`
- `phase_update`
- `interaction`
- `monitor_update`
- `result`

## Important Result Fields

The final `result.data` payload is expected to include:

- `report_pdf`
- `report_md`
- `abnormal_indicators`
- `reasoning_result`
- `decision_suggestion`
- `warning`
- `semantic_data`

The monitor panel should consume:

- `monitor_update.data.semantic_data`
- `monitor_update.data.abnormal_indicators`
- `monitor_update.data.stage`

## Task Persistence

- Directory: `task_progress/`
- One JSON file per task
- Status values:
  - `pending`
  - `processing`
  - `completed`
  - `failed`

Use `scripts/fix_task_statuses.py` when stale `processing` tasks need repair.

## Common Investigation Targets

### Monitor panel not updating

- Check that `src/api/ws/server.py` emits `monitor_update`.
- Confirm it happens before `result`.
- Then inspect frontend `handleWsMessage`.

### LLM returns non-JSON

- Check `src/services/reasoning_engine_v2.py`.
- Check `src/prompts/templates.py`.
- Verify direct mode stream fallback still works.

### Report not in Chinese

- Check `src/prompts/templates.py` prompts first.
- Then inspect result normalization in `src/services/reasoning_engine_v2.py`.

### Task stuck in processing

- Check exception handling in `src/api/ws/server.py`.
- Check persistence in `src/core/task_manager.py`.
- Use `scripts/fix_task_statuses.py` if the state is already stale on disk.
