from collections.abc import Callable
from typing import Union

from django_bulk_hooks.priority import Priority

_hooks: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_hook(
    model, event, handler_cls, method_name, condition, priority: Union[int, Priority]
):
    key = (model, event)
    hooks = _hooks.setdefault(key, [])
    hooks.append((handler_cls, method_name, condition, priority))
    # keep sorted by priority
    hooks.sort(key=lambda x: x[3])
    print(f"DEBUG: Registered hook {handler_cls.__name__}.{method_name} for {model.__name__}.{event} with condition: {condition}")
    print(f"DEBUG: Model class: {model} (id: {id(model)})")
    print(f"DEBUG: Total hooks for {model.__name__}.{event}: {len(hooks)}")


def get_hooks(model, event):
    key = (model, event)
    hooks = _hooks.get(key, [])
    print(f"DEBUG: get_hooks called for {model.__name__}.{event}, found {len(hooks)} hooks")
    print(f"DEBUG: Hook key: {key}")
    print(f"DEBUG: Model class: {model} (id: {id(model)})")
    print(f"DEBUG: All registered hook keys: {list(_hooks.keys())}")
    for hook in hooks:
        handler_cls, method_name, condition, priority = hook
        print(f"DEBUG: Hook: {handler_cls.__name__}.{method_name} with condition: {condition}")
    return hooks


def list_all_hooks():
    """Debug function to list all registered hooks"""
    return _hooks
