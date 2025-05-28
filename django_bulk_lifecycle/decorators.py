from .registry import register_hook


def hook(event, model=None, condition=None, priority=0):
    def decorator(func):
        register_hook(model, event, func, condition, priority)
        return func

    return decorator
