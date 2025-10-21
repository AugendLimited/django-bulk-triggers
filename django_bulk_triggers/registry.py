"""
Central registry for trigger handlers.

Provides thread-safe registration and lookup of triggers with
deterministic priority ordering.
"""

import logging
import threading
from collections.abc import Callable
from typing import Dict, List, Optional, Tuple, Type, Union

from django_bulk_triggers.enums import Priority

logger = logging.getLogger(__name__)

# Type alias for trigger info tuple
TriggerInfo = Tuple[Type, str, Optional[Callable], int]


class TriggerRegistry:
    """
    Central registry for all trigger handlers.

    Manages registration, lookup, and lifecycle of triggers with
    thread-safe operations and deterministic ordering by priority.

    This is a singleton - use get_registry() to access the instance.
    """

    def __init__(self):
        """Initialize an empty registry with thread-safe storage."""
        self._triggers: Dict[Tuple[Type, str], List[TriggerInfo]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        model: Type,
        event: str,
        handler_cls: Type,
        method_name: str,
        condition: Optional[Callable],
        priority: Union[int, Priority],
    ) -> None:
        """
        Register a trigger handler for a model and event.

        Args:
            model: Django model class
            event: Event name (e.g., 'after_update', 'before_create')
            handler_cls: Trigger handler class
            method_name: Name of the method to call on handler
            condition: Optional condition to filter records
            priority: Execution priority (lower values execute first)
        """
        with self._lock:
            key = (model, event)
            triggers = self._triggers.setdefault(key, [])

            # Check for duplicates before adding
            trigger_info = (handler_cls, method_name, condition, priority)
            if trigger_info not in triggers:
                triggers.append(trigger_info)
                # Sort by priority (lower values first)
                triggers.sort(key=lambda x: x[3])
                logger.debug(
                    f"Registered {handler_cls.__name__}.{method_name} "
                    f"for {model.__name__}.{event} (priority={priority})"
                )
            else:
                logger.debug(
                    f"Trigger {handler_cls.__name__}.{method_name} "
                    f"already registered for {model.__name__}.{event}"
                )

    def get_triggers(self, model: Type, event: str) -> List[TriggerInfo]:
        """
        Get all triggers for a model and event.

        Args:
            model: Django model class
            event: Event name

        Returns:
            List of trigger info tuples (handler_cls, method_name, condition, priority)
            sorted by priority (lower values first)
        """
        with self._lock:
            key = (model, event)
            triggers = self._triggers.get(key, [])

            # Only log when triggers are found or for specific events to reduce noise
            if triggers or event in [
                "after_update",
                "before_update",
                "after_create",
                "before_create",
            ]:
                logger.debug(
                    f"get_triggers {model.__name__}.{event} found {len(triggers)} triggers"
                )

            return triggers

    def unregister(
        self, model: Type, event: str, handler_cls: Type, method_name: str
    ) -> None:
        """
        Unregister a specific trigger handler.

        Used when child classes override parent trigger methods.

        Args:
            model: Django model class
            event: Event name
            handler_cls: Trigger handler class to remove
            method_name: Method name to remove
        """
        with self._lock:
            key = (model, event)
            if key not in self._triggers:
                return

            triggers = self._triggers[key]
            # Filter out the specific trigger
            self._triggers[key] = [
                (h_cls, m_name, cond, pri)
                for h_cls, m_name, cond, pri in triggers
                if not (h_cls == handler_cls and m_name == method_name)
            ]

            # Clean up empty trigger lists
            if not self._triggers[key]:
                del self._triggers[key]

            logger.debug(
                f"Unregistered {handler_cls.__name__}.{method_name} "
                f"for {model.__name__}.{event}"
            )

    def clear(self) -> None:
        """
        Clear all registered triggers.

        Useful for testing to ensure clean state between tests.
        """
        with self._lock:
            self._triggers.clear()

            # Also clear TriggerMeta state to ensure complete reset
            from django_bulk_triggers.handler import TriggerMeta

            TriggerMeta._registered.clear()
            TriggerMeta._class_trigger_map.clear()

            logger.debug("Cleared all registered triggers")

    def list_all(self) -> Dict[Tuple[Type, str], List[TriggerInfo]]:
        """
        Get all registered triggers for debugging.

        Returns:
            Dictionary mapping (model, event) tuples to lists of trigger info
        """
        with self._lock:
            return dict(self._triggers)

    def count_triggers(
        self, model: Optional[Type] = None, event: Optional[str] = None
    ) -> int:
        """
        Count registered triggers, optionally filtered by model and/or event.

        Args:
            model: Optional model class to filter by
            event: Optional event name to filter by

        Returns:
            Number of matching triggers
        """
        with self._lock:
            if model is None and event is None:
                # Count all triggers
                return sum(len(triggers) for triggers in self._triggers.values())
            elif model is not None and event is not None:
                # Count triggers for specific model and event
                return len(self._triggers.get((model, event), []))
            elif model is not None:
                # Count all triggers for a model
                return sum(
                    len(triggers)
                    for (m, _), triggers in self._triggers.items()
                    if m == model
                )
            else:  # event is not None
                # Count all triggers for an event
                return sum(
                    len(triggers)
                    for (_, e), triggers in self._triggers.items()
                    if e == event
                )


# Global singleton registry
_registry: Optional[TriggerRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> TriggerRegistry:
    """
    Get the global trigger registry instance.

    Creates the registry on first access (singleton pattern).
    Thread-safe initialization.

    Returns:
        TriggerRegistry singleton instance
    """
    global _registry

    if _registry is None:
        with _registry_lock:
            # Double-checked locking
            if _registry is None:
                _registry = TriggerRegistry()

    return _registry


# Backward-compatible module-level functions
def register_trigger(
    model: Type,
    event: str,
    handler_cls: Type,
    method_name: str,
    condition: Optional[Callable],
    priority: Union[int, Priority],
) -> None:
    """
    Register a trigger handler (backward-compatible function).

    Delegates to the global registry instance.
    """
    registry = get_registry()
    registry.register(model, event, handler_cls, method_name, condition, priority)


def get_triggers(model: Type, event: str) -> List[TriggerInfo]:
    """
    Get triggers for a model and event (backward-compatible function).

    Delegates to the global registry instance.
    """
    registry = get_registry()
    return registry.get_triggers(model, event)


def unregister_trigger(
    model: Type, event: str, handler_cls: Type, method_name: str
) -> None:
    """
    Unregister a trigger handler (backward-compatible function).

    Delegates to the global registry instance.
    """
    registry = get_registry()
    registry.unregister(model, event, handler_cls, method_name)


def clear_triggers() -> None:
    """
    Clear all registered triggers (backward-compatible function).

    Delegates to the global registry instance.
    Useful for testing.
    """
    registry = get_registry()
    registry.clear()


def list_all_triggers() -> Dict[Tuple[Type, str], List[TriggerInfo]]:
    """
    List all registered triggers (backward-compatible function).

    Delegates to the global registry instance.
    """
    registry = get_registry()
    return registry.list_all()
