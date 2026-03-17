"""Network endpoint classification helpers."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_internal_endpoint(
    endpoint_url: str,
    internal_hostname_suffixes: list[str],
    allow_private_ip_ranges: bool,
) -> bool:
    """Return True if endpoint is internal/private by hostname or IP.

    Args:
        endpoint_url: Full endpoint URL.
        internal_hostname_suffixes: Allowed hostname suffixes or exact hostnames.
        allow_private_ip_ranges: Whether RFC1918/loopback/link-local IPs are accepted.
    """
    parsed = urlparse(endpoint_url)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False

    for suffix in internal_hostname_suffixes:
        clean = suffix.strip().lower()
        if not clean:
            continue
        if clean.startswith(".") and hostname.endswith(clean):
            return True
        if hostname == clean:
            return True

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    if not allow_private_ip_ranges:
        return False

    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
    )
