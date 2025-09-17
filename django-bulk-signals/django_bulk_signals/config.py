"""
Configuration management for bulk signals.

This module provides configuration management for the bulk signals system,
allowing for easy customization of behavior without code changes.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from django.conf import settings

from django_bulk_signals.settings import (
    get_all_bulk_signals_settings,
    validate_bulk_signals_settings,
)

logger = logging.getLogger(__name__)


@dataclass
class BulkSignalsConfig:
    """Configuration for bulk signals system."""

    # Execution strategy
    executor_class: str = "django_bulk_signals.executors.SyncTriggerExecutor"
    executor_kwargs: Dict[str, Any] = field(default_factory=dict)

    # Performance settings
    batch_size: int = 1000
    enable_caching: bool = False
    cache_ttl: int = 300  # 5 minutes

    # Circuit breaker settings
    enable_circuit_breaker: bool = False
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_timeout: int = 60

    # Metrics settings
    enable_metrics: bool = False
    metrics_backend: str = "memory"  # memory, prometheus, statsd

    # Logging settings
    log_level: str = "INFO"
    log_execution_time: bool = False
    log_instance_counts: bool = True

    # Error handling
    fail_fast: bool = True
    max_retries: int = 0
    retry_delay: float = 1.0

    # Django integration
    use_django_settings: bool = True
    custom_settings_prefix: str = "BULK_SIGNALS"


class ConfigManager:
    """Manages configuration for bulk signals."""

    def __init__(self, config: Optional[BulkSignalsConfig] = None):
        self._config = config or BulkSignalsConfig()
        self._load_from_django_settings()

    def _load_from_django_settings(self):
        """Load configuration from Django settings."""
        if not self._config.use_django_settings:
            return

        # Validate settings first
        try:
            validate_bulk_signals_settings()
        except Exception as e:
            logger.error(f"Invalid bulk signals settings: {e}")
            return

        # Load all settings
        settings_dict = get_all_bulk_signals_settings()

        # Update configuration
        self._config.executor_class = settings_dict["EXECUTOR_CLASS"]
        self._config.executor_kwargs = settings_dict["EXECUTOR_KWARGS"]
        self._config.batch_size = settings_dict["BATCH_SIZE"]
        self._config.enable_caching = settings_dict["ENABLE_CACHING"]
        self._config.cache_ttl = settings_dict["CACHE_TTL"]
        self._config.enable_circuit_breaker = settings_dict["ENABLE_CIRCUIT_BREAKER"]
        self._config.circuit_breaker_failure_threshold = settings_dict[
            "CIRCUIT_BREAKER_FAILURE_THRESHOLD"
        ]
        self._config.circuit_breaker_timeout = settings_dict["CIRCUIT_BREAKER_TIMEOUT"]
        self._config.enable_metrics = settings_dict["ENABLE_METRICS"]
        self._config.metrics_backend = settings_dict["METRICS_BACKEND"]
        self._config.log_level = settings_dict["LOG_LEVEL"]
        self._config.log_execution_time = settings_dict["LOG_EXECUTION_TIME"]
        self._config.log_instance_counts = settings_dict["LOG_INSTANCE_COUNTS"]
        self._config.fail_fast = settings_dict["FAIL_FAST"]
        self._config.max_retries = settings_dict["MAX_RETRIES"]
        self._config.retry_delay = settings_dict["RETRY_DELAY"]

    def get_executor_class(self):
        """Get the executor class."""
        try:
            module_path, class_name = self._config.executor_class.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            logger.error(
                f"Failed to import executor class {self._config.executor_class}: {e}"
            )
            # Fallback to default
            from django_bulk_signals.executors import SyncTriggerExecutor

            return SyncTriggerExecutor

    def get_executor_kwargs(self) -> Dict[str, Any]:
        """Get executor kwargs."""
        return self._config.executor_kwargs.copy()

    def get_config(self) -> BulkSignalsConfig:
        """Get the current configuration."""
        return self._config

    def update_config(self, **kwargs):
        """Update configuration values."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
            else:
                logger.warning(f"Unknown configuration key: {key}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "executor_class": self._config.executor_class,
            "executor_kwargs": self._config.executor_kwargs,
            "batch_size": self._config.batch_size,
            "enable_caching": self._config.enable_caching,
            "cache_ttl": self._config.cache_ttl,
            "enable_circuit_breaker": self._config.enable_circuit_breaker,
            "circuit_breaker_failure_threshold": self._config.circuit_breaker_failure_threshold,
            "circuit_breaker_timeout": self._config.circuit_breaker_timeout,
            "enable_metrics": self._config.enable_metrics,
            "metrics_backend": self._config.metrics_backend,
            "log_level": self._config.log_level,
            "log_execution_time": self._config.log_execution_time,
            "log_instance_counts": self._config.log_instance_counts,
            "fail_fast": self._config.fail_fast,
            "max_retries": self._config.max_retries,
            "retry_delay": self._config.retry_delay,
        }


# Global configuration manager instance
config_manager = ConfigManager()


def get_config() -> BulkSignalsConfig:
    """Get the current configuration."""
    return config_manager.get_config()


def update_config(**kwargs):
    """Update configuration values."""
    config_manager.update_config(**kwargs)


def get_executor_class():
    """Get the configured executor class."""
    return config_manager.get_executor_class()


def get_executor_kwargs() -> Dict[str, Any]:
    """Get executor configuration kwargs."""
    return config_manager.get_executor_kwargs()
