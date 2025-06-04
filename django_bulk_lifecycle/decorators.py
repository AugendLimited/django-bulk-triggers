import inspect
from functools import wraps
from django.core.exceptions import FieldDoesNotExist

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


def preload_related(*related_fields):
    """
    Decorator that preloads related fields in-place on `new_records`, before the hook logic runs.

    - Works with instance methods (resolves `self`)
    - Avoids replacing model instances
    - Populates Django's relation cache to avoid extra queries
    """

    def decorator(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            if "new_records" not in bound.arguments:
                raise TypeError(
                    "@preload_related requires a 'new_records' argument in the decorated function"
                )

            new_records = bound.arguments["new_records"]

            if not isinstance(new_records, list):
                raise TypeError(
                    f"@preload_related expects a list of model instances, got {type(new_records)}"
                )

            if not new_records:
                return func(*args, **kwargs)

            # In-place preload
            model_cls = new_records[0].__class__
            ids = [obj.pk for obj in new_records if obj.pk is not None]
            if not ids:
                return func(*args, **kwargs)

            fetched = model_cls.objects.select_related(*related_fields).in_bulk(ids)

            for obj in new_records:
                preloaded = fetched.get(obj.pk)
                if not preloaded:
                    continue
                for field in related_fields:
                    if "." in field:
                        raise ValueError(
                            f"@preload_related does not support nested fields like '{field}'"
                        )

                    try:
                        f = model_cls._meta.get_field(field)
                        if not (
                            f.is_relation and not f.many_to_many and not f.one_to_many
                        ):
                            continue
                    except FieldDoesNotExist:
                        continue

                    try:
                        rel_obj = getattr(preloaded, field)
                        setattr(obj, field, rel_obj)
                        obj._state.fields_cache[field] = rel_obj
                    except AttributeError:
                        pass

            return func(*bound.args, **bound.kwargs)

        return wrapper

    return decorator
