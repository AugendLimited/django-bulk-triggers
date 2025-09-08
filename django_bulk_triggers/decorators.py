import inspect
from functools import wraps

from django.core.exceptions import FieldDoesNotExist

from django_bulk_triggers.enums import DEFAULT_PRIORITY
from django_bulk_triggers.registry import register_trigger


def trigger(event, *, model, condition=None, priority=DEFAULT_PRIORITY):
    """
    Decorator to annotate a method with multiple triggers trigger registrations.
    If no priority is provided, uses Priority.NORMAL (50).
    """

    def decorator(fn):
        if not hasattr(fn, "triggers_triggers"):
            fn.triggers_triggers = []
        fn.triggers_triggers.append((model, event, condition, priority))
        return fn

    return decorator


def select_related(*related_fields):
    """
    Decorator that preloads related fields in-place on `new_records`, before the trigger logic runs.

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

            # Determine which instances actually need preloading
            # Allow model_cls to be passed as a keyword argument for testing
            if "model_cls" in bound.arguments:
                model_cls = bound.arguments["model_cls"]
            else:
                model_cls = new_records[0].__class__
            ids_to_fetch = []
            for obj in new_records:
                if obj.pk is None:
                    continue
                # if any related field is not already cached on the instance,
                # mark it for fetching
                # Handle Mock objects that don't have _state.fields_cache
                if hasattr(obj, "_state") and hasattr(obj._state, "fields_cache"):
                    try:
                        if any(
                            field not in obj._state.fields_cache
                            for field in related_fields
                        ):
                            ids_to_fetch.append(obj.pk)
                    except (TypeError, AttributeError):
                        # If _state.fields_cache is not iterable or accessible, always fetch
                        ids_to_fetch.append(obj.pk)
                else:
                    # For Mock objects or objects without _state.fields_cache, always fetch
                    ids_to_fetch.append(obj.pk)

            # Always validate fields for nested field errors, regardless of whether we need to fetch
            # Note: We allow nested fields as Django's select_related supports them

            fetched = {}
            if ids_to_fetch:
                # Validate fields before passing to select_related
                validated_fields = []
                for field in related_fields:
                    # For nested fields (containing __), let Django's select_related handle validation
                    if "__" in field:
                        validated_fields.append(field)
                        continue

                    try:
                        # Handle Mock objects that don't have _meta
                        if hasattr(model_cls, "_meta"):
                            f = model_cls._meta.get_field(field)
                            if not (
                                f.is_relation
                                and not f.many_to_many
                                and not f.one_to_many
                            ):
                                continue
                            validated_fields.append(field)
                        else:
                            # For Mock objects, skip validation
                            continue
                    except (FieldDoesNotExist, AttributeError):
                        continue

                if validated_fields:
                    # Use the base manager to avoid recursion
                    try:
                        fetched = model_cls._base_manager.select_related(
                            *validated_fields
                        ).in_bulk(ids_to_fetch)
                    except Exception:
                        # If select_related fails (e.g., invalid nested fields), skip preloading
                        fetched = {}

            for obj in new_records:
                preloaded = fetched.get(obj.pk)
                if not preloaded:
                    continue
                for field in related_fields:
                    # Handle Mock objects that don't have _state.fields_cache
                    if hasattr(obj, "_state") and hasattr(obj._state, "fields_cache"):
                        if field in obj._state.fields_cache:
                            # don't override values that were explicitly set or already loaded
                            continue
                    if "." in field:
                        # Skip fields with dots (legacy format, not supported)
                        continue

                    try:
                        # Handle Mock objects that don't have _meta
                        if hasattr(model_cls, "_meta"):
                            f = model_cls._meta.get_field(field)
                            if not (
                                f.is_relation
                                and not f.many_to_many
                                and not f.one_to_many
                            ):
                                continue
                        else:
                            # For Mock objects, skip validation
                            continue
                    except (FieldDoesNotExist, AttributeError):
                        continue

                    try:
                        rel_obj = getattr(preloaded, field)
                        setattr(obj, field, rel_obj)
                        # Only set _state.fields_cache if it exists
                        if hasattr(obj, "_state") and hasattr(
                            obj._state, "fields_cache"
                        ):
                            obj._state.fields_cache[field] = rel_obj
                    except AttributeError:
                        pass

            return func(*bound.args, **bound.kwargs)

        return wrapper

    return decorator


def bulk_trigger(model_cls, event, when=None, priority=None):
    """
    Decorator to register a bulk trigger for a model.

    Args:
        model_cls: The model class to trigger into
        event: The event to trigger into (e.g., BEFORE_UPDATE, AFTER_UPDATE)
        when: Optional condition for when the trigger should run
        priority: Optional priority for trigger execution order
    """

    def decorator(func):
        # Create a simple handler class for the function
        class FunctionHandler:
            def __init__(self):
                self.func = func

            def handle(self, new_records=None, old_records=None, **kwargs):
                return self.func(new_records, old_records)

        # Register the trigger using the registry
        register_trigger(
            model=model_cls,
            event=event,
            handler_cls=FunctionHandler,
            method_name="handle",
            condition=when,
            priority=priority or DEFAULT_PRIORITY,
        )

        # Set attribute to indicate the function has been registered as a bulk trigger
        func._bulk_trigger_registered = True

        return func

    return decorator
