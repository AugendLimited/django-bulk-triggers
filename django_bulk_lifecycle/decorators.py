def hook(event, *, model, condition=None, priority=0):
    """
    Only annotate the method with its hook metadata.
    The TriggerHandler metaclass (or manual ready() registration)
    will pick this up later.
    """

    def decorator(fn):
        fn.lifecycle_hook = (model, event, condition, priority)
        return fn

    return decorator
