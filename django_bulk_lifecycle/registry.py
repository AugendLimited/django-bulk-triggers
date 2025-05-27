_registry = {}


def register_hook(model_cls, event, func, condition=None, priority=0):
    _registry.setdefault(model_cls, {}).setdefault(event, []).append(
        (priority, func, condition)
    )
    _registry[model_cls][event].sort(key=lambda x: x[0])  # sort by priority


def get_hooks(model_cls, event):
    return [
        (func, cond) for _, func, cond in _registry.get(model_cls, {}).get(event, [])
    ]
