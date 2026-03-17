# Production Upgrade Guide (Microsoft Stack)

## Goal
Deploy this agentic CI/CD system in enterprise environments using:
- Azure DevOps Boards + Repos + Pipelines
- Azure Databricks Unity Catalog workspaces per environment
- Hosted LLM endpoint + optional MCP tool servers
- Human approvals at promotion gates

## Enterprise capability map
- Priority-based intake from PBIs/Bugs/User Stories
- Repo identification from work-item tags or default repo config
- Branch-per-work-item automation (`feature/pbi-<id>-...`)
- New repository provisioning when required (config-controlled)
- Developer checks before CI/CD
- PR creation hooks for QE promotion workflows
- Stage-by-stage approvals and test controls
- Clarification loop for incomplete requirements with DevOps discussion audit record
- Preflight connectivity validation and fail-fast startup
- Retry policy for transient external API failures
- Idempotent work-item processing to avoid duplicate deployments
- Failure remediation loop with HIL approvals before fix attempts

## Config strategy
Use `config/config_connected.yaml` and provide:
- DevOps board URL + organization/project
- Repos URL + repository
- Pipelines URL/prefix
- Databricks workspace URLs (DEV required; QE/STG/PROD optional if pipelines own promotion)
- Prompt and MCP configuration

### Why two YAML files?
- `config/config_simulate.yaml` is for safe dry-run/mock iterations.
- `config/config_connected.yaml` is for real service endpoints, stricter approvals, and hosted LLM/MCP wiring.

Keeping them separate avoids accidental production calls during development.

### Runtime profile model (updated)
- `integration_mode: "simulate"` means dry-run/mock integration behavior.
- `integration_mode: "connected"` means real Azure service calls.
- `deployment_strategy: "dev_first_promotion"` captures your architecture intent explicitly.
- `security.strict_private_mode: true` enforces private/internal LLM and MCP endpoints.

### Recommended workflow for your current model
If Databricks changes are done in DEV and Azure Pipelines handles promotions, keep:
- `workflow.stage_sequence: ["dev","qe","stg","prod"]`
- `workflow.databricks_apply_in_stages: ["dev"]`
- `workflow.hil_approval_stages: ["qe","stg","prod"]`
- `runtime.require_preflight_before_run: true`
- `runtime.enable_idempotency: true`

### Token handling
Supported in code:
- direct token fields in config (for isolated PoC only)
- environment variable fallback via `*_env` fields

Production recommendation:
1. Keep direct token fields empty.
2. Inject secrets through Key Vault / secure runtime env vars.
3. Rotate PAT/tokens and apply least privilege.

## Target Architecture
```text
Azure DevOps Board --> Orchestrator VM/Service --> Azure Repos (branch/PR)
                                |                        |
                                |                        v
                                |                   Azure Pipelines
                                |                        |
                                v                        v
                       Approval Chatbot/API --> Databricks env rollout
                                |
                                v
                         Human RFC/CAB approvals

Cross-cutting:
- Prompt engine + hosted LLM
- MCP server connectors
- Azure Monitor / SIEM logging
- Audit trace for approvals and releases
```

## Hardening Checklist
- [ ] Azure AD service principals / managed identity
- [ ] Key Vault for all secrets
- [ ] TLS everywhere
- [ ] RBAC on approval APIs
- [ ] Environment-specific guardrails and release policies
- [ ] Dependency and code security scans in CI
- [ ] Immutable audit evidence for approvals and deployments

## Chatbot / HIL enhancements now available
- `GET /approvals/pending-with-suggestions`
- `GET /approvals/{request_id}/suggestion`
- `GET /preflight/run`
- Browser HIL console at `GET /ui` (chat + approvals + clarifications + active work-items)

## In-house LLM recommendation
For private enterprise usage, run local inference (e.g., Ollama) and use:
- `prompts.llm_provider: "ollama"`
- internal endpoint such as `http://127.0.0.1:11434/v1/chat/completions`
- `prompts.llm_requires_api_key: false`

## Example secure deployment notes (commented for activation)
```yaml
# INSTRUCTION: Activate in your infra-as-code repository.
# orchestrator:
#   image: your-registry/agentic-de-cicd:latest
#   env:
#     - name: AZDO_PAT
#       valueFrom: keyvault://kv-prod/azdo-pat
#     - name: DATABRICKS_TOKEN
#       valueFrom: keyvault://kv-prod/databricks-token
#     - name: LLM_API_KEY
#       valueFrom: keyvault://kv-prod/llm-api-key
```

## Changelog
- **2026-03-16**: Added production guidance for repo automation, priority handling, prompts, MCP, and secure token strategy.
