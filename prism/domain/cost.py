"""Pure domain logic for calculating LLM request costs."""

from prism.domain.models import ModelPricing


class CostCalculator:
    """Calculate request costs using provider-reported token usage."""

    @staticmethod
    def calculate(
        prompt_tokens: int,
        completion_tokens: int,
        model_pricing: ModelPricing,
    ) -> float:
        """Calculate cost in USD using per-million-token pricing."""

        if (
            isinstance(prompt_tokens, bool)
            or not isinstance(prompt_tokens, int)
            or prompt_tokens < 0
        ):
            raise ValueError("prompt_tokens must be a non-negative integer.")

        if (
            isinstance(completion_tokens, bool)
            or not isinstance(completion_tokens, int)
            or completion_tokens < 0
        ):
            raise ValueError(
                "completion_tokens must be a non-negative integer."
            )

        input_cost = (
            prompt_tokens * model_pricing.input_price_per_million
        )
        output_cost = (
            completion_tokens * model_pricing.output_price_per_million
        )

        return (input_cost + output_cost) / 1_000_000
