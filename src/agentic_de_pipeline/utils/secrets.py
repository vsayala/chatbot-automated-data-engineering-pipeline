"""Secret retrieval helpers with config and env fallback."""

from __future__ import annotations

import os


def resolve_secret(
    direct_value: str | None,
    env_name: str,
    secret_label: str,
    required: bool = True,
) -> str:
    """Resolve secret from direct config value or environment variable.

    Args:
        direct_value: Optional direct value configured in YAML.
        env_name: Environment variable name fallback.
        secret_label: Friendly name used in error messages.
        required: Whether missing values should raise.

    Returns:
        Resolved secret value, or empty string if not required and missing.
    """
    if direct_value:
        return direct_value

    value = os.getenv(env_name, "")
    if value:
        return value

    if required:
        raise RuntimeError(
            f"Missing {secret_label}. Set '{env_name}' in environment "
            "or provide direct token value in config."
        )
    return ""
