from collections.abc import Callable
from typing import Union

from django_bulk_hooks.priority import Priority

import logging

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
    logger.debug(
        "Registering hook: model=%s, event=%s, handler_cls=%s, method_name=%s, condition=%s, priority=%s",
        model.__name__,
        event,
        handler_cls.__name__,
        method_name,
        condition,
        priority,
    )


def get_hooks(model, event):
    logger.debug(
        "Retrieving hooks: model=%s, event=%s, hooks_found=%d",
        model.__name__,
        event,
        len(_hooks.get((model, event), [])),
    )
    return _hooks.get((model, event), [])
