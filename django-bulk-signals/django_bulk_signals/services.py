"""
Trigger service layer for bulk operations.

This module provides the core business logic for trigger orchestration,
separating concerns from infrastructure components.
"""

import logging
from typing import Any, List, Optional

from django.dispatch import Signal

from django_bulk_signals.conditions import TriggerCondition
from django_bulk_signals.config import get_executor_class, get_executor_kwargs
from django_bulk_signals.executors import TriggerExecutor

logger = logging.getLogger(__name__)


# TriggerExecutor is now imported from executors module


class TriggerServiceConfig:
    """Configuration for trigger service."""

    def __init__(
        self,
        executor: Optional[TriggerExecutor] = None,
        enable_metrics: bool = False,
        enable_circuit_breaker: bool = False,
    ):
        # Use configured executor if not provided
        if executor is None:
            executor_class = get_executor_class()
            executor_kwargs = get_executor_kwargs()
            executor = executor_class(**executor_kwargs)

        self.executor = executor
        self.enable_metrics = enable_metrics
        self.enable_circuit_breaker = enable_circuit_breaker


class TriggerService:
    """
    Service layer for trigger orchestration.

    This class handles the business logic of:
    - Filtering instances based on conditions
    - Executing trigger handlers
    - Managing trigger execution flow
    """

    def __init__(self, config: Optional[TriggerServiceConfig] = None):
        self.config = config or TriggerServiceConfig()
        self.logger = logger
        self.executor = self.config.executor

    def filter_instances(
        self,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        condition: Optional[TriggerCondition] = None,
    ) -> tuple[List[Any], List[Any]]:
        """
        Filter instances based on condition with performance optimizations.

        Args:
            instances: List of current instances
            originals: List of original instances (for comparison)
            condition: Optional condition to filter by

        Returns:
            Tuple of (filtered_instances, filtered_originals)
        """
        if not condition:
            return instances, originals or []

        if not instances:
            return [], []

        # Early exit for empty instances
        if len(instances) == 0:
            return [], []

        # Use list comprehension for better performance
        try:
            # Ensure originals list is same length as instances
            originals_list = originals or [None] * len(instances)

            # Use zip and list comprehension for better performance
            filtered_pairs = [
                (instance, original)
                for instance, original in zip(instances, originals_list)
                if self._check_condition_safe(condition, instance, original)
            ]

            if filtered_pairs:
                filtered_instances, filtered_originals = zip(*filtered_pairs)
                filtered_instances = list(filtered_instances)
                filtered_originals = list(filtered_originals)
            else:
                filtered_instances, filtered_originals = [], []

        except Exception as e:
            self.logger.error(f"Condition filtering failed: {e}")
            # Fallback to empty results on error
            filtered_instances, filtered_originals = [], []

        self.logger.debug(
            f"Filtered {len(filtered_instances)} instances from {len(instances)} "
            f"(condition: {condition.__class__.__name__})"
        )

        return filtered_instances, filtered_originals

    def _check_condition_safe(
        self, condition: TriggerCondition, instance: Any, original: Any
    ) -> bool:
        """Safely check condition with error handling."""
        try:
            return condition.check(instance, original)
        except Exception as e:
            self.logger.warning(f"Condition check failed for instance {instance}: {e}")
            return False

    def execute_triggers(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        condition: Optional[TriggerCondition] = None,
        **kwargs,
    ) -> None:
        """
        Execute triggers for the given signal.

        Args:
            signal: Django signal to fire
            sender: Model class sending the signal
            instances: List of instances
            originals: List of original instances (for comparison)
            condition: Optional condition to filter by
            **kwargs: Additional signal arguments
        """
        if not instances:
            return

        # Filter instances based on condition
        filtered_instances, filtered_originals = self.filter_instances(
            instances, originals, condition
        )

        if not filtered_instances:
            self.logger.debug(
                f"No instances met condition for signal {signal.__name__}"
            )
            return

        # Delegate to executor strategy
        self.executor.execute(
            signal, sender, filtered_instances, filtered_originals, **kwargs
        )

    def execute_before_triggers(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        condition: Optional[TriggerCondition] = None,
        **kwargs,
    ) -> None:
        """Execute BEFORE triggers."""
        self.execute_triggers(signal, sender, instances, originals, condition, **kwargs)

    def execute_after_triggers(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        condition: Optional[TriggerCondition] = None,
        **kwargs,
    ) -> None:
        """Execute AFTER triggers."""
        self.execute_triggers(signal, sender, instances, originals, condition, **kwargs)


# Service registry for dependency injection
_service_registry = {}


def register_service(service: TriggerService, name: str = "default"):
    """Register a service instance for dependency injection."""
    _service_registry[name] = service


def get_service(name: str = "default") -> TriggerService:
    """Get a registered service instance."""
    if name not in _service_registry:
        # Create and register default service
        default_service = TriggerService()
        _service_registry[name] = default_service
    return _service_registry[name]


def clear_services():
    """Clear all registered services (useful for testing)."""
    _service_registry.clear()


# Default service for backward compatibility
_default_service = get_service()
