# Agentic AI for Data Engineering CI/CD (Local-First)

## Purpose
This project implements a local-first, human-in-the-loop agentic workflow for data engineering delivery using Microsoft services:
- Azure DevOps Boards (PBI/bug/user story intake)
- Azure Repos (branch + PR automation)
- Azure Pipelines CI/CD promotion
- Azure Databricks Unity Catalog workspaces (dev/qe/stg/prod)
- Chatbot/API approval checkpoints for safe deployments

## What this build now supports
1. Reads DevOps work items and ranks by **priority**.
2. Infers target repo from tags (example: `repo:data-engineering-repo`) or default config.
3. Generates branch name with work item ID (`feature/pbi-<id>-...`).
4. Executes developer workflow (branch, basic tests, commit/push, PR hook).
5. Runs stage flow Dev -> QE -> STG -> PROD with mandatory approvals.
6. Keeps learning memory for future ranking/context.
7. Uses prompt templates and optional hosted LLM endpoint.
8. Supports MCP server configuration snapshot for tool integrations.

## Architecture (Local Runtime)
```text
Azure DevOps Work Items (mock/local JSON or REST)
            |
            v
Requirement Agent (Prompt + MCP context)
            |
            v
Developer Workflow Service -> Azure Repos (branch/tests/commit/push/PR)
            |
            v
Databricks + Azure Pipelines + QA + Promotion Agent
            |
            v
Human Approval Service (QE/STG/PROD gates via API/Console)
            |
            v
Learning Store (state/learning_memory.json)
```

## Config you need (`config/config_local.yaml`)
You can provide all service links directly:
- Azure DevOps: `organization_url`, `project`, `board_url`
- Azure Repos: `repository_url`, `repository_name`
- Azure Pipelines: `pipeline_url`
- Databricks: workspace URLs (for your current model, DEV is enough)

### Workflow model for "DEV Databricks + Pipeline promotions"
Use:
- `workflow.stage_sequence: ["dev","qe","stg","prod"]`
- `workflow.databricks_apply_in_stages: ["dev"]`
- `workflow.hil_approval_stages: ["qe","stg","prod"]`

This means the agent changes Databricks only in DEV, then drives QE/STG/PROD through pipeline runs with human approvals.

### Token options
Each integration accepts either:
- direct token in config (example `personal_access_token`, `token`), or
- env var reference (`*_env` fields).

> Recommended for real usage: keep token fields empty and use environment variables.

## Local Setup
1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. Run tests:
   ```bash
   python3 -m pytest
   ```

3. Process one work item:
   ```bash
   python3 main.py --config config/config_local.yaml run-once
   ```

4. Start chatbot approval API:
   ```bash
   python3 main.py --config config/config_local.yaml serve-chat --host 0.0.0.0 --port 8000
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

## Runtime and safety flags
- `azure_repos.dry_run: true` => simulate branch/commit/push/PR calls safely.
- `runtime.enable_repo_automation: true` => enable repository lifecycle automation.
- `runtime.run_basic_tests: true` + `runtime.basic_test_command` => local validation command.
- `workflow.*` => control stage order, where Databricks is executed, and where HIL approval is required.

## Logging
- Master log: `logs/project_master.log`
- Module logs:
  - `logs/azure_devops.log`
  - `logs/azure_repos.log`
  - `logs/databricks.log`
  - `logs/azure_pipelines.log`
  - `logs/orchestrator.log`
  - `logs/approvals.log`
  - plus agent/service logs

## Changelog
- **2026-03-16**: Added priority-based intake, repo automation flow, prompts/MCP config, and token-capable service configuration.
