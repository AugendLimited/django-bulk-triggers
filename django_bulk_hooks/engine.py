import logging
import os
import time

from django.core.exceptions import ValidationError

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


_PROFILE_ENABLED = bool(
    int(os.getenv("DJANGO_BULK_HOOKS_PROFILE", os.getenv("BULK_HOOKS_PROFILE", "0")))
)


def _log_profile(message: str) -> None:
    if _PROFILE_ENABLED:
        print(f"[bulk_hooks.profile] {message}", flush=True)


def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    Run hooks for a given model, event, and records.
    """
    if not new_records:
        return

    # Get hooks for this model and event
    t0 = time.perf_counter() if _PROFILE_ENABLED else None
    hooks = get_hooks(model_cls, event)
    if _PROFILE_ENABLED:
        _log_profile(
            f"engine.get_hooks model={model_cls.__name__} event={event} took {(time.perf_counter()-t0)*1000:.2f}ms"
        )

    if not hooks:
        return

    # For BEFORE_* events, run model.clean() first for validation
    if event.startswith("before_"):
        t_clean = time.perf_counter() if _PROFILE_ENABLED else None
        for instance in new_records:
            try:
                instance.clean()
            except ValidationError as e:
                logger.error("Validation failed for %s: %s", instance, e)
                raise
        if _PROFILE_ENABLED:
            _log_profile(
                f"engine.model_clean model={model_cls.__name__} event={event} n={len(new_records)} took {(time.perf_counter()-t_clean)*1000:.2f}ms"
            )

    # Process hooks
    t_hooks_total = time.perf_counter() if _PROFILE_ENABLED else None
    for handler_cls, method_name, condition, priority in hooks:
        handler_instance = handler_cls()
        func = getattr(handler_instance, method_name)

        to_process_new = []
        to_process_old = []

        t_select = time.perf_counter() if _PROFILE_ENABLED else None
        for new, original in zip(
            new_records,
            old_records or [None] * len(new_records),
            strict=True,
        ):
            if not condition or condition.check(new, original):
                to_process_new.append(new)
                to_process_old.append(original)
        if _PROFILE_ENABLED:
            _log_profile(
                f"engine.select_records handler={handler_cls.__name__}.{method_name} event={event} n={len(new_records)} selected={len(to_process_new)} took {(time.perf_counter()-t_select)*1000:.2f}ms"
            )

        if to_process_new:
            try:
                t_handler = time.perf_counter() if _PROFILE_ENABLED else None
                func(
                    new_records=to_process_new,
                    old_records=to_process_old if any(to_process_old) else None,
                )
                if _PROFILE_ENABLED:
                    _log_profile(
                        f"engine.handler handler={handler_cls.__name__}.{method_name} event={event} n={len(to_process_new)} took {(time.perf_counter()-t_handler)*1000:.2f}ms"
                    )
            except Exception as e:
                raise

    if _PROFILE_ENABLED:
        _log_profile(
            f"engine.run model={model_cls.__name__} event={event} n={len(new_records)} took {(time.perf_counter()-t_hooks_total)*1000:.2f}ms (handlers only)"
        )
