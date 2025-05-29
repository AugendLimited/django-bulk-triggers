from django_bulk_lifecycle.registry import get_hooks, register_hook


class TriggerHandlerMeta(type):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        for method_name, method in namespace.items():
            if hasattr(method, "lifecycle_hook"):
                model_cls, event, condition, priority = method.lifecycle_hook

                register_hook(
                    model=model_cls,
                    event=event,
                    handler_cls=cls,
                    method_name=method_name,
                    condition=condition,
                    priority=priority,
                )
        return cls


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
        Dispatch all registered hooks for (model, event),
        instantiating each handler via its DI-wired __init__.
        """
        for handler_cls, method_name, condition, priority in get_hooks(model, event):
            if condition is not None and not condition(
                new_records=new_records, old_records=old_records
            ):
                continue

            handler: TriggerHandler = handler_cls()

            bound = getattr(handler, method_name)

            bound(new_records=new_records, old_records=old_records, **kwargs)
