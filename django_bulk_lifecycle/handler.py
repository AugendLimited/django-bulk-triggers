from django_bulk_lifecycle.conditions import HookCondition
from django_bulk_lifecycle.registry import get_hooks, register_hook
import logging

logger = logging.getLogger(__name__)


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
                logger.debug(
                    "Registered hook %s.%s → %s.%s (cond=%r, prio=%s)",
                    model_cls.__name__,
                    event,
                    cls.__name__,
                    method_name,
                    condition,
                    priority,
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
        # Ensure new_records is a list
        new_records = new_records or []

        # Normalize old_records: ensure list and pad with None to match new_records length
        if old_records:
            old_records = list(old_records)
        else:
            old_records = []
        if len(old_records) < len(new_records):
            old_records += [None] * (len(new_records) - len(old_records))

        logger.debug(
            "ℹ️  bulk_lifecycle.handle() start: model=%s event=%s new_count=%d old_count=%d",
            model.__name__,
            event,
            len(new_records),
            len(old_records),
        )

        for handler_cls, method_name, condition, priority in get_hooks(model, event):
            logger.debug(
                "→ evaluating hook %s.%s (cond=%r, prio=%s)",
                handler_cls.__name__,
                method_name,
                condition,
                priority,
            )

            passed = True
            if condition is not None:
                if isinstance(condition, HookCondition):
                    # Dump condition internals
                    try:
                        cond_info = condition.__dict__
                    except Exception:
                        cond_info = str(condition)
                    logger.debug(
                        "   [cond-info] %s.%s → %r",
                        handler_cls.__name__,
                        method_name,
                        cond_info,
                    )

                    checks = []
                    for new, old in zip(new_records, old_records):
                        # Peek at the watched field and expected value
                        watched_field = getattr(condition, "field", None) or getattr(
                            condition, "field_name", None
                        )
                        actual_val = getattr(new, watched_field, None)
                        expected = getattr(
                            condition, "expected_value", None
                        ) or getattr(condition, "value", None)
                        logger.debug(
                            "   [field-lookup] %s.%s → field=%r actual=%r expected=%r",
                            handler_cls.__name__,
                            method_name,
                            watched_field,
                            actual_val,
                            expected,
                        )

                        result = condition.check(new, old)
                        checks.append(result)
                        logger.debug(
                            "   [cond-check] %s.%s → new=%r old=%r => %s",
                            handler_cls.__name__,
                            method_name,
                            new,
                            old,
                            result,
                        )
                    passed = any(checks)
                    logger.debug(
                        "   [cond-summary] %s.%s any-passed=%s",
                        handler_cls.__name__,
                        method_name,
                        passed,
                    )
                else:
                    passed = condition(new_records=new_records, old_records=old_records)
                    logger.debug(
                        "   [legacy-cond] %s.%s → full-list => %s",
                        handler_cls.__name__,
                        method_name,
                        passed,
                    )

            if not passed:
                logger.debug(
                    "↳ skipping %s.%s (condition not met)",
                    handler_cls.__name__,
                    method_name,
                )
                continue

            # Instantiate and invoke handler
            handler = handler_cls()
            method = getattr(handler, method_name)
            logger.info(
                "✨ invoking %s.%s on %d record(s)",
                handler_cls.__name__,
                method_name,
                len(new_records),
            )
            try:
                method(new_records=new_records, old_records=old_records, **kwargs)
            except Exception:
                logger.exception(
                    "❌ exception in %s.%s",
                    handler_cls.__name__,
                    method_name,
                )

        logger.debug(
            "✔️  bulk_lifecycle.handle() complete for %s.%s",
            model.__name__,
            event,
        )
