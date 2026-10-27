"""Unit tests for Prism configuration loading and validation."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from prism.config.loader import ConfigLoadError, load_configuration


CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def temporary_config():
    """Create isolated copies of the sample configuration files."""
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp)

        for filename in (
            "seed_keys.json",
            "model_pricing.json",
            "gateway_config.sample.json",
        ):
            shutil.copy(CONFIG_DIR / filename, target / filename)

        yield target


def read_json(directory, filename):
    return json.loads(
        (directory / filename).read_text(encoding="utf-8-sig")
    )


def write_json(directory, filename, data):
    (directory / filename).write_text(
        json.dumps(data), encoding="utf-8"
    )


def test_loads_all_sample_configuration(temporary_config):
    config = load_configuration(temporary_config)

    assert len(config.seed_keys) == 1
    assert len(config.model_pricing) == 2
    assert "fast" in config.gateway_config.aliases


def test_environment_variables_override_defaults(temporary_config):
    with patch.dict(
        os.environ,
        {
            "PRISM_PROVIDER_TIMEOUT_SECONDS": "45",
            "PRISM_MAX_RETRIES": "4",
        },
    ):
        config = load_configuration(temporary_config)

    assert config.gateway_config.provider_timeout_seconds == 45.0
    assert config.gateway_config.max_retries == 4


def test_missing_file_raises_clear_error(temporary_config):
    (temporary_config / "seed_keys.json").unlink()

    with pytest.raises(ConfigLoadError, match="configuration file not found"):
        load_configuration(temporary_config)


def test_alias_to_unknown_model_is_rejected(temporary_config):
    data = read_json(temporary_config, "gateway_config.sample.json")
    data["aliases"]["fast"]["primary_model"] = "missing-model"
    write_json(temporary_config, "gateway_config.sample.json", data)

    with pytest.raises(
        ConfigLoadError, match="missing from model_pricing.json"
    ):
        load_configuration(temporary_config)


def test_zero_budget_is_rejected(temporary_config):
    data = read_json(temporary_config, "seed_keys.json")
    data[0]["budget_usd"] = 0
    write_json(temporary_config, "seed_keys.json", data)

    with pytest.raises(
        ConfigLoadError, match="budget_usd must be a positive number"
    ):
        load_configuration(temporary_config)


def test_zero_rate_limit_is_rejected(temporary_config):
    data = read_json(temporary_config, "seed_keys.json")
    data[0]["rate_limit_rpm"] = 0
    write_json(temporary_config, "seed_keys.json", data)

    with pytest.raises(
        ConfigLoadError, match="rate_limit_rpm must be a positive integer"
    ):
        load_configuration(temporary_config)


def test_non_integer_rate_limit_is_rejected(temporary_config):
    data = read_json(temporary_config, "seed_keys.json")
    data[0]["rate_limit_rpm"] = 1.5
    write_json(temporary_config, "seed_keys.json", data)

    with pytest.raises(
        ConfigLoadError, match="rate_limit_rpm must be a positive integer"
    ):
        load_configuration(temporary_config)
