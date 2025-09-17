"""
Production initialization for bulk signals.

This module provides production-ready initialization functions
for setting up bulk signals with proper dependency injection.
"""

import logging
from typing import Optional

from django_bulk_signals.config import get_config
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

logger = logging.getLogger(__name__)


def initialize_bulk_signals(
    environment: str = "production",
    custom_executor: Optional[object] = None,
    service_name: str = "default",
):
    """
    Initialize bulk signals for production use.

    Args:
        environment: Environment name (production, staging, development)
        custom_executor: Custom executor instance
        service_name: Name for the service registration
    """
    logger.info(f"Initializing bulk signals for {environment} environment")

    # Get configuration
    config = get_config()

    # Create executor based on environment and configuration
    executor = _create_executor_for_environment(environment, config, custom_executor)

    # Create service configuration
    service_config = TriggerServiceConfig(executor=executor)

    # Create and register service
    service = TriggerService(service_config)
    register_service(service, service_name)

    logger.info(f"Bulk signals initialized with {executor.__class__.__name__}")
    return service


def _create_executor_for_environment(environment: str, config, custom_executor=None):
    """Create appropriate executor for the environment."""
    if custom_executor:
        return custom_executor

    # Start with base executor
    executor = SyncTriggerExecutor()

    if environment == "production":
        # Production: Full feature set
        executor = _wrap_with_production_features(executor, config)
    elif environment == "staging":
        # Staging: Most features but lighter
        executor = _wrap_with_staging_features(executor, config)
    else:
        # Development: Minimal features
        executor = _wrap_with_development_features(executor, config)

    return executor


def _wrap_with_production_features(executor, config):
    """Wrap executor with production features."""
    # Add metrics
    if config.enable_metrics:
        executor = MetricsTriggerExecutor(executor)

    # Add circuit breaker
    if config.enable_circuit_breaker:
        executor = CircuitBreakerTriggerExecutor(
            executor,
            failure_threshold=config.circuit_breaker_failure_threshold,
            timeout=config.circuit_breaker_timeout,
        )

    # Add batching
    if config.batch_size > 0:
        executor = BatchedTriggerExecutor(executor, batch_size=config.batch_size)

    return executor


def _wrap_with_staging_features(executor, config):
    """Wrap executor with staging features."""
    # Add metrics but no circuit breaker
    if config.enable_metrics:
        executor = MetricsTriggerExecutor(executor)

    # Add batching
    if config.batch_size > 0:
        executor = BatchedTriggerExecutor(executor, batch_size=config.batch_size)

    return executor


def _wrap_with_development_features(executor, config):
    """Wrap executor with development features."""
    # Minimal features for development
    return executor


def create_custom_executor(executor_type: str, **kwargs):
    """
    Create a custom executor instance.

    Args:
        executor_type: Type of executor to create
        **kwargs: Executor-specific arguments
    """
    executor_classes = {
        "sync": SyncTriggerExecutor,
        "batched": BatchedTriggerExecutor,
        "metrics": MetricsTriggerExecutor,
        "circuit_breaker": CircuitBreakerTriggerExecutor,
        "composite": CompositeTriggerExecutor,
    }

    if executor_type not in executor_classes:
        raise ValueError(f"Unknown executor type: {executor_type}")

    executor_class = executor_classes[executor_type]
    return executor_class(**kwargs)


def get_production_service():
    """Get the production-configured service."""
    return initialize_bulk_signals(environment="production")


def get_development_service():
    """Get the development-configured service."""
    return initialize_bulk_signals(environment="development")
