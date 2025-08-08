import logging
import threading
from collections import deque
from itertools import zip_longest

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


def get_handler_cache():
    """Thread-local cache for handler instances, scoped per outermost run."""
    if not hasattr(_hook_context, "handler_cache"):
        _hook_context.handler_cache = {}
    return _hook_context.handler_cache


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


Hook = HookContextState()


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

        if len(queue) > 1:
            return  # nested call, will be processed by outermost

        # only outermost handle will process the queue
        # initialize a fresh handler cache for this run
        _hook_context.handler_cache = {}
        while queue:
            cls_, event_, model_, new_, old_, kw_ = queue.popleft()
            cls_._process(event_, model_, new_, old_, **kw_)

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

        # Hooks are already kept sorted by priority in the registry
        hooks = get_hooks(model, event)

        def _execute():
            new_local = new_records or []
            old_local = old_records or []
            cache = get_handler_cache()

            for handler_cls, method_name, condition, priority in hooks:
                # If there's no condition, pass through all records fast
                if condition is None:
                    handler = cache.get(handler_cls)
                    if handler is None:
                        handler = handler_cls()
                        cache[handler_cls] = handler
                    method = getattr(handler, method_name)
                    try:
                        method(
                            new_records=new_local,
                            old_records=old_local,
                            **kwargs,
                        )
                    except Exception:
                        logger.exception(
                            "Error in hook %s.%s", handler_cls.__name__, method_name
                        )
                    continue

                # Filter matching records without allocating full boolean list
                to_process_new = []
                to_process_old = []
                for n, o in zip_longest(new_local, old_local, fillvalue=None):
                    if n is None:
                        continue
                    if condition.check(n, o):
                        to_process_new.append(n)
                        to_process_old.append(o)

                if not to_process_new:
                    continue

                handler = cache.get(handler_cls)
                if handler is None:
                    handler = handler_cls()
                    cache[handler_cls] = handler
                method = getattr(handler, method_name)
                try:
                    method(
                        new_records=to_process_new,
                        old_records=to_process_old,
                        **kwargs,
                    )
                except Exception:
                    logger.exception(
                        "Error in hook %s.%s", handler_cls.__name__, method_name
                    )

        conn = transaction.get_connection()
        try:
            if conn.in_atomic_block and event.startswith("after_"):
                transaction.on_commit(_execute)
            else:
                _execute()
        finally:
            hook_vars.new = None
            hook_vars.old = None
            hook_vars.event = None
            hook_vars.model = None
            hook_vars.depth -= 1
            # Clear cache only when queue is empty (outermost completion)
            if not get_hook_queue():
                if hasattr(_hook_context, "handler_cache"):
                    _hook_context.handler_cache.clear()
