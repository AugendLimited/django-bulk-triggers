import logging
import threading
from collections import deque

from django.db import transaction

from django_bulk_triggers.registry import get_triggers, register_trigger

logger = logging.getLogger(__name__)


# Thread-local trigger context and trigger state
class TriggerVars(threading.local):
    def __init__(self):
        self.new = None
        self.old = None
        self.event = None
        self.model = None
        self.depth = 0


trigger_vars = TriggerVars()

# Trigger queue per thread
_trigger_context = threading.local()


def get_trigger_queue():
    if not hasattr(_trigger_context, "queue"):
        _trigger_context.queue = deque()
    return _trigger_context.queue


class TriggerContextState:
    @property
    def is_before(self):
        return trigger_vars.event.startswith("before_") if trigger_vars.event else False

    @property
    def is_after(self):
        return trigger_vars.event.startswith("after_") if trigger_vars.event else False

    @property
    def is_create(self):
        return "create" in trigger_vars.event if trigger_vars.event else False

    @property
    def is_update(self):
        return "update" in trigger_vars.event if trigger_vars.event else False

    @property
    def new(self):
        return trigger_vars.new

    @property
    def old(self):
        return trigger_vars.old

    @property
    def model(self):
        return trigger_vars.model


TriggerContext = TriggerContextState()


class TriggerMeta(type):
    _registered = set()

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        for method_name, method in namespace.items():
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
        return cls


class Trigger(metaclass=TriggerMeta):
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
        queue = get_trigger_queue()
        queue.append((cls, event, model, new_records, old_records, kwargs))
        logger.debug(f"Added item to queue: {event}")

        # Process the entire queue immediately - no depth checking
        logger.debug(f"Processing queue with {len(queue)} items")
        while queue:
            item = queue.popleft()
            if len(item) == 6:
                cls_, event_, model_, new_, old_, kw_ = item
                logger.debug(f"Processing queue item: {event_}")
                # Call _process on the Trigger class, not the calling class
                Trigger._process(event_, model_, new_, old_, **kw_)
            else:
                logger.warning(f"Invalid queue item format: {item}")
                continue

    @classmethod
    def _process(
        cls,
        event,
        model,
        new_records,
        old_records,
        **kwargs,
    ):
        # Remove depth tracking - let Django handle recursion
        trigger_vars.new = new_records
        trigger_vars.old = old_records
        trigger_vars.event = event
        trigger_vars.model = model

        triggers = sorted(get_triggers(model, event), key=lambda x: x[3])
        logger.debug(f"Found {len(triggers)} triggers for {event}")

        def _execute():
            logger.debug(f"Executing {len(triggers)} triggers for {event}")
            new_local = new_records or []
            old_local = old_records or []
            if len(old_local) < len(new_local):
                old_local += [None] * (len(new_local) - len(old_local))

            for handler_cls, method_name, condition, priority in triggers:
                logger.debug(f"Processing trigger {handler_cls.__name__}.{method_name}")
                if condition is not None:
                    checks = [
                        condition.check(n, o) for n, o in zip(new_local, old_local)
                    ]
                    if not any(checks):
                        logger.debug(
                            f"Condition failed for {handler_cls.__name__}.{method_name}"
                        )
                        continue

                handler = handler_cls()
                method = getattr(handler, method_name)
                logger.debug(f"Executing {handler_cls.__name__}.{method_name}")

                try:
                    method(
                        new_records=new_local,
                        old_records=old_local,
                        **kwargs,
                    )
                    logger.debug(
                        f"Successfully executed {handler_cls.__name__}.{method_name}"
                    )
                except Exception:
                    logger.exception(
                        "Error in trigger %s.%s", handler_cls.__name__, method_name
                    )
                    # Re-raise the exception to ensure transaction rollback like Salesforce
                    raise

        conn = transaction.get_connection()
        logger.debug(
            f"Transaction in_atomic_block: {conn.in_atomic_block}, event: {event}"
        )
        try:
            # For Salesforce-like behavior, execute all triggers within the same transaction
            # This ensures that if any trigger fails, the entire transaction rolls back
            logger.debug(f"Executing {event} immediately within transaction")
            logger.debug(f"DEBUG: Handler executing {event} immediately within transaction")
            _execute()
        finally:
            trigger_vars.new = None
            trigger_vars.old = None
            trigger_vars.event = None
            trigger_vars.model = None
            # Remove depth decrement - let Django handle recursion
