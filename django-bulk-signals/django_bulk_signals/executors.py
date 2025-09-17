"""
Trigger execution strategies for bulk operations.

This module provides different execution strategies for triggers,
allowing for synchronous, asynchronous, batched, and other execution patterns.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from django.dispatch import Signal

logger = logging.getLogger(__name__)


class TriggerExecutor(ABC):
    """Abstract base class for trigger execution strategies."""

    @abstractmethod
    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers with the given strategy."""
        pass


class SyncTriggerExecutor(TriggerExecutor):
    """Synchronous trigger executor - executes triggers immediately."""

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers synchronously."""
        if not instances:
            return

        # Prepare signal arguments
        signal_kwargs = {"sender": sender, "instances": instances, **kwargs}

        if originals is not None:
            signal_kwargs["originals"] = originals

        # Fire the signal
        try:
            signal_name = getattr(signal, "__name__", str(signal))
            logger.debug(f"Firing signal {signal_name} for {len(instances)} instances")
            signal.send(**signal_kwargs)
        except Exception as e:
            signal_name = getattr(signal, "__name__", str(signal))
            logger.error(f"Signal {signal_name} handler failed: {e}")
            raise


class BatchedTriggerExecutor(TriggerExecutor):
    """Batched trigger executor - executes triggers in batches for performance."""

    def __init__(
        self, batch_size: int = 1000, executor: Optional[TriggerExecutor] = None
    ):
        self.batch_size = batch_size
        self.executor = executor or SyncTriggerExecutor()

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers in batches."""
        if not instances:
            return

        # Split into batches
        for i in range(0, len(instances), self.batch_size):
            batch_instances = instances[i : i + self.batch_size]
            batch_originals = originals[i : i + self.batch_size] if originals else None

            logger.debug(
                f"Executing batch {i // self.batch_size + 1} with {len(batch_instances)} instances"
            )

            # Execute batch
            self.executor.execute(
                signal, sender, batch_instances, batch_originals, **kwargs
            )


class AsyncTriggerExecutor(TriggerExecutor):
    """Asynchronous trigger executor - executes triggers asynchronously."""

    def __init__(self, executor: Optional[TriggerExecutor] = None):
        self.executor = executor or SyncTriggerExecutor()

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers asynchronously."""
        # For now, delegate to sync executor
        # In the future, this could use Celery, asyncio, or other async frameworks
        logger.debug(
            "AsyncTriggerExecutor: delegating to sync executor (async not implemented yet)"
        )
        self.executor.execute(signal, sender, instances, originals, **kwargs)


class CircuitBreakerTriggerExecutor(TriggerExecutor):
    """Circuit breaker trigger executor - prevents cascading failures."""

    def __init__(
        self,
        executor: Optional[TriggerExecutor] = None,
        failure_threshold: int = 5,
        timeout: int = 60,
    ):
        self.executor = executor or SyncTriggerExecutor()
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers with circuit breaker protection."""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                logger.warning("Circuit breaker is OPEN - skipping trigger execution")
                return

        try:
            self.executor.execute(signal, sender, instances, originals, **kwargs)
            self._on_success()
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit breaker."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.timeout

    def _on_success(self):
        """Handle successful execution."""
        self.failure_count = 0
        self.state = "CLOSED"

    def _on_failure(self):
        """Handle failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"Circuit breaker opened after {self.failure_count} failures")


class MetricsTriggerExecutor(TriggerExecutor):
    """Metrics trigger executor - collects execution metrics."""

    def __init__(self, executor: Optional[TriggerExecutor] = None):
        self.executor = executor or SyncTriggerExecutor()
        self.metrics = {}  # Simple in-memory metrics for now

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers with metrics collection."""
        signal_name = getattr(signal, "__name__", str(signal))
        start_time = time.time()

        try:
            self.executor.execute(signal, sender, instances, originals, **kwargs)

            # Record success metrics
            execution_time = time.time() - start_time
            self._record_metric(f"{signal_name}.success", 1)
            self._record_metric(f"{signal_name}.execution_time", execution_time)
            self._record_metric(f"{signal_name}.instance_count", len(instances))

        except Exception as e:
            # Record failure metrics
            execution_time = time.time() - start_time
            self._record_metric(f"{signal_name}.failure", 1)
            self._record_metric(f"{signal_name}.execution_time", execution_time)
            raise

    def _record_metric(self, name: str, value: float):
        """Record a metric value."""
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(value)

    def get_metrics(self) -> dict:
        """Get collected metrics."""
        return self.metrics.copy()


# Composite executor for combining multiple strategies
class CompositeTriggerExecutor(TriggerExecutor):
    """Composite executor that combines multiple execution strategies."""

    def __init__(self, *executors: TriggerExecutor):
        self.executors = executors

    def execute(
        self,
        signal: Signal,
        sender: Any,
        instances: List[Any],
        originals: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        """Execute triggers using all configured executors."""
        for executor in self.executors:
            executor.execute(signal, sender, instances, originals, **kwargs)
