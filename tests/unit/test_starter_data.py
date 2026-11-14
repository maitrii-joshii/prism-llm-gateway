"""The gateway must load the unmodified Airtribe starter data files."""

from pathlib import Path

from prism.config.loader import load_configuration, provider_for_model

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_loads_official_starter_data_unchanged():
    config = load_configuration(DATA_DIR)

    # Four seed tenants, with the exact starter key values.
    assert {k.tenant_id for k in config.seed_keys} == {
        "search",
        "research",
        "free-tier",
        "budget-demo",
    }

    free = next(k for k in config.seed_keys if k.tenant_id == "free-tier")
    assert free.rate_limit_rpm == 10
    assert free.budget_usd == 5
    assert free.cache_enabled is True
    assert free.cache_threshold == 0.85

    search = next(k for k in config.seed_keys if k.tenant_id == "search")
    assert search.model_allowlist == ["fast"]
    assert search.cache_threshold == 0.92

    research = next(k for k in config.seed_keys if k.tenant_id == "research")
    assert research.cache_enabled is False
    assert "auto" in research.model_allowlist

    budget = next(k for k in config.seed_keys if k.tenant_id == "budget-demo")
    assert budget.budget_usd == 0.00001

    # Price table.
    assert set(config.model_pricing) == {
        "alpha-small",
        "alpha-large",
        "beta-small",
        "beta-large",
    }
    assert config.model_pricing["alpha-small"].input_price_per_million == 0.15
    assert config.model_pricing["beta-large"].output_price_per_million == 10.00


def test_official_gateway_config_aliases_providers_and_retry():
    gateway = load_configuration(DATA_DIR).gateway_config

    assert gateway.aliases["fast"].primary_model == "alpha-small"
    assert gateway.aliases["fast"].fallback_chain == ["beta-small"]
    assert gateway.aliases["smart"].primary_model == "alpha-large"
    assert gateway.aliases["smart"].fallback_chain == ["beta-large"]

    # `auto` is a router, not a model alias.
    assert "auto" not in gateway.aliases
    assert gateway.auto_routes == {"fast": "fast", "smart": "smart"}

    assert [p.name for p in gateway.providers] == ["alpha", "beta"]

    # max_attempts=3 -> 2 retries; initial_backoff_ms=200 -> 0.2s.
    assert gateway.max_retries == 2
    assert gateway.retry_base_delay_seconds == 0.2


def test_provider_for_model_uses_name_prefix():
    gateway = load_configuration(DATA_DIR).gateway_config

    assert provider_for_model("alpha-small", gateway.providers).name == "alpha"
    assert provider_for_model("beta-large", gateway.providers).name == "beta"
    assert provider_for_model("gpt-4o-mini", gateway.providers) is None

