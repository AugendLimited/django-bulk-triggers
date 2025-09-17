"""
Django app configuration for bulk signals.

This module provides proper Django app configuration with dependency injection
setup for production use.
"""

from django.apps import AppConfig
from django.conf import settings

from django_bulk_signals.config import get_executor_class, get_executor_kwargs
from django_bulk_signals.executors import (
    BatchedTriggerExecutor,
    CircuitBreakerTriggerExecutor,
    CompositeTriggerExecutor,
    MetricsTriggerExecutor,
    SyncTriggerExecutor,
)
from django_bulk_signals.services import (
    TriggerService,
    TriggerServiceConfig,
    register_service,
)


class BulkSignalsConfig(AppConfig):
    """Django app configuration for bulk signals."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_bulk_signals"
    verbose_name = "Django Bulk Signals"

    def ready(self):
        """Initialize services when Django app is ready."""
        self._setup_default_service()
        self._setup_configured_services()

    def _setup_default_service(self):
        """Setup the default service with basic configuration."""
        default_service = TriggerService()
        register_service(default_service, "default")

    def _setup_configured_services(self):
        """Setup services based on Django settings configuration."""
        # Get configured executor
        executor_class = get_executor_class()
        executor_kwargs = get_executor_kwargs()

        # Create executor instance
        executor = executor_class(**executor_kwargs)

        # Wrap with additional executors based on configuration
        executor = self._wrap_executor_with_features(executor)

        # Create configured service
        config = TriggerServiceConfig(executor=executor)
        configured_service = TriggerService(config)

        # Register configured service
        register_service(configured_service, "configured")

        # Make configured service the default
        register_service(configured_service, "default")

    def _wrap_executor_with_features(self, executor):
        """Wrap executor with additional features based on configuration."""
        from django_bulk_signals.config import get_config

        config = get_config()

        # Add metrics if enabled
        if config.enable_metrics:
            executor = MetricsTriggerExecutor(executor)

        # Add circuit breaker if enabled
        if config.enable_circuit_breaker:
            executor = CircuitBreakerTriggerExecutor(
                executor,
                failure_threshold=config.circuit_breaker_failure_threshold,
                timeout=config.circuit_breaker_timeout,
            )

        # Add batching if batch size is configured
        if config.batch_size > 0:
            executor = BatchedTriggerExecutor(executor, batch_size=config.batch_size)

        return executor
