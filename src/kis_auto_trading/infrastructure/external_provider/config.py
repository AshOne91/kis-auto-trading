from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

EXTERNAL_PROVIDER_URL_ENV: Final = "KIS_API_URL"
DEFAULT_HEALTH_PATH: Final = "/"
DEFAULT_TIMEOUT_SECONDS: Final = 5.0
DEFAULT_MAX_RETRIES: Final = 2
DEFAULT_RETRY_DELAY_SECONDS: Final = 0.1


@dataclass(frozen=True, slots=True)
class ExternalProviderConfig:
    base_url: str
    health_path: str = DEFAULT_HEALTH_PATH
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS

    @classmethod
    def from_environment(cls) -> ExternalProviderConfig:
        base_url = os.environ.get(EXTERNAL_PROVIDER_URL_ENV)
        if not base_url:
            raise RuntimeError(f'{EXTERNAL_PROVIDER_URL_ENV} must be set')
        return cls(base_url=base_url.rstrip('/'))
