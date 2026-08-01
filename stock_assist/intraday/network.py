"""Explicit provider-scoped network routing without exposing proxy details."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Literal
from urllib.request import OpenerDirector, ProxyHandler, build_opener


NetworkRegion = Literal["domestic", "foreign", "local", "unknown"]
ProxyPolicy = Literal["direct", "system_proxy", "local_only", "automatic"]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: float = 0.0


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int
    scope: str = "endpoint_refresh"


@dataclass(frozen=True)
class ProviderNetworkPolicy:
    provider_id: str
    network_region: NetworkRegion
    proxy_policy: ProxyPolicy
    timeout_seconds: float
    retry_policy: RetryPolicy
    circuit_breaker_policy: CircuitBreakerPolicy
    transport: str = "https"
    route_scope: str = "application_client"
    os_tun_bypass_guaranteed: bool = False

    @property
    def display_route(self) -> str:
        return {
            "direct": "国内直连",
            "system_proxy": "国外系统代理",
            "local_only": "本地服务",
        }.get(self.proxy_policy, "自动/未知")

    def safe_diagnostic(self) -> dict[str, object]:
        """Return route facts that cannot disclose the configured proxy endpoint."""

        payload = asdict(self)
        payload["display_route"] = self.display_route
        return payload


_DOMESTIC = {
    "eastmoney",
    "eastmoney_push2",
    "eastmoney_push2his",
    "tencent",
    "cninfo",
    "iwencai",
}
_LOCAL = {"localhost", "127.0.0.1", "futu_opend"}
_FOREIGN = {"yahoo", "global_markets"}


def provider_policy(provider_id: str) -> ProviderNetworkPolicy:
    """Return the declared route for a known provider; unknown stays explicit."""

    normalized = str(provider_id).strip().lower()
    if normalized == "galaxy_amazingdata":
        return ProviderNetworkPolicy(
            provider_id=normalized,
            network_region="domestic",
            proxy_policy="direct",
            timeout_seconds=12.0,
            retry_policy=RetryPolicy(max_attempts=1),
            circuit_breaker_policy=CircuitBreakerPolicy(failure_threshold=3),
            transport="raw_tcp",
        )
    if normalized in _DOMESTIC:
        return ProviderNetworkPolicy(
            provider_id=normalized,
            network_region="domestic",
            proxy_policy="direct",
            timeout_seconds=3.0 if normalized.startswith("eastmoney") else 8.0,
            retry_policy=RetryPolicy(max_attempts=1),
            circuit_breaker_policy=CircuitBreakerPolicy(failure_threshold=3),
        )
    if normalized in _LOCAL:
        return ProviderNetworkPolicy(
            provider_id=normalized,
            network_region="local",
            proxy_policy="local_only",
            timeout_seconds=2.0,
            retry_policy=RetryPolicy(max_attempts=1),
            circuit_breaker_policy=CircuitBreakerPolicy(failure_threshold=2),
            transport="local_tcp",
        )
    if normalized in _FOREIGN:
        return ProviderNetworkPolicy(
            provider_id=normalized,
            network_region="foreign",
            proxy_policy="system_proxy",
            timeout_seconds=15.0,
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.5),
            circuit_breaker_policy=CircuitBreakerPolicy(failure_threshold=3),
        )
    return ProviderNetworkPolicy(
        provider_id=normalized or "unknown",
        network_region="unknown",
        proxy_policy="automatic",
        timeout_seconds=10.0,
        retry_policy=RetryPolicy(max_attempts=1),
        circuit_breaker_policy=CircuitBreakerPolicy(failure_threshold=3),
    )


def build_urllib_opener(policy: ProviderNetworkPolicy) -> OpenerDirector:
    """Create a provider-owned urllib opener without mutating process env."""

    if policy.proxy_policy in {"direct", "local_only"}:
        opener = build_opener(ProxyHandler({}))
    else:
        opener = build_opener(ProxyHandler())
    opener.insightradar_proxy_policy = policy.proxy_policy
    return opener


def build_requests_session(policy: ProviderNetworkPolicy):
    """Create a provider-owned requests Session with explicit env inheritance."""

    import requests

    session = requests.Session()
    session.trust_env = policy.proxy_policy in {"system_proxy", "automatic"}
    return session


def declared_provider_routes() -> list[dict[str, object]]:
    """Expose the finite runtime route registry without proxy values."""

    provider_ids = (
        "galaxy_amazingdata",
        "eastmoney_push2",
        "eastmoney_push2his",
        "tencent",
        "cninfo",
        "iwencai",
        "yahoo",
        "localhost",
        "futu_opend",
    )
    return [provider_policy(provider).safe_diagnostic() for provider in provider_ids]


_PROXY_ASSIGNMENT = re.compile(
    r"(?i)\b(?:https?_proxy|all_proxy|no_proxy)\s*=\s*\S+"
)
_URL = re.compile(r"(?i)\b(?:https?|socks5?)://[^\s'\"]+")
_PROXY_KEY_VALUE = re.compile(
    r"(?i)\b(host|hostname|port|proxy|user|username|password|passwd)"
    r"\s*(?:=|:)\s*(?:'[^']*'|\"[^\"]*\"|[^,\s)]+)"
)
_PROXY_MAPPING_VALUE = re.compile(
    r"(?i)(?P<quote>['\"])(?P<key>hostname|host|port|proxy|username|user|password|passwd)"
    r"(?P=quote)\s*:\s*(?:'[^']*'|\"[^\"]*\"|[^,\s)}]+)"
)
_PROXY_CREDENTIAL_SPACE_VALUE = re.compile(
    r"(?i)\b(username|user|password|passwd)"
    r"\s+(?:'[^']*'|\"[^\"]*\"|[^,\s)]+)"
)
_PROXY_KEY_SPACE_VALUE = re.compile(
    r"(?i)\b(hostname|host|port|proxy)"
    r"\s+(?:'[^']*'|\"[^\"]*\"|[^,\s)]+)"
)
_PROXY_AUTHORITY = re.compile(
    r"(?i)(?<![\w])[^\s:/@]+:[^\s/@]+@(?=[^\s]+)"
)
_HOST_PORT = re.compile(
    r"(?i)\b(?:(?:[a-z0-9-]+\.)+[a-z]{2,}|(?:\d{1,3}\.){3}\d{1,3})"
    r"(?::\d{2,5})?\b"
)


def sanitize_diagnostic_text(value: object) -> str:
    """Remove proxy endpoints and credentials from diagnostics, API, and UI text."""

    text = str(value or "")
    text = _PROXY_ASSIGNMENT.sub("[redacted_proxy]", text)
    text = _URL.sub("[redacted_proxy]", text)
    text = _PROXY_AUTHORITY.sub("[redacted_proxy]@", text)
    text = _PROXY_MAPPING_VALUE.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}: "
            "[redacted_proxy]"
        ),
        text,
    )
    text = _PROXY_KEY_VALUE.sub(
        lambda match: f"{match.group(1)}=[redacted_proxy]",
        text,
    )
    text = _PROXY_CREDENTIAL_SPACE_VALUE.sub(
        lambda match: f"{match.group(1)} [redacted_proxy]",
        text,
    )
    text = _PROXY_KEY_SPACE_VALUE.sub(
        lambda match: f"{match.group(1)} [redacted_proxy]",
        text,
    )
    text = _HOST_PORT.sub("[redacted_proxy]", text)
    return text


def sanitized_error_type(exc: BaseException) -> str:
    """Expose only a stable exception class, never its endpoint-bearing message."""

    return type(exc).__name__
