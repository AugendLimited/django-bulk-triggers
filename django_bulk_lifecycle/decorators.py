from django_bulk_lifecycle.enums import DEFAULT_PRIORITY


def hook(event, *, model, condition=None, priority=DEFAULT_PRIORITY):
    """
    Decorator to annotate a method with multiple lifecycle hook registrations.
    If no priority is provided, uses Priority.NORMAL (50).
    """

    def decorator(fn):
        if not hasattr(fn, "lifecycle_hooks"):
            fn.lifecycle_hooks = []
        fn.lifecycle_hooks.append((model, event, condition, priority))
        return fn

    return decorator


def select_related(*related_fields):
    """
    Decorator for lifecycle hook functions. Replaces a list of instances
    with the same instances bulk-loaded using select_related().
    """

    def decorator(handler_func):
        def wrapper(*args, **kwargs):
            # Support instance method handlers (skip 'self')
            if len(args) == 0:
                raise TypeError(
                    "@select_related requires at least one positional argument"
                )

            # Assume the first argument is the instances list
            instances = args[0]

            if not isinstance(instances, list):
                raise TypeError(
                    f"@select_related expects a list of model instances as the first argument, got {type(instances)}"
                )

            if not instances:
                return handler_func(*args, **kwargs)

            model = instances[0].__class__
            ids = [obj.pk for obj in instances]
            preloaded = list(
                model.objects.select_related(*related_fields).filter(pk__in=ids)
            )

            # Rebuild args tuple with preloaded instances
            new_args = (preloaded,) + args[1:]
            return handler_func(*new_args, **kwargs)

        return wrapper

    return decorator
