"""Core domain models used throughout the Prism LLM Gateway."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class VirtualKeyConfig(BaseModel):
    """Configuration and permissions associated with a tenant's virtual key."""

    key_hash: str
    tenant_id: str
    budget_usd: float = Field(ge=0)
    rate_limit_rpm: int = Field(gt=0)
    model_allowlist: list[str]
    cache_enabled: bool
    cache_threshold: float = Field(ge=0, le=1)
    status: str


class ProviderResponse(BaseModel):
    """Normalized response returned by a provider."""

    content: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    finish_reason: str | None = None
    raw_response: dict[str, Any]


class RequestContext(BaseModel):
    """Carries request data and decisions through the gateway pipeline."""

    request_id: str
    key_config: VirtualKeyConfig | None = None

    model_requested: str = ""
    model_resolved: str | None = None
    provider_name: str | None = None

    model_candidates: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)

    messages: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False

    request_payload: dict[str, Any] = Field(default_factory=dict)
    provider_response: ProviderResponse | None = None

    stream_prompt_tokens: int = Field(default=0, ge=0)
    stream_completion_tokens: int = Field(default=0, ge=0)

    decision_trace: list[str] = Field(default_factory=list)
    start_time: datetime

    cache_status: str = "miss"
    fallback_used: bool = False
    cost_usd: float = Field(default=0.0, ge=0)


class LogEntry(BaseModel):
    """Request-level metadata stored in the request_logs table."""

    request_id: str
    key_hash: str | None = None

    model_requested: str = ""
    model_resolved: str | None = None
    provider: str | None = None

    status_code: int

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)

    cache_result: str | None = None
    fallback_used: bool = False
    retries: int = Field(default=0, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)

    decision_trace: list[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CacheEntry(BaseModel):
    """A semantic cache entry belonging to one virtual API key."""

    id: int | None = None
    key_hash: str
    alias: str
    embedding: list[float]
    response_body: dict[str, Any]
    hit_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CacheStats(BaseModel):
    """Aggregated semantic cache statistics."""

    total_entries: int = Field(default=0, ge=0)
    total_hits: int = Field(default=0, ge=0)


class ModelPricing(BaseModel):
    """Pricing for a model, expressed per million tokens."""

    model_name: str
    input_price_per_million: float = Field(ge=0)
    output_price_per_million: float = Field(ge=0)


class AliasConfig(BaseModel):
    """Maps a friendly model alias to a primary model and fallback chain."""

    alias_name: str
    primary_model: str
    fallback_chain: list[str] = Field(default_factory=list)


class GatewayConfig(BaseModel):
    """Initial gateway-wide runtime configuration."""

    aliases: dict[str, AliasConfig] = Field(default_factory=dict)
    model_pricing: dict[str, ModelPricing] = Field(default_factory=dict)
    provider_timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0)


class UsageRecord(BaseModel):
    """Token usage and cost recorded for a gateway request."""

    request_id: str
    tenant_id: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    created_at: datetime


class MonthlyUsage(BaseModel):
    """Aggregated usage for one virtual key in one calendar month."""

    key_hash: str
    month: str
    total_spend_usd: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_requests: int = Field(ge=0)
    cache_hits: int = Field(ge=0)


__all__ = [
    "VirtualKeyConfig",
    "RequestContext",
    "ProviderResponse",
    "ModelPricing",
    "GatewayConfig",
    "AliasConfig",
    "UsageRecord",
    "MonthlyUsage",
    "LogEntry",
    "CacheEntry",
    "CacheStats",
]
