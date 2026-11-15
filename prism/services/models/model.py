"""Application service for model discovery."""

from typing import Any


class ModelService:
    """Provides the models exposed by the Prism gateway."""

    DEFAULT_MODELS = ("fast", "smart", "auto")

    @staticmethod
    def list_models(loaded_config: Any = None) -> list[dict[str, Any]]:
        """Return configured models in OpenAI-compatible format.

        Args:
            loaded_config: Validated application configuration.
                Expected to expose model_pricing and gateway_config.

        Returns:
            A list containing model metadata.
        """

        if loaded_config is None:
            return [
                {
                    "id": model_name,
                    "object": "model",
                    "owned_by": "prism",
                }
                for model_name in ModelService.DEFAULT_MODELS
            ]

        models: list[dict[str, Any]] = []

        gateway_config = loaded_config.gateway_config

        for alias_name in gateway_config.aliases:
            models.append(
                {
                    "id": alias_name,
                    "object": "model",
                    "owned_by": "prism",
                    "permission": [],
                }
            )

        for model_name in loaded_config.model_pricing:
            models.append(
                {
                    "id": model_name,
                    "object": "model",
                    "owned_by": "provider",
                    "permission": [],
                }
            )

        return models
