# Production Upgrade Guide (Microsoft Stack)

## Goal
Upgrade this local-first agentic CI/CD system into an enterprise deployment for any organization using:
- Azure DevOps Boards + Repos + Pipelines
- Azure Databricks Unity Catalog workspaces per environment
- Secure hosted LLM + agent runtime on organization-controlled VM or container platform

## Target Enterprise Architecture
```text
[Azure DevOps Boards] ---> [Agent Orchestrator Service] ---> [Azure Repos PR/Code Changes]
                                     |                           |
                                     |                           v
                                     |                     [Azure Pipelines]
                                     |                           |
                                     v                           v
                              [Approval Chatbot/API] ---> [Deploy to QE/STG/PROD Databricks]
                                     |
                                     v
                            [Human-in-the-loop RFC Approval]

Cross-cutting:
- Secrets from Azure Key Vault
- Identity via Managed Identity / Service Principals
- Logs to Azure Monitor + Log Analytics
- Audit trail persisted for compliance
```

## Deployment Steps
1. **Containerize runtime**
   - Build a Docker image for this service.
   - Deploy on Azure VM Scale Set, AKS, or Container Apps.

2. **Secure identity and secrets**
   - Move PAT/token to Key Vault.
   - Replace PAT auth with OAuth/service principals where possible.
   - Apply least-privilege IAM to Azure DevOps and Databricks.

3. **Enable real integrations**
   - Set `local_mode: false` in `config/config_prod.yaml`.
   - Configure real organization/project/workspace URLs.
   - Set secure env variables in deployment runtime.

4. **HITL workflow governance**
   - Integrate approvals with enterprise chat (Teams bot).
   - Require named approvers by stage (QE lead, release manager, CAB/RFC approver).

5. **Testing and release controls**
   - Add test suites for data contracts, schema drift, DQ thresholds, and rollback logic.
   - Add gate checks in Azure Pipelines before stage promotions.

6. **Compliance and auditing**
   - Persist approvals, deployment evidence, and test artifacts for audit.
   - Add immutable storage policy for release evidence.

## Production Connector Activation Notes
The code includes commented blocks and local-first REST adapters. To harden for production:
- `src/agentic_de_pipeline/adapters/azure_devops.py`
  - Optionally switch to Azure DevOps SDK.
- `src/agentic_de_pipeline/adapters/azure_pipelines.py`
  - Add branch policy validation, artifact provenance checks, and release gates.
- `src/agentic_de_pipeline/adapters/databricks.py`
  - Optionally switch to Databricks SDK with OAuth and scoped permissions.

## Recommended Enhancements for Organization-Wide Rollout
- Multi-tenant configuration model per business unit/team.
- Pluggable policy engine for deployment approvals.
- Prompt versioning + evaluation pipelines for LLM agent behavior.
- RAG knowledge layer for prior PBIs, bug fixes, and runbooks.
- RBAC for chatbot actions and approval scopes.

## Example Production Docker Setup (Commented for Future Activation)
```dockerfile
# INSTRUCTION: Save as Dockerfile when activating production deployment.
# FROM python:3.11-slim
# WORKDIR /app
# COPY . /app
# RUN pip install --no-cache-dir -r requirements.txt
# EXPOSE 8000
# CMD ["python", "main.py", "--config", "config/config_prod.yaml", "serve-chat", "--host", "0.0.0.0", "--port", "8000"]
```

## Security Checklist
- [ ] Secrets from Key Vault only
- [ ] Managed identity / OAuth enabled
- [ ] TLS enabled for all traffic
- [ ] Approval endpoint authenticated and authorized
- [ ] Audit logs exported to SIEM
- [ ] Dependency vulnerability scans in CI

## Changelog
- **2026-03-16**: Initial production upgrade guide and architecture path added.
