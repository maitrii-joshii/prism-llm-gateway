"""Environment-backed settings for the Prism gateway."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    config_dir: Path

    # Gateway resilience settings
    provider_timeout_seconds: float | None = None
    max_retries: int | None = None
    connect_timeout_seconds: float = 5.0
    retry_base_delay_seconds: float = 1.0

    # Application settings
    max_tokens_cap: int = 4096

    # OpenAI provider settings
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Groq provider settings
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    @classmethod
    def from_env(cls) -> "Settings":
        """Load .env defaults and then read environment variables."""

        load_dotenv(PROJECT_ROOT / ".env", override=False)

        config_dir = Path(
            os.getenv("PRISM_CONFIG_DIR", str(PROJECT_ROOT / "config"))
        ).expanduser()

        timeout_value = os.getenv("PRISM_PROVIDER_TIMEOUT_SECONDS")
        retries_value = os.getenv("PRISM_MAX_RETRIES")
        connect_timeout_value = os.getenv(
            "PRISM_CONNECT_TIMEOUT_SECONDS", "5.0"
        )
        retry_delay_value = os.getenv(
            "PRISM_RETRY_BASE_DELAY_SECONDS", "1.0"
        )
        max_tokens_value = os.getenv("PRISM_MAX_TOKENS_CAP", "4096")

        try:
            timeout = (
                float(timeout_value) if timeout_value is not None else None
            )
            connect_timeout = float(connect_timeout_value)
            retry_base_delay = float(retry_delay_value)
        except ValueError as exc:
            raise ValueError(
                "Timeout and retry delay settings must be valid numbers."
            ) from exc

        try:
            retries = (
                int(retries_value) if retries_value is not None else None
            )
        except ValueError as exc:
            raise ValueError(
                "PRISM_MAX_RETRIES must be an integer."
            ) from exc

        try:
            max_tokens = int(max_tokens_value)
        except ValueError as exc:
            raise ValueError(
                "PRISM_MAX_TOKENS_CAP must be an integer."
            ) from exc

        if timeout is not None and timeout <= 0:
            raise ValueError(
                "PRISM_PROVIDER_TIMEOUT_SECONDS must be greater than zero."
            )

        if retries is not None and retries < 0:
            raise ValueError(
                "PRISM_MAX_RETRIES must be zero or greater."
            )

        if connect_timeout <= 0:
            raise ValueError(
                "PRISM_CONNECT_TIMEOUT_SECONDS must be greater than zero."
            )

        if retry_base_delay < 0:
            raise ValueError(
                "PRISM_RETRY_BASE_DELAY_SECONDS cannot be negative."
            )

        if max_tokens <= 0:
            raise ValueError(
                "PRISM_MAX_TOKENS_CAP must be greater than zero."
            )

        return cls(
            config_dir=config_dir,
            provider_timeout_seconds=timeout,
            max_retries=retries,
            connect_timeout_seconds=connect_timeout,
            retry_base_delay_seconds=retry_base_delay,
            max_tokens_cap=max_tokens,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv(
                "OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            groq_base_url=os.getenv(
                "GROQ_BASE_URL",
                "https://api.groq.com/openai/v1",
            ),
        )


__all__ = ["Settings"]
