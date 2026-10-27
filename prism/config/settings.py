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
    provider_timeout_seconds: float | None = None
    max_retries: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        """Load .env defaults and then read environment variables."""

        load_dotenv(PROJECT_ROOT / ".env", override=False)

        config_dir = Path(
            os.getenv("PRISM_CONFIG_DIR", str(PROJECT_ROOT / "config"))
        ).expanduser()

        timeout_value = os.getenv("PRISM_PROVIDER_TIMEOUT_SECONDS")
        retries_value = os.getenv("PRISM_MAX_RETRIES")

        try:
            timeout = (
                float(timeout_value) if timeout_value is not None else None
            )
        except ValueError as exc:
            raise ValueError(
                "PRISM_PROVIDER_TIMEOUT_SECONDS must be a number."
            ) from exc

        try:
            retries = (
                int(retries_value) if retries_value is not None else None
            )
        except ValueError as exc:
            raise ValueError(
                "PRISM_MAX_RETRIES must be an integer."
            ) from exc

        if timeout is not None and timeout <= 0:
            raise ValueError(
                "PRISM_PROVIDER_TIMEOUT_SECONDS must be greater than zero."
            )

        if retries is not None and retries < 0:
            raise ValueError(
                "PRISM_MAX_RETRIES must be zero or greater."
            )

        return cls(
            config_dir=config_dir,
            provider_timeout_seconds=timeout,
            max_retries=retries,
        )


__all__ = ["Settings"]
