"""Load and validate Prism gateway configuration files."""

import json
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


def _validate_seed_keys(data: Any) -> list[VirtualKeyConfig]:
    """Validate tenant keys and convert raw keys into SHA-256 hashes."""

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


def _validate_pricing(data: Any) -> dict[str, ModelPricing]:
    """Convert pricing JSON into a dictionary indexed by model name."""

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


def _validate_gateway(
    data: Any,
    pricing: dict[str, ModelPricing],
    settings: Settings,
) -> GatewayConfig:
    """Validate aliases and gateway-wide settings."""

    if not isinstance(data, dict):
        raise ConfigLoadError(
            "gateway_config.sample.json must contain a JSON object."
        )

    aliases_data = data.get("aliases", {})
    if not isinstance(aliases_data, dict):
        raise ConfigLoadError(
            "gateway_config.sample.json: aliases must be a JSON object."
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

    config_data: dict[str, Any] = {
        "aliases": aliases,
        "model_pricing": pricing,
        "provider_timeout_seconds": data.get(
            "provider_timeout_seconds", 30.0
        ),
        "max_retries": data.get("max_retries", 2),
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
    gateway_data = _read_json(directory / "gateway_config.sample.json")

    seed_keys = _validate_seed_keys(seed_data)
    pricing = _validate_pricing(pricing_data)

    for key in seed_keys:
        for model_name in key.model_allowlist:
            if model_name not in pricing:
                raise ConfigLoadError(
                    f"Tenant '{key.tenant_id}' allows model "
                    f"'{model_name}', which is missing from "
                    "model_pricing.json."
                )

    gateway_config = _validate_gateway(gateway_data, pricing, settings)

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
]
