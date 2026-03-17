"""Prompt rendering and optional hosted LLM invocation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from agentic_de_pipeline.config import PromptConfig, SecurityConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.utils.network import is_internal_endpoint
from agentic_de_pipeline.utils.retry import RetryPolicy, run_with_retry
from agentic_de_pipeline.utils.secrets import resolve_secret


class PromptEngine:
    """Loads prompt templates and optionally calls hosted LLM endpoints."""

    def __init__(
        self,
        config: PromptConfig,
        log_dir: str,
        retry_policy: RetryPolicy | None = None,
        security_config: SecurityConfig | None = None,
    ) -> None:
        self.config = config
        self.security_config = security_config
        self.retry_policy = retry_policy or RetryPolicy(attempts=2, initial_delay_seconds=0.5, max_delay_seconds=2.0)
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.prompt_engine",
            log_dir=log_dir,
            file_name="prompt_engine.log",
        )
        self.templates = self._load_templates(config.templates_path)

    @staticmethod
    def _load_templates(path: str) -> dict[str, str]:
        template_path = Path(path)
        if not template_path.exists():
            return {}
        data: dict[str, Any]
        with template_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return {str(key): str(value) for key, value in data.items()}

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template with context fallback."""
        template = self.templates.get(template_name, "")
        if not template:
            return context.get("fallback", "")
        try:
            return template.format(**context)
        except KeyError:
            self.logger.warning("prompt_template_missing_keys template=%s", template_name)
            return context.get("fallback", "")

    def generate_text(self, prompt: str) -> str:
        """Generate text from LLM endpoint if enabled; else return prompt."""
        if not self.config.llm_enabled or not self.config.llm_endpoint_url:
            return prompt

        if (
            self.security_config
            and self.security_config.strict_private_mode
            and self.security_config.enforce_internal_llm_endpoint
        ):
            if not is_internal_endpoint(
                endpoint_url=self.config.llm_endpoint_url,
                internal_hostname_suffixes=self.security_config.internal_hostname_suffixes,
                allow_private_ip_ranges=self.security_config.allow_private_ip_ranges,
            ):
                raise RuntimeError("Strict private mode blocked non-internal LLM endpoint.")

        import urllib.request

        api_key = resolve_secret(
            direct_value=self.config.llm_api_key,
            env_name=self.config.llm_api_key_env,
            secret_label="LLM API key",
            required=True,
        )

        payload = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": "You are a senior data engineering planner."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            self.config.llm_endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        def _invoke() -> dict:
            with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))

        body = run_with_retry(
            operation_name="prompt_engine_llm_call",
            action=_invoke,
            policy=self.retry_policy,
            logger=self.logger,
        )

        choices = body.get("choices", [])
        if not choices:
            return prompt
        return str(choices[0].get("message", {}).get("content", prompt)).strip()
