from collections.abc import Callable
from typing import Union

from django_bulk_hooks.enums import Priority

_hooks: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_hook(
    model, event, handler_cls, method_name, condition, priority: Union[int, Priority]
):
    key = (model, event)
    hooks = _hooks.setdefault(key, [])
    hooks.append((handler_cls, method_name, condition, priority))
    # keep sorted by priority
    hooks.sort(key=lambda x: x[3])


def get_hooks(model, event):
    return _hooks.get((model, event), [])


def list_all_hooks():
    """Debug function to list all registered hooks"""
    return _hooks
