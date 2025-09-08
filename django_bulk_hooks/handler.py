import logging
import threading
from collections import deque

from django.db import transaction

from django_bulk_hooks.registry import get_hooks, register_hook

logger = logging.getLogger(__name__)


# Thread-local hook context and hook state
class HookVars(threading.local):
    def __init__(self):
        self.new = None
        self.old = None
        self.event = None
        self.model = None
        self.depth = 0


hook_vars = HookVars()

# Hook queue per thread
_hook_context = threading.local()


def get_hook_queue():
    if not hasattr(_hook_context, "queue"):
        _hook_context.queue = deque()
    return _hook_context.queue


class HookContextState:
    @property
    def is_before(self):
        return hook_vars.event.startswith("before_") if hook_vars.event else False

    @property
    def is_after(self):
        return hook_vars.event.startswith("after_") if hook_vars.event else False

    @property
    def is_create(self):
        return "create" in hook_vars.event if hook_vars.event else False

    @property
    def is_update(self):
        return "update" in hook_vars.event if hook_vars.event else False

    @property
    def new(self):
        return hook_vars.new

    @property
    def old(self):
        return hook_vars.old

    @property
    def model(self):
        return hook_vars.model


HookContext = HookContextState()


class HookMeta(type):
    _registered = set()

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        for method_name, method in namespace.items():
            if hasattr(method, "hooks_hooks"):
                for model_cls, event, condition, priority in method.hooks_hooks:
                    key = (model_cls, event, cls, method_name)
                    if key not in HookMeta._registered:
                        register_hook(
                            model=model_cls,
                            event=event,
                            handler_cls=cls,
                            method_name=method_name,
                            condition=condition,
                            priority=priority,
                        )
                        HookMeta._registered.add(key)
        return cls


class Hook(metaclass=HookMeta):
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
        queue = get_hook_queue()
        queue.append((cls, event, model, new_records, old_records, kwargs))
        logger.debug(f"Added item to queue: {event}, depth: {hook_vars.depth}")

        # If we're already processing hooks (depth > 0), don't process the queue
        # The outermost call will process the entire queue
        if hook_vars.depth > 0:
            logger.debug(f"Depth > 0, returning without processing queue")
            return

        # Process the entire queue
        logger.debug(f"Processing queue with {len(queue)} items")
        while queue:
            item = queue.popleft()
            if len(item) == 6:
                cls_, event_, model_, new_, old_, kw_ = item
                logger.debug(f"Processing queue item: {event_}")
                # Call _process on the Hook class, not the calling class
                Hook._process(event_, model_, new_, old_, **kw_)
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
        hook_vars.depth += 1
        hook_vars.new = new_records
        hook_vars.old = old_records
        hook_vars.event = event
        hook_vars.model = model

        hooks = sorted(get_hooks(model, event), key=lambda x: x[3])
        logger.debug(f"Found {len(hooks)} hooks for {event}")

        def _execute():
            logger.debug(f"Executing {len(hooks)} hooks for {event}")
            new_local = new_records or []
            old_local = old_records or []
            if len(old_local) < len(new_local):
                old_local += [None] * (len(new_local) - len(old_local))

            for handler_cls, method_name, condition, priority in hooks:
                logger.debug(f"Processing hook {handler_cls.__name__}.{method_name}")
                if condition is not None:
                    checks = [
                        condition.check(n, o) for n, o in zip(new_local, old_local)
                    ]
                    if not any(checks):
                        logger.debug(f"Condition failed for {handler_cls.__name__}.{method_name}")
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
                    logger.debug(f"Successfully executed {handler_cls.__name__}.{method_name}")
                except Exception:
                    logger.exception(
                        "Error in hook %s.%s", handler_cls.__name__, method_name
                    )

        conn = transaction.get_connection()
        logger.debug(f"Transaction in_atomic_block: {conn.in_atomic_block}, event: {event}")
        try:
            if conn.in_atomic_block and event.startswith("after_"):
                logger.debug(f"Deferring {event} to on_commit")
                transaction.on_commit(_execute)
            else:
                logger.debug(f"Executing {event} immediately")
                _execute()
        finally:
            hook_vars.new = None
            hook_vars.old = None
            hook_vars.event = None
            hook_vars.model = None
            hook_vars.depth -= 1
