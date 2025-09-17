"""
Django settings integration for bulk signals.

This module provides Django settings integration for configuring
bulk signals behavior in production.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_bulk_signals_setting(setting_name: str, default=None):
    """Get a bulk signals setting from Django settings."""
    return getattr(settings, f"BULK_SIGNALS_{setting_name}", default)


def validate_bulk_signals_settings():
    """Validate bulk signals settings."""
    # Validate executor class
    executor_class = get_bulk_signals_setting("EXECUTOR_CLASS")
    if executor_class:
        try:
            module_path, class_name = executor_class.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)
        except (ImportError, AttributeError, ValueError) as e:
            raise ImproperlyConfigured(
                f"Invalid BULK_SIGNALS_EXECUTOR_CLASS: {executor_class}. Error: {e}"
            )

    # Validate batch size
    batch_size = get_bulk_signals_setting("BATCH_SIZE", 1000)
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ImproperlyConfigured(
            f"BULK_SIGNALS_BATCH_SIZE must be a positive integer, got: {batch_size}"
        )

    # Validate circuit breaker settings
    if get_bulk_signals_setting("ENABLE_CIRCUIT_BREAKER", False):
        failure_threshold = get_bulk_signals_setting(
            "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5
        )
        timeout = get_bulk_signals_setting("CIRCUIT_BREAKER_TIMEOUT", 60)

        if not isinstance(failure_threshold, int) or failure_threshold < 1:
            raise ImproperlyConfigured(
                f"BULK_SIGNALS_CIRCUIT_BREAKER_FAILURE_THRESHOLD must be a positive integer, got: {failure_threshold}"
            )

        if not isinstance(timeout, (int, float)) or timeout < 1:
            raise ImproperlyConfigured(
                f"BULK_SIGNALS_CIRCUIT_BREAKER_TIMEOUT must be a positive number, got: {timeout}"
            )

    # Validate cache TTL
    cache_ttl = get_bulk_signals_setting("CACHE_TTL", 300)
    if not isinstance(cache_ttl, int) or cache_ttl < 1:
        raise ImproperlyConfigured(
            f"BULK_SIGNALS_CACHE_TTL must be a positive integer, got: {cache_ttl}"
        )


# Default settings for bulk signals
DEFAULT_BULK_SIGNALS_SETTINGS = {
    "EXECUTOR_CLASS": "django_bulk_signals.executors.SyncTriggerExecutor",
    "EXECUTOR_KWARGS": {},
    "BATCH_SIZE": 1000,
    "ENABLE_CACHING": False,
    "CACHE_TTL": 300,
    "ENABLE_CIRCUIT_BREAKER": False,
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD": 5,
    "CIRCUIT_BREAKER_TIMEOUT": 60,
    "ENABLE_METRICS": False,
    "METRICS_BACKEND": "memory",
    "LOG_LEVEL": "INFO",
    "LOG_EXECUTION_TIME": False,
    "LOG_INSTANCE_COUNTS": True,
    "FAIL_FAST": True,
    "MAX_RETRIES": 0,
    "RETRY_DELAY": 1.0,
}


def get_all_bulk_signals_settings():
    """Get all bulk signals settings with defaults."""
    settings_dict = {}
    for key, default_value in DEFAULT_BULK_SIGNALS_SETTINGS.items():
        settings_dict[key] = get_bulk_signals_setting(key, default_value)
    return settings_dict
