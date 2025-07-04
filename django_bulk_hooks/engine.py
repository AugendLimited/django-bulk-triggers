import logging

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


def run(model_cls, event, new_instances, original_instances=None, ctx=None):
    hooks = get_hooks(model_cls, event)

    logger.debug(
        "Executing engine.run: model=%s, event=%s, #new_instances=%d, #original_instances=%d",
        model_cls.__name__,
        event,
        len(new_instances),
        len(original_instances or []),
    )

    for handler_cls, method_name, condition, priority in hooks:
        handler_instance = handler_cls()
        func = getattr(handler_instance, method_name)

        logger.debug(
            "Executing hook %s for %s.%s with priority=%s",
            func.__name__,
            model_cls.__name__,
            event,
            priority,
        )

        to_process_new = []
        to_process_old = []

        for new, original in zip(
            new_instances,
            original_instances or [None] * len(new_instances),
            strict=True,
        ):
            logger.debug(
                "  considering instance: new=%r, original=%r",
                new,
                original,
            )

            if not condition or condition.check(new, original):
                to_process_new.append(new)
                to_process_old.append(original)
                logger.debug("    -> will process (passed condition)")
            else:
                logger.debug("    -> skipped (condition returned False)")

        if to_process_new:
            logger.info(
                "Calling %s on %d instance(s): %r",
                func.__name__,
                len(to_process_new),
                to_process_new,
            )

            # Call the function with direct arguments
            func(to_process_new, to_process_old if any(to_process_old) else None)
        else:
            logger.debug("No instances to process for hook %s", func.__name__)
