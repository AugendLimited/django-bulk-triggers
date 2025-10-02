import logging
from collections.abc import Callable
from typing import Union

from django_bulk_triggers.enums import Priority

logger = logging.getLogger(__name__)

_triggers: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_trigger(
    model, event, handler_cls, method_name, condition, priority: Union[int, Priority]
):
    key = (model, event)
    triggers = _triggers.setdefault(key, [])

    # Check for duplicates before adding
    trigger_info = (handler_cls, method_name, condition, priority)
    if trigger_info not in triggers:
        triggers.append(trigger_info)
        # Sort by priority (lower values first)
        triggers.sort(key=lambda x: x[3])
        logger.debug(f"Registered {handler_cls.__name__}.{method_name} for {model.__name__}.{event}")
    else:
        logger.debug(f"Trigger {handler_cls.__name__}.{method_name} already registered for {model.__name__}.{event}")


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

    # Also clear the TriggerMeta._registered set to ensure clean state
    from django_bulk_triggers.handler import TriggerMeta
    TriggerMeta._registered.clear()

    logger.debug("Cleared all registered triggers")


def unregister_trigger(model, event, handler_cls, method_name):
    """
    Unregister a specific trigger.
    Used when child classes override parent trigger methods.
    """
    key = (model, event)
    if key not in _triggers:
        return
    
    triggers = _triggers[key]
    # Find and remove the specific trigger
    triggers[:] = [
        (h_cls, m_name, cond, pri)
        for h_cls, m_name, cond, pri in triggers
        if not (h_cls == handler_cls and m_name == method_name)
    ]
    
    # Clean up empty trigger lists
    if not triggers:
        del _triggers[key]
    
    logger.debug(f"Unregistered {handler_cls.__name__}.{method_name} for {model.__name__}.{event}")


def list_all_triggers():
    """Debug function to list all registered triggers"""
    return _triggers
