import inspect
from functools import wraps

from django.core.exceptions import FieldDoesNotExist
from django_bulk_hooks.enums import DEFAULT_PRIORITY
from django_bulk_hooks.registry import register_hook


def hook(event, *, model, condition=None, priority=DEFAULT_PRIORITY):
    """
    Decorator to annotate a method with multiple hooks hook registrations.
    If no priority is provided, uses Priority.NORMAL (50).
    """

    def decorator(fn):
        if not hasattr(fn, "hooks_hooks"):
            fn.hooks_hooks = []
        fn.hooks_hooks.append((model, event, condition, priority))
        return fn

    return decorator


def select_related(*related_fields):
    """
    Decorator that preloads related fields in-place on `new_records`, before the hook logic runs.

    - Works with instance methods (resolves `self`)
    - Avoids replacing model instances
    - Populates Django's relation cache to avoid extra queries
    """

    def decorator(func):
        sig = inspect.signature(func)
        # Precompute the positional index of 'new_records' to avoid per-call binding
        param_names = list(sig.parameters.keys())
        new_records_pos = param_names.index("new_records") if "new_records" in param_names else None
        # Fail fast on nested fields (not supported)
        for f in related_fields:
            if "." in f:
                raise ValueError(f"@select_related does not support nested fields like '{f}'")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Fast retrieval of new_records without full signature binding
            new_records = kwargs.get("new_records")
            if new_records is None and new_records_pos is not None and len(args) > new_records_pos:
                new_records = args[new_records_pos]
            if new_records is None:
                # Fallback for uncommon signatures
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                if "new_records" not in bound.arguments:
                    raise TypeError("@select_related requires a 'new_records' argument in the decorated function")
                new_records = bound.arguments["new_records"]

            if not isinstance(new_records, list):
                raise TypeError(f"@select_related expects a list of model instances, got {type(new_records)}")

            if not new_records:
                return func(*args, **kwargs)

            # Determine which instances actually need preloading
            model_cls = new_records[0].__class__

            # Validate fields once per model class for this call
            valid_fields = []
            for field in related_fields:
                try:
                    f = model_cls._meta.get_field(field)
                    if f.is_relation and not f.many_to_many and not f.one_to_many:
                        valid_fields.append(field)
                except FieldDoesNotExist:
                    continue

            if not valid_fields:
                return func(*args, **kwargs)

            ids_to_fetch = []
            for obj in new_records:
                if obj.pk is None:
                    continue
                # If any valid related field is not cached, fetch this object
                if any(field not in obj._state.fields_cache for field in valid_fields):
                    ids_to_fetch.append(obj.pk)

            if not ids_to_fetch:
                return func(*args, **kwargs)

            # Deduplicate while preserving order
            seen = set()
            ids_to_fetch = [i for i in ids_to_fetch if not (i in seen or seen.add(i))]

            # Use the base manager to avoid recursion and preload in one query
            fetched = model_cls._base_manager.select_related(*valid_fields).in_bulk(ids_to_fetch)

            for obj in new_records:
                if obj.pk not in fetched:
                    continue
                preloaded = fetched[obj.pk]
                for field in valid_fields:
                    if field in obj._state.fields_cache:
                        continue
                    rel_obj = getattr(preloaded, field, None)
                    if rel_obj is None:
                        continue
                    setattr(obj, field, rel_obj)
                    obj._state.fields_cache[field] = rel_obj

            return func(*args, **kwargs)

        return wrapper

    return decorator


def bulk_hook(model_cls, event, when=None, priority=None):
    """
    Decorator to register a bulk hook for a model.
    
    Args:
        model_cls: The model class to hook into
        event: The event to hook into (e.g., BEFORE_UPDATE, AFTER_UPDATE)
        when: Optional condition for when the hook should run
        priority: Optional priority for hook execution order
    """
    def decorator(func):
        # Create a simple handler class for the function
        class FunctionHandler:
            def __init__(self):
                self.func = func
            
            def handle(self, new_instances, original_instances):
                return self.func(new_instances, original_instances)
        
        # Register the hook using the registry
        register_hook(
            model=model_cls,
            event=event,
            handler_cls=FunctionHandler,
            method_name='handle',
            condition=when,
            priority=priority or DEFAULT_PRIORITY,
        )
        return func
    return decorator
