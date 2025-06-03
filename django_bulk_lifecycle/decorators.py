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
    Decorator to preload related fields in bulk via select_related.
    Prevents N+1 queries in lifecycle hooks or bulk handlers by ensuring
    related objects are loaded efficiently.
    """

    def decorator(handler_func):
        def wrapper(instances, *args, **kwargs):
            if not instances:
                return handler_func(instances, *args, **kwargs)

            if hasattr(instances, "select_related"):
                # It's a queryset: use select_related directly
                instances = instances.select_related(*related_fields)
            else:
                # It's a list of instances: reload in bulk using select_related
                model = instances[0].__class__
                ids = [obj.pk for obj in instances]
                instances = list(
                    model.objects.select_related(*related_fields).filter(pk__in=ids)
                )

            return handler_func(instances, *args, **kwargs)

        return wrapper

    return decorator
