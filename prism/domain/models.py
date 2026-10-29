"""Core domain models used throughout the Prism LLM Gateway."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RequestContext(BaseModel):
    """Carries request data and decisions through the gateway pipeline."""

    request_id: str
    key_config: VirtualKeyConfig
    model_requested: str
    model_resolved: str | None = None
    provider_name: str | None = None
    messages: list[dict[str, Any]]
    stream: bool
    decision_trace: list[str] = Field(default_factory=list)
    start_time: datetime

    # Response metadata used to populate Prism response headers.
    cache_status: str = "miss"
    fallback_used: bool = False
    cost_usd: float = Field(default=0.0, ge=0)


class ProviderResponse(BaseModel):
    """Normalized response returned by an LLM provider."""

    content: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    finish_reason: str | None = None
    raw_response: dict[str, Any]


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


__all__ = [
    "VirtualKeyConfig",
    "RequestContext",
    "ProviderResponse",
    "ModelPricing",
    "GatewayConfig",
    "AliasConfig",
    "UsageRecord",
]
