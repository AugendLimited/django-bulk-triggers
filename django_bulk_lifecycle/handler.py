from django_bulk_lifecycle.registry import get_hooks, register_hook


class TriggerHandlerMeta(type):
    def __new__(cls, name, bases, dct):
        for attr in dct.values():
            if hasattr(attr, "lifecycle_hook"):
                model_cls, event, condition, priority = attr.lifecycle_hook
                register_hook(model_cls, event, attr, condition, priority)
        return super().__new__(cls, name, bases, dct)


class TriggerHandler(metaclass=TriggerHandlerMeta):
    @classmethod
    def handle(
        cls,
        event: str,
        model: type,
        *,
        new_records: list = None,
        old_records: list = None,
        **kwargs,
    ) -> None:
        """
        Dispatch all registered hooks for (model, event), in priority order,
        passing along new_records/old_records and any extra kwargs.
        """
        hooks = get_hooks(model, event)
        for func, condition, priority in hooks:
            if condition is None or condition(
                new_records=new_records, old_records=old_records
            ):
                func(new_records=new_records, old_records=old_records, **kwargs)
