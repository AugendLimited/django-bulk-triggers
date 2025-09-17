"""
Example Django settings for production use of bulk signals.

This file shows how to properly configure bulk signals in production
with dependency injection and enterprise features.
"""

# Example Django settings.py configuration for bulk signals

# Basic configuration
BULK_SIGNALS_EXECUTOR_CLASS = "django_bulk_signals.executors.SyncTriggerExecutor"
BULK_SIGNALS_EXECUTOR_KWARGS = {}

# Performance configuration
BULK_SIGNALS_BATCH_SIZE = 1000
BULK_SIGNALS_ENABLE_CACHING = True
BULK_SIGNALS_CACHE_TTL = 300

# Circuit breaker configuration for resilience
BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = True
BULK_SIGNALS_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
BULK_SIGNALS_CIRCUIT_BREAKER_TIMEOUT = 60

# Metrics configuration
BULK_SIGNALS_ENABLE_METRICS = True
BULK_SIGNALS_METRICS_BACKEND = "prometheus"  # or "memory", "statsd"

# Logging configuration
BULK_SIGNALS_LOG_LEVEL = "INFO"
BULK_SIGNALS_LOG_EXECUTION_TIME = True
BULK_SIGNALS_LOG_INSTANCE_COUNTS = True

# Error handling configuration
BULK_SIGNALS_FAIL_FAST = True
BULK_SIGNALS_MAX_RETRIES = 3
BULK_SIGNALS_RETRY_DELAY = 1.0

# Advanced configuration examples:

# Example 1: Batched execution for high-volume operations
BULK_SIGNALS_EXECUTOR_CLASS = "django_bulk_signals.executors.BatchedTriggerExecutor"
BULK_SIGNALS_EXECUTOR_KWARGS = {
    "batch_size": 500,
    "executor": "django_bulk_signals.executors.SyncTriggerExecutor",
}

# Example 2: Composite executor with multiple features
BULK_SIGNALS_EXECUTOR_CLASS = "django_bulk_signals.executors.CompositeTriggerExecutor"
BULK_SIGNALS_EXECUTOR_KWARGS = {
    "executors": [
        "django_bulk_signals.executors.MetricsTriggerExecutor",
        "django_bulk_signals.executors.CircuitBreakerTriggerExecutor",
        "django_bulk_signals.executors.BatchedTriggerExecutor",
    ]
}

# Example 3: Custom executor for async processing
BULK_SIGNALS_EXECUTOR_CLASS = "myapp.executors.CeleryTriggerExecutor"
BULK_SIGNALS_EXECUTOR_KWARGS = {"queue": "bulk_signals", "priority": "high"}

# Example 4: Development vs Production settings
import os

if os.environ.get("ENVIRONMENT") == "production":
    # Production settings
    BULK_SIGNALS_ENABLE_METRICS = True
    BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = True
    BULK_SIGNALS_BATCH_SIZE = 2000
    BULK_SIGNALS_LOG_LEVEL = "WARNING"
else:
    # Development settings
    BULK_SIGNALS_ENABLE_METRICS = False
    BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = False
    BULK_SIGNALS_BATCH_SIZE = 100
    BULK_SIGNALS_LOG_LEVEL = "DEBUG"
