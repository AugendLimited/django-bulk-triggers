import logging
from collections.abc import Callable
from typing import Union

from django_bulk_triggers.priority import Priority

logger = logging.getLogger(__name__)

_triggers: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_trigger(
    model, event, handler_cls, method_name, condition, priority: Union[int, Priority]
):
    key = (model, event)
    triggers = _triggers.setdefault(key, [])
    triggers.append((handler_cls, method_name, condition, priority))
    # Sort by priority (lower values first)
    triggers.sort(key=lambda x: x[3])
    logger.debug(f"Registered {handler_cls.__name__}.{method_name} for {model.__name__}.{event}")


def get_triggers(model, event):
    key = (model, event)
    triggers = _triggers.get(key, [])
    # Only log when triggers are found or for specific events to reduce noise
    if triggers or event in ['after_update', 'before_update', 'after_create', 'before_create']:
        logger.debug(f"get_triggers {model.__name__}.{event} found {len(triggers)} triggers")
    return triggers


def clear_triggers():
    """Clear all registered triggers. Useful for testing."""
    global _triggers
    _triggers.clear()
    logger.debug("Cleared all registered triggers")


def list_all_triggers():
    """Debug function to list all registered triggers"""
    return _triggers
