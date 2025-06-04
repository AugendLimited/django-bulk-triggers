from django_bulk_lifecycle.registry import get_hooks
import logging

logger = logging.getLogger(__name__)


def run(model_cls, event, new_instances, original_instances=None, ctx=None):
    hooks = get_hooks(model_cls, event)

    logger.debug(
        "bulk_lifecycle.run: model=%s, event=%s, #new=%d, #original=%d",
        model_cls.__name__,
        event,
        len(new_instances),
        len(original_instances or []),
    )

    for handler_cls, method_name, condition, priority in hooks:
        func = getattr(handler_cls(), method_name)

        logger.debug(
            "Executing hook %s for %s.%s", func.__name__, model_cls.__name__, event
        )

        to_process = []
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
                to_process.append(new)
                logger.debug("    -> will process (passed condition)")
            else:
                logger.debug("    -> skipped (condition returned False)")

        if to_process:
            logger.info(
                "Calling %s on %d instance(s): %r",
                func.__name__,
                len(to_process),
                to_process,
            )
            func(ctx, to_process)
        else:
            logger.debug("No instances to process for hook %s", func.__name__)
