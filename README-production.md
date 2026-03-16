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
- Developer checks before CI/CD
- PR creation hooks for QE promotion workflows
- Stage-by-stage approvals and test controls

## Config strategy
Use `config/config_prod.yaml` and provide:
- DevOps board URL + organization/project
- Repos URL + repository
- Pipelines URL/prefix
- Databricks workspace URLs (DEV required; QE/STG/PROD optional if pipelines own promotion)
- Prompt and MCP configuration

### Why two YAML files?
- `config/config_local.yaml` is for safe local runs, mock/testing, and quick iteration.
- `config/config_prod.yaml` is for real service endpoints, stricter approvals, and hosted LLM/MCP wiring.

Keeping them separate avoids accidental production calls during development.

### Recommended workflow for your current model
If Databricks changes are done in DEV and Azure Pipelines handles promotions, keep:
- `workflow.stage_sequence: ["dev","qe","stg","prod"]`
- `workflow.databricks_apply_in_stages: ["dev"]`
- `workflow.hil_approval_stages: ["qe","stg","prod"]`

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
