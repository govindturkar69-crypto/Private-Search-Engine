"""Runtime-only configuration manager with strict allowlist validation."""

import logging
from typing import Any, Dict
from src.api.admin_models import ConfigUpdateRequest, RuntimeConfigResponse
from src.config import Config

logger = logging.getLogger(__name__)

ALLOWED_SETTINGS = {
    "log_level",
    "rate_limit_per_minute",
    "crawler_max_depth",
    "crawler_politeness_delay",
}


class ConfigService:
    """Manages strictly allowlisted in-memory configuration updates at runtime."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._runtime_overrides: Dict[str, Any] = {
            "log_level": config.server.log_level,
            "rate_limit_per_minute": config.server.rate_limit_per_minute,
            "crawler_max_depth": config.crawl.max_depth,
            "crawler_politeness_delay": config.crawl.crawl_delay,
        }

    def get_runtime_config(self) -> RuntimeConfigResponse:
        """Return the current allowlisted runtime settings."""
        return RuntimeConfigResponse(
            settings=dict(self._runtime_overrides),
            notice="Runtime-only settings. Changes reset when the server restarts.",
        )

    def update_setting(self, update: ConfigUpdateRequest) -> RuntimeConfigResponse:
        """Validate and apply an in-memory runtime configuration change."""
        key = update.key
        val = update.value

        if key not in ALLOWED_SETTINGS:
            raise ValueError(
                f"Configuration key '{key}' cannot be modified at runtime. "
                f"Allowed keys: {sorted(list(ALLOWED_SETTINGS))}"
            )

        if key == "log_level":
            val_str = str(val).upper()
            if val_str not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                raise ValueError(
                    f"Invalid log_level '{val}'. Must be one of "
                    "DEBUG, INFO, WARNING, ERROR, CRITICAL"
                )
            self._runtime_overrides[key] = val_str
            self.config.server.log_level = val_str
            # Apply dynamically to loggers
            logging.getLogger().setLevel(val_str)
            for name in logging.root.manager.loggerDict:
                logging.getLogger(name).setLevel(val_str)
            logger.info(f"Runtime log level updated to {val_str}")

        elif key == "rate_limit_per_minute":
            try:
                val_int = int(val)
            except (ValueError, TypeError):
                raise ValueError("rate_limit_per_minute must be an integer")
            if not (1 <= val_int <= 10000):
                raise ValueError("rate_limit_per_minute must be between 1 and 10000")
            self._runtime_overrides[key] = val_int
            self.config.server.rate_limit_per_minute = val_int
            logger.info(f"Runtime rate limit updated to {val_int} req/min")

        elif key == "crawler_max_depth":
            try:
                val_int = int(val)
            except (ValueError, TypeError):
                raise ValueError("crawler_max_depth must be an integer")
            if not (1 <= val_int <= 5):
                raise ValueError("crawler_max_depth must be between 1 and 5")
            self._runtime_overrides[key] = val_int
            self.config.crawl.max_depth = val_int
            logger.info(f"Runtime crawler max depth updated to {val_int}")

        elif key == "crawler_politeness_delay":
            try:
                val_float = float(val)
            except (ValueError, TypeError):
                raise ValueError("crawler_politeness_delay must be a float or integer")
            if not (0.1 <= val_float <= 30.0):
                raise ValueError(
                    "crawler_politeness_delay must be between 0.1 and 30.0 seconds"
                )
            self._runtime_overrides[key] = val_float
            self.config.crawl.crawl_delay = val_float
            logger.info(f"Runtime crawler politeness delay updated to {val_float}s")

        return self.get_runtime_config()
