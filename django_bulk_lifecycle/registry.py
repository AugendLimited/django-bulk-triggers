from collections.abc import Callable

_hooks: dict[tuple[type, str], list[tuple[type, str, Callable, int]]] = {}


def register_hook(model, event, handler_cls, method_name, condition, priority):
    key = (model, event)
    hooks = _hooks.setdefault(key, [])
    hooks.append((handler_cls, method_name, condition, priority))
    # keep sorted by priority
    hooks.sort(key=lambda x: x[3])


def get_hooks(model, event):
    return _hooks.get((model, event), [])
