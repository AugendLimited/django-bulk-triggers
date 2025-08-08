import logging
import os
import time
from itertools import repeat

from django.core.exceptions import ValidationError

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


_PROFILE_ENABLED = bool(
    int(os.getenv("DJANGO_BULK_HOOKS_PROFILE", os.getenv("BULK_HOOKS_PROFILE", "0")))
)
_PROFILE_MIN_MS = float(os.getenv("DJANGO_BULK_HOOKS_PROFILE_MIN_MS", "0"))


def _log_profile(message: str, duration_ms: float | None = None) -> None:
    if not _PROFILE_ENABLED:
        return
    if duration_ms is not None and duration_ms < _PROFILE_MIN_MS:
        return
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
        dt = (time.perf_counter() - t0) * 1000 if t0 is not None else 0.0
        _log_profile(
            f"engine.get_hooks model={model_cls.__name__} event={event} took {dt:.2f}ms",
            dt,
        )

    if not hooks:
        return

    # For BEFORE_* events, run model.clean() first for validation
    if event.startswith("before_") and not getattr(ctx, "skip_model_clean", False):
        t_clean = time.perf_counter() if _PROFILE_ENABLED else None
        for instance in new_records:
            try:
                instance.clean()
            except ValidationError as e:
                logger.error("Validation failed for %s: %s", instance, e)
                raise
        if _PROFILE_ENABLED:
            dt = (time.perf_counter() - t_clean) * 1000 if t_clean is not None else 0.0
            _log_profile(
                f"engine.model_clean model={model_cls.__name__} event={event} n={len(new_records)} took {dt:.2f}ms",
                dt,
            )

    # Process hooks
    t_hooks_total = time.perf_counter() if _PROFILE_ENABLED else None
    for handler_cls, method_name, condition, priority in hooks:
        handler_instance = handler_cls()
        func = getattr(handler_instance, method_name)

        # Fast path: if no condition, pass-through all records
        if not condition:
            try:
                t_handler = time.perf_counter() if _PROFILE_ENABLED else None
                func(
                    new_records=new_records,
                    old_records=old_records if old_records and any(old_records) else None,
                )
                if _PROFILE_ENABLED:
                    dt = (time.perf_counter() - t_handler) * 1000 if t_handler is not None else 0.0
                    _log_profile(
                        f"engine.handler handler={handler_cls.__name__}.{method_name} event={event} n={len(new_records)} took {dt:.2f}ms",
                        dt,
                    )
            except Exception:
                raise
            continue

        # Conditional path: select matching records
        to_process_new = []
        to_process_old = []

        t_select = time.perf_counter() if _PROFILE_ENABLED else None
        for new, original in zip(
            new_records,
            old_records if old_records is not None else repeat(None),
        ):
            if condition.check(new, original):
                to_process_new.append(new)
                to_process_old.append(original)
        if _PROFILE_ENABLED:
            dt = (time.perf_counter() - t_select) * 1000 if t_select is not None else 0.0
            _log_profile(
                f"engine.select_records handler={handler_cls.__name__}.{method_name} event={event} n={len(new_records)} selected={len(to_process_new)} took {dt:.2f}ms",
                dt,
            )

        if to_process_new:
            try:
                t_handler = time.perf_counter() if _PROFILE_ENABLED else None
                func(
                    new_records=to_process_new,
                    old_records=to_process_old if any(to_process_old) else None,
                )
                if _PROFILE_ENABLED:
                    dt = (time.perf_counter() - t_handler) * 1000 if t_handler is not None else 0.0
                    _log_profile(
                        f"engine.handler handler={handler_cls.__name__}.{method_name} event={event} n={len(to_process_new)} took {dt:.2f}ms",
                        dt,
                    )
            except Exception:
                raise

    if _PROFILE_ENABLED:
        dt = (time.perf_counter() - t_hooks_total) * 1000 if t_hooks_total is not None else 0.0
        _log_profile(
            f"engine.run model={model_cls.__name__} event={event} n={len(new_records)} took {dt:.2f}ms (handlers only)",
            dt,
        )
