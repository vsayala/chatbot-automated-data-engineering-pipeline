"""MCP connector registry for external tool endpoints."""

from __future__ import annotations

import json
import urllib.request

from agentic_de_pipeline.config import MCPConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.utils.retry import RetryPolicy, run_with_retry


class MCPRouter:
    """Tracks configured MCP servers and availability metadata."""

    def __init__(self, config: MCPConfig, log_dir: str) -> None:
        self.config = config
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.mcp_router",
            log_dir=log_dir,
            file_name="mcp_router.log",
        )

    def is_enabled(self) -> bool:
        """Return whether MCP integration is enabled."""
        return self.config.enabled

    def status_snapshot(self) -> dict[str, str]:
        """Return configured server endpoints for observability."""
        if not self.config.enabled:
            return {"mcp": "disabled"}

        snapshot = {name: endpoint for name, endpoint in self.config.servers.items()}
        self.logger.info("mcp_servers_loaded count=%s", len(snapshot))
        return snapshot

    def invoke_action(
        self,
        server_name: str,
        action: str,
        payload: dict,
        retry_policy: RetryPolicy,
    ) -> dict:
        """Invoke an MCP action on a configured server endpoint."""
        if not self.config.enabled:
            raise RuntimeError("MCP is disabled in configuration.")
        if server_name not in self.config.servers:
            raise KeyError(f"MCP server not configured: {server_name}")

        endpoint = self.config.servers[server_name].rstrip("/")
        token = self.config.server_tokens.get(server_name, "")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = json.dumps({"action": action, "payload": payload}).encode("utf-8")
        request = urllib.request.Request(
            url=endpoint,
            data=body,
            headers=headers,
            method="POST",
        )

        def _action() -> dict:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout_seconds) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))

        result = run_with_retry(
            operation_name=f"mcp_{server_name}_{action}",
            action=_action,
            policy=retry_policy,
            logger=self.logger,
        )
        self.logger.info("mcp_action_invoked server=%s action=%s", server_name, action)
        return result

    def ping_all(self, retry_policy: RetryPolicy) -> dict[str, str]:
        """Ping all configured MCP servers and report connectivity state."""
        if not self.config.enabled:
            return {"mcp": "disabled"}

        status: dict[str, str] = {}
        for server_name in self.config.servers:
            try:
                self.invoke_action(
                    server_name=server_name,
                    action="health_check",
                    payload={},
                    retry_policy=retry_policy,
                )
                status[server_name] = "reachable"
            except Exception as exc:  # pylint: disable=broad-except
                status[server_name] = f"unreachable: {exc}"
        return status
