import logging
from collections.abc import Callable
from typing import Union

from django_bulk_hooks.priority import Priority

logger = logging.getLogger(__name__)

_hooks: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_hook(
    model, event, handler_cls, method_name, condition, priority: Union[int, Priority]
):
    key = (model, event)
    hooks = _hooks.setdefault(key, [])
    hooks.append((handler_cls, method_name, condition, priority))
    # keep sorted by priority
    hooks.sort(key=lambda x: x[3])
    logger.info(
        "Registering hook: model=%s, event=%s, handler_cls=%s, method_name=%s, condition=%s, priority=%s",
        model.__name__,
        event,
        handler_cls.__name__,
        method_name,
        condition,
        priority,
    )


def get_hooks(model, event):
    hooks = _hooks.get((model, event), [])
    logger.info(
        "Retrieving hooks: model=%s, event=%s, hooks_found=%d",
        model.__name__,
        event,
        len(hooks),
    )
    return hooks


def list_all_hooks():
    """Debug function to list all registered hooks"""
    logger.debug("All registered hooks: %s", _hooks)
    return _hooks
