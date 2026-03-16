# Agentic AI for Data Engineering CI/CD (Local-First)

## Purpose
This project implements a local-first, human-in-the-loop agentic workflow for data engineering delivery using Microsoft services:
- Azure DevOps Boards (PBI/bug/user story intake)
- Azure Databricks Unity Catalog workspaces (dev/qe/stg/prod)
- Azure Pipelines CI/CD promotion
- Chatbot/API approval checkpoints for safe deployments

The current implementation is an MVP foundation that runs fully local while preserving production-ready integration paths in code (commented/instructional blocks included in adapters).

## Architecture (Local Runtime)
```text
Azure DevOps Work Items (mock/local JSON or REST)
            |
            v
Requirement Agent --> Implementation Agent --> Databricks Adapter (dev/qe/stg/prod)
            |                                          |
            v                                          v
      Human Approval Service <---- Chat API ---- Azure Pipelines Adapter
            |
            v
      QA Agent + Promotion Agent
            |
            v
      Learning Store (state/learning_memory.json)

Observability:
- logs/project_master.log (aggregate)
- module logs (azure_devops.log, databricks.log, azure_pipelines.log, orchestrator.log, etc.)
```

## Folder Structure
- `main.py` - single entry point (run once, loop, chatbot server)
- `src/agentic_de_pipeline/` - modular source package
- `config/config_local.yaml` - local settings
- `config/config_prod.yaml` - production template settings
- `sample_data/work_items.json` - local work-item mock input
- `tests/` - unit, integration, regression suites
- `state/` - approvals + learning persistence
- `logs/` - runtime logs

## Prerequisites
- Python 3.11+

## Local Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run tests:
   ```bash
   pytest
   ```

3. Process one work item:
   ```bash
   python main.py --config config/config_local.yaml run-once
   ```

4. Start chatbot approval API:
   ```bash
   python main.py --config config/config_local.yaml serve-chat --host 0.0.0.0 --port 8000
   ```

5. Trigger processing via API:
   ```bash
   curl -X POST http://localhost:8000/workflow/process-next
   ```

6. View pending approvals:
   ```bash
   curl http://localhost:8000/approvals/pending
   ```

7. Submit decision:
   ```bash
   curl -X POST "http://localhost:8000/approvals/<request_id>/decision" \
     -H "Content-Type: application/json" \
     -d '{"approved": true, "approver": "engineer@local", "comment": "Looks good"}'
   ```

## Local Security Notes
- Never hardcode secrets.
- For production mode, set secrets via env vars:
  - `AZDO_PAT`
  - `DATABRICKS_TOKEN`

## Logging
- Master log: `logs/project_master.log`
- Module logs:
  - `logs/azure_devops.log`
  - `logs/databricks.log`
  - `logs/azure_pipelines.log`
  - `logs/orchestrator.log`
  - `logs/approvals.log`
  - plus agent-specific logs

Each operation logs start/end, duration, errors, and resource metrics (CPU time + memory high-water mark).

## Changelog
- **2026-03-16**: Initial MVP scaffold created (orchestrator, adapters, HITL approvals, chatbot API, local config, tests).
