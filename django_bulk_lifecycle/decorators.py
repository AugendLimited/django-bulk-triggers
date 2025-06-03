def hook(event, *, model, condition=None, priority=0):
    """
    Decorator to annotate a method with multiple lifecycle hook registrations.
    """
    def decorator(fn):
        if not hasattr(fn, "lifecycle_hooks"):
            fn.lifecycle_hooks = []
        fn.lifecycle_hooks.append((model, event, condition, priority))
        return fn
    return decorator
