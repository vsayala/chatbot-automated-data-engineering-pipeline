"""MCP connector registry for external tool endpoints."""

from __future__ import annotations

from agentic_de_pipeline.config import MCPConfig
from agentic_de_pipeline.logging_utils import get_module_logger


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
