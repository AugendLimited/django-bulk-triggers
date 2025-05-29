from collections.abc import Callable


_hooks: dict[tuple[type, str], list[tuple[callable, Callable, int]]] = {}


def register_hook(model, event, func, condition, priority):
    key = (model, event)
    _hooks.setdefault(key, []).append((func, condition, priority))
    _hooks[key].sort(key=lambda x: x[2])


def get_hooks(model, event):
    return _hooks.get((model, event), [])
