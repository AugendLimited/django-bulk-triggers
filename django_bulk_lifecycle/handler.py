from django_bulk_lifecycle.registry import register_hook


class TriggerHandlerMeta(type):
    def __new__(cls, name, bases, dct):
        for attr in dct.values():
            if hasattr(attr, "lifecycle_hook"):
                model_cls, event, condition, priority = attr.lifecycle_hook
                register_hook(model_cls, event, attr, condition, priority)
        return super().__new__(cls, name, bases, dct)


class TriggerHandler(metaclass=TriggerHandlerMeta):
    pass
