"""Load and validate Prism gateway configuration files."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prism.domain.security import hash_api_key
from prism.config.settings import Settings
from prism.domain.models import (
    AliasConfig,
    GatewayConfig,
    ModelPricing,
    ProviderConfig,
    VirtualKeyConfig,
)


class ConfigLoadError(RuntimeError):
    """Raised when gateway configuration cannot be loaded safely."""


@dataclass(frozen=True)
class LoadedConfig:
    """All validated configuration needed to start the gateway."""

    seed_keys: list[VirtualKeyConfig]
    model_pricing: dict[str, ModelPricing]
    gateway_config: GatewayConfig


def _read_json(path: Path) -> Any:
    """Read JSON and provide a clear error if it cannot be loaded."""

    if not path.is_file():
        raise ConfigLoadError(
            f"Required configuration file not found: {path}. "
            "Create the file or set PRISM_CONFIG_DIR to the correct folder."
        )

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            f"Invalid JSON in {path}, line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ConfigLoadError(
            f"Could not read configuration file {path}: {exc}"
        ) from exc


def _normalize_seed_keys(data: Any) -> Any:
    """Convert the Airtribe starter ``seed_keys.json`` shape to Prism's.

    The starter file is ``{"tenants": [{"team", "virtual_key", ...}]}``.
    Prism's internal (legacy) shape is a flat list; lists pass through.
    """

    if not (isinstance(data, dict) and "tenants" in data):
        return data

    tenants = data["tenants"]
    if not isinstance(tenants, list):
        raise ConfigLoadError("seed_keys.json: 'tenants' must be a list.")

    normalized: list[Any] = []

    for tenant in tenants:
        if not isinstance(tenant, dict):
            normalized.append(tenant)  # validator reports the error
            continue

        cache = tenant.get("semantic_cache") or {}
        rate = tenant.get("rate_limit") or {}

        normalized.append(
            {
                "key": tenant.get("virtual_key"),
                "tenant_id": tenant.get("team"),
                "budget_usd": tenant.get("monthly_budget_usd"),
                # tokens_per_minute is accepted in the file but not enforced.
                "rate_limit_rpm": rate.get("requests_per_minute"),
                "model_allowlist": tenant.get("model_allowlist"),
                "cache_enabled": bool(cache.get("enabled", False)),
                "cache_threshold": cache.get("similarity_threshold", 0.85),
                "status": tenant.get("status", "active"),
            }
        )

    return normalized


def _validate_seed_keys(data: Any) -> list[VirtualKeyConfig]:
    """Validate tenant keys and convert raw keys into SHA-256 hashes."""

    data = _normalize_seed_keys(data)

    if not isinstance(data, list):
        raise ConfigLoadError(
            "seed_keys.json must contain a JSON array of virtual keys."
        )

    keys: list[VirtualKeyConfig] = []

    for index, item in enumerate(data):
        label = f"seed_keys.json entry {index}"

        if not isinstance(item, dict):
            raise ConfigLoadError(f"{label} must be a JSON object.")

        raw_key = item.get("key")

        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ConfigLoadError(
                f"{label}: key must be a non-empty string."
            )

        budget = item.get("budget_usd")
        if (
            isinstance(budget, bool)
            or not isinstance(budget, (int, float))
            or budget <= 0
        ):
            raise ConfigLoadError(
                f"{label}: budget_usd must be a positive number."
            )

        rate = item.get("rate_limit_rpm")
        if (
            isinstance(rate, bool)
            or not isinstance(rate, int)
            or rate <= 0
        ):
            raise ConfigLoadError(
                f"{label}: rate_limit_rpm must be a positive integer."
            )

        key_data = {
            **item,
            "key_hash": hash_api_key(raw_key),
        }
        key_data.pop("key", None)

        try:
            keys.append(VirtualKeyConfig.model_validate(key_data))
        except ValidationError as exc:
            raise ConfigLoadError(f"Invalid {label}: {exc}") from exc

    return keys


def _normalize_pricing(data: Any) -> Any:
    """Convert the starter ``model_pricing.json`` shape to Prism's.

    Starter: ``{"_comment": ..., "alpha-small": {"input_per_1m": .., "output_per_1m": ..}}``.
    """

    if not isinstance(data, dict):
        return data

    is_starter_shape = any(
        isinstance(value, dict) and "input_per_1m" in value
        for value in data.values()
    )

    if not is_starter_shape:
        return data

    entries: list[dict[str, Any]] = []

    for name, value in data.items():
        if name.startswith("_") or not isinstance(value, dict):
            continue  # skip "_comment" style metadata

        entries.append(
            {
                "model_name": name,
                "input_price_per_million": value.get("input_per_1m"),
                "output_price_per_million": value.get("output_per_1m"),
            }
        )

    return entries


def _validate_pricing(data: Any) -> dict[str, ModelPricing]:
    """Convert pricing JSON into a dictionary indexed by model name."""

    data = _normalize_pricing(data)

    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = list(data.values())
    else:
        raise ConfigLoadError(
            "model_pricing.json must contain a JSON array or object."
        )

    pricing: dict[str, ModelPricing] = {}

    for index, item in enumerate(entries):
        try:
            model = ModelPricing.model_validate(item)
        except ValidationError as exc:
            raise ConfigLoadError(
                f"Invalid model_pricing.json entry {index}: {exc}"
            ) from exc

        if model.model_name in pricing:
            raise ConfigLoadError(
                f"Duplicate pricing entry for model '{model.model_name}'."
            )

        pricing[model.model_name] = model

    if not pricing:
        raise ConfigLoadError(
            "model_pricing.json must define at least one model."
        )

    return pricing


def provider_for_model(
    model_name: str,
    providers: list[ProviderConfig],
) -> ProviderConfig | None:
    """Return the provider serving ``model_name``.

    Convention (matches the starter mock providers): provider ``alpha``
    serves models named ``alpha-*``. The longest matching name wins.
    """

    matches = [
        provider
        for provider in providers
        if model_name.startswith(f"{provider.name}-")
    ]

    if not matches:
        return None

    return max(matches, key=lambda provider: len(provider.name))


def _normalize_gateway(data: Any) -> Any:
    """Convert the starter ``gateway_config.sample.json`` shape to Prism's.

    Starter keys: ``providers``, ``model_aliases`` (with ``primary`` /
    ``fallbacks`` and an ``auto`` entry using ``route_by_difficulty``),
    and ``retry``. Prism's legacy shape (``aliases``) passes through.
    """

    if not (isinstance(data, dict) and "model_aliases" in data):
        return data

    aliases: dict[str, Any] = {}
    auto_routes: dict[str, str] = {}

    model_aliases = data["model_aliases"]
    if not isinstance(model_aliases, dict):
        raise ConfigLoadError(
            "gateway_config: model_aliases must be a JSON object."
        )

    for name, value in model_aliases.items():
        if name.startswith("_") or not isinstance(value, dict):
            continue

        if "route_by_difficulty" in value:
            routes = value["route_by_difficulty"]
            auto_routes = {
                "fast": routes.get("simple", "fast"),
                "smart": routes.get("complex", "smart"),
            }
            continue

        aliases[name] = {
            "alias_name": name,
            "primary_model": value.get("primary"),
            "fallback_chain": value.get("fallbacks", []),
        }

    normalized: dict[str, Any] = {
        "aliases": aliases,
        "auto_routes": auto_routes,
        "providers": data.get("providers", []),
    }

    retry = data.get("retry")
    if isinstance(retry, dict):
        attempts = retry.get("max_attempts")
        if isinstance(attempts, int) and attempts >= 1:
            normalized["max_retries"] = attempts - 1

        backoff_ms = retry.get("initial_backoff_ms")
        if isinstance(backoff_ms, (int, float)) and backoff_ms >= 0:
            normalized["retry_base_delay_seconds"] = backoff_ms / 1000.0

    return normalized


def _build_providers(raw_providers: Any) -> list[ProviderConfig]:
    """Build the provider registry, allowing env overrides.

    ``PRISM_PROVIDER_<NAME>_BASE_URL`` and ``PRISM_PROVIDER_<NAME>_API_KEY``
    override the file values so secrets and container hostnames stay out
    of the committed JSON.
    """

    if not isinstance(raw_providers, list):
        raise ConfigLoadError("gateway_config: providers must be a list.")

    providers: list[ProviderConfig] = []

    for index, item in enumerate(raw_providers):
        if not isinstance(item, dict):
            raise ConfigLoadError(
                f"gateway_config provider {index} must be a JSON object."
            )

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigLoadError(
                f"gateway_config provider {index}: name is required."
            )

        env_prefix = f"PRISM_PROVIDER_{name.upper().replace('-', '_')}"

        base_url = os.getenv(f"{env_prefix}_BASE_URL") or item.get("base_url")
        api_key = os.getenv(f"{env_prefix}_API_KEY") or item.get("api_key")

        try:
            providers.append(
                ProviderConfig(name=name, base_url=base_url, api_key=api_key)
            )
        except ValidationError as exc:
            raise ConfigLoadError(
                f"Invalid provider '{name}': {exc}"
            ) from exc

    return providers


def _validate_gateway(
    data: Any,
    pricing: dict[str, ModelPricing],
    settings: Settings,
) -> GatewayConfig:
    """Validate aliases and gateway-wide settings."""

    data = _normalize_gateway(data)

    if not isinstance(data, dict):
        raise ConfigLoadError(
            "gateway_config.json must contain a JSON object."
        )

    aliases_data = data.get("aliases", {})
    if not isinstance(aliases_data, dict):
        raise ConfigLoadError(
            "gateway_config.json: aliases must be a JSON object."
        )

    aliases: dict[str, AliasConfig] = {}

    for alias_key, alias_data in aliases_data.items():
        try:
            alias = AliasConfig.model_validate(alias_data)
        except ValidationError as exc:
            raise ConfigLoadError(
                f"Invalid alias '{alias_key}': {exc}"
            ) from exc

        if alias_key != alias.alias_name:
            raise ConfigLoadError(
                f"Alias key '{alias_key}' does not match "
                f"alias_name '{alias.alias_name}'."
            )

        for model_name in [alias.primary_model, *alias.fallback_chain]:
            if model_name not in pricing:
                raise ConfigLoadError(
                    f"Alias '{alias.alias_name}' references model "
                    f"'{model_name}', which is missing from "
                    "model_pricing.json."
                )

        aliases[alias_key] = alias

    providers = _build_providers(data.get("providers", []))

    if providers:
        for alias in aliases.values():
            for model_name in [alias.primary_model, *alias.fallback_chain]:
                if provider_for_model(model_name, providers) is None:
                    raise ConfigLoadError(
                        f"Alias '{alias.alias_name}' uses model "
                        f"'{model_name}', but no provider in the registry "
                        f"serves it (expected a provider named "
                        f"'<provider>-...')."
                    )

    auto_routes = data.get("auto_routes", {})
    for tier, alias_name in auto_routes.items():
        if alias_name not in aliases:
            raise ConfigLoadError(
                f"auto route '{tier}' points to unknown alias "
                f"'{alias_name}'."
            )

    config_data: dict[str, Any] = {
        "aliases": aliases,
        "model_pricing": pricing,
        "provider_timeout_seconds": data.get(
            "provider_timeout_seconds", 30.0
        ),
        "max_retries": data.get("max_retries", 2),
        "providers": providers,
        "auto_routes": auto_routes,
        "retry_base_delay_seconds": data.get("retry_base_delay_seconds"),
    }

    if settings.provider_timeout_seconds is not None:
        config_data["provider_timeout_seconds"] = (
            settings.provider_timeout_seconds
        )

    if settings.max_retries is not None:
        config_data["max_retries"] = settings.max_retries

    try:
        return GatewayConfig.model_validate(config_data)
    except ValidationError as exc:
        raise ConfigLoadError(
            f"Invalid gateway configuration: {exc}"
        ) from exc


def load_configuration(
    config_dir: str | Path | None = None,
) -> LoadedConfig:
    """Load and validate all three configuration files."""

    settings = Settings.from_env()
    directory = (
        Path(config_dir) if config_dir is not None else settings.config_dir
    )

    seed_data = _read_json(directory / "seed_keys.json")
    pricing_data = _read_json(directory / "model_pricing.json")

    # Prefer gateway_config.json; fall back to gateway_config.sample.json
    # so that existing deployments using the legacy filename keep working.
    gateway_config_path = directory / "gateway_config.json"
    if not gateway_config_path.is_file():
        gateway_config_path = directory / "gateway_config.sample.json"
    gateway_data = _read_json(gateway_config_path)

    seed_keys = _validate_seed_keys(seed_data)
    pricing = _validate_pricing(pricing_data)

    # Validate the gateway config first so we can include alias names in the
    # set of valid allowlist identifiers below.
    gateway_config = _validate_gateway(gateway_data, pricing, settings)

    # Every entry in a key's model_allowlist must be a known pricing model
    # name OR a gateway alias name (e.g. "fast", "smart") OR the wildcard "*".
    # This lets operators write alias-based allowlists without enumerating
    # every underlying model name.
    valid_identifiers = (
        set(pricing.keys())
        | set(gateway_config.aliases.keys())
        | {"*", "auto"}
    )

    for key in seed_keys:
        for model_name in key.model_allowlist:
            if model_name not in valid_identifiers:
                raise ConfigLoadError(
                    f"Tenant '{key.tenant_id}' allows model/alias "
                    f"'{model_name}', which is not a known model or alias. "
                    "Check model_pricing.json and gateway_config.json."
                )

    return LoadedConfig(
        seed_keys=seed_keys,
        model_pricing=pricing,
        gateway_config=gateway_config,
    )


def load_seed_keys(
    config_dir: str | Path | None = None,
) -> list[VirtualKeyConfig]:
    """Load all configuration and return the validated virtual keys."""

    return load_configuration(config_dir).seed_keys


def load_model_pricing(
    config_dir: str | Path | None = None,
) -> dict[str, ModelPricing]:
    """Load all configuration and return model pricing."""

    return load_configuration(config_dir).model_pricing


def load_gateway_config(
    config_dir: str | Path | None = None,
) -> GatewayConfig:
    """Load all configuration and return gateway settings."""

    return load_configuration(config_dir).gateway_config


__all__ = [
    "ConfigLoadError",
    "LoadedConfig",
    "load_configuration",
    "load_seed_keys",
    "load_model_pricing",
    "load_gateway_config",
    "provider_for_model",
]
