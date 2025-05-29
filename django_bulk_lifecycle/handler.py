from django_bulk_lifecycle.conditions import HookCondition
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
        for handler_cls, method_name, condition, priority in get_hooks(model, event):

            # --- condition check: run per-instance if it's a HookCondition ---
            if condition is not None:
                if isinstance(condition, HookCondition):
                    # zip old & new (old_records may be None for inserts)
                    pairs = zip(new_records or [], old_records or [])
                    # only proceed if *any* instance satisfies the condition
                    if not any(condition.check(new, old) for new, old in pairs):
                        continue
                else:
                    # legacy: a plain callable that expects the full lists
                    if not condition(new_records=new_records, old_records=old_records):
                        continue

            # instantiate your DI-wired handler
            handler = handler_cls()
            method  = getattr(handler, method_name)
            method(new_records=new_records, old_records=old_records, **kwargs)
