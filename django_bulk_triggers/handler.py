import logging

from django_bulk_triggers.registry import register_trigger

logger = logging.getLogger(__name__)


class TriggerMeta(type):
    _registered = set()
    _class_trigger_map: dict[type, set[tuple]] = {}  # Track which triggers belong to which class

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        mcs._register_triggers_for_class(cls)
        return cls

    @classmethod
    def _register_triggers_for_class(mcs, cls):
        """
        Register triggers for a given class following OOP inheritance semantics.
        
        - Child classes inherit all parent trigger methods
        - Child overrides replace parent implementations (not add to them)
        - Child can add new trigger methods
        """
        from django_bulk_triggers.registry import register_trigger, unregister_trigger
        
        # Step 1: Unregister ALL triggers from parent classes in the MRO
        # This ensures only the most-derived class owns the active triggers,
        # providing true OOP semantics (overrides replace, others are inherited once).
        for base in cls.__mro__[1:]:  # Skip cls itself, start from first parent
            if not isinstance(base, TriggerMeta):
                continue

            if base in mcs._class_trigger_map:
                for model_cls, event, base_cls, method_name in list(mcs._class_trigger_map[base]):
                    key = (model_cls, event, base_cls, method_name)
                    if key in TriggerMeta._registered:
                        unregister_trigger(model_cls, event, base_cls, method_name)
                        TriggerMeta._registered.discard(key)
                        logger.debug(
                            f"Unregistered base trigger: {base_cls.__name__}.{method_name} "
                            f"(superseded by {cls.__name__})"
                        )
        
        # Step 2: Register all trigger methods on this class (including inherited ones)
        # Walk the MRO to find ALL methods with trigger decorators
        all_trigger_methods = {}
        for klass in reversed(cls.__mro__):  # Start from most base class
            if not isinstance(klass, TriggerMeta):
                continue
            for method_name, method in klass.__dict__.items():
                if hasattr(method, "triggers_triggers"):
                    # Store with method name as key - child methods will override parent
                    all_trigger_methods[method_name] = method
        
        # Step 3: Register all trigger methods with THIS class as the handler
        if cls not in mcs._class_trigger_map:
            mcs._class_trigger_map[cls] = set()
        
        for method_name, method in all_trigger_methods.items():
            if hasattr(method, "triggers_triggers"):
                for model_cls, event, condition, priority in method.triggers_triggers:
                    key = (model_cls, event, cls, method_name)
                    if key not in TriggerMeta._registered:
                        register_trigger(
                            model=model_cls,
                            event=event,
                            handler_cls=cls,
                            method_name=method_name,
                            condition=condition,
                            priority=priority,
                        )
                        TriggerMeta._registered.add(key)
                        mcs._class_trigger_map[cls].add(key)
                        logger.debug(
                            f"Registered trigger: {cls.__name__}.{method_name} "
                            f"for {model_cls.__name__}.{event}"
                        )

    @classmethod
    def re_register_all_triggers(mcs):
        """Re-register all triggers for all existing Trigger classes."""
        # Clear the registered set and class trigger map so we can re-register
        TriggerMeta._registered.clear()
        mcs._class_trigger_map.clear()

        # Find all Trigger classes and re-register their triggers
        import gc

        registered_classes = set()
        for obj in gc.get_objects():
            if isinstance(obj, type) and isinstance(obj, TriggerMeta):
                if obj not in registered_classes:
                    registered_classes.add(obj)
                    mcs._register_triggers_for_class(obj)


class Trigger(metaclass=TriggerMeta):
    """
    Base class for trigger handlers.
    
    Triggers are registered via the @trigger decorator and executed by
    the TriggerDispatcher. This class serves as a base for all trigger
    handlers and uses TriggerMeta for automatic registration.
    
    All trigger execution logic has been moved to TriggerDispatcher for
    a single, consistent execution path.
    """
    pass
