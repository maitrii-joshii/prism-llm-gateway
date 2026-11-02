import pytest

from prism.domain.cost import CostCalculator
from prism.domain.models import ModelPricing


@pytest.fixture
def gpt_pricing() -> ModelPricing:
    return ModelPricing(
        model_name="gpt-4o-mini",
        input_price_per_million=0.15,
        output_price_per_million=0.60,
    )


@pytest.fixture
def llama_pricing() -> ModelPricing:
    return ModelPricing(
        model_name="llama-3.3-70b-versatile",
        input_price_per_million=0.59,
        output_price_per_million=0.79,
    )


def test_calculates_gpt_cost(gpt_pricing: ModelPricing) -> None:
    cost = CostCalculator.calculate(
        prompt_tokens=1000,
        completion_tokens=500,
        model_pricing=gpt_pricing,
    )

    assert cost == pytest.approx(0.00045)


def test_calculates_llama_cost(llama_pricing: ModelPricing) -> None:
    cost = CostCalculator.calculate(
        prompt_tokens=1000,
        completion_tokens=500,
        model_pricing=llama_pricing,
    )

    assert cost == pytest.approx(0.000985)


def test_returns_zero_for_zero_tokens(
    gpt_pricing: ModelPricing,
) -> None:
    cost = CostCalculator.calculate(
        prompt_tokens=0,
        completion_tokens=0,
        model_pricing=gpt_pricing,
    )

    assert cost == 0.0


def test_calculates_input_cost_only(
    gpt_pricing: ModelPricing,
) -> None:
    cost = CostCalculator.calculate(
        prompt_tokens=1000,
        completion_tokens=0,
        model_pricing=gpt_pricing,
    )

    assert cost == pytest.approx(0.00015)


def test_calculates_output_cost_only(
    gpt_pricing: ModelPricing,
) -> None:
    cost = CostCalculator.calculate(
        prompt_tokens=0,
        completion_tokens=1000,
        model_pricing=gpt_pricing,
    )

    assert cost == pytest.approx(0.00060)


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens"),
    [
        (-1, 0),
        (0, -1),
        (1.5, 0),
        (0, 2.5),
        (True, 0),
    ],
)
def test_rejects_invalid_token_counts(
    gpt_pricing: ModelPricing,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    with pytest.raises(ValueError):
        CostCalculator.calculate(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_pricing=gpt_pricing,
        )
