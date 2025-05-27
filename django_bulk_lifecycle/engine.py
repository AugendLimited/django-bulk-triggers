from registry import get_hooks


def run(model_cls, event, new_instances, original_instances=None, ctx=None):
    hooks = get_hooks(model_cls, event)
    for func, condition in hooks:
        to_process = []
        for new, original in zip(
            new_instances, original_instances or [None] * len(new_instances)
        ):
            if not condition or condition.check(new, original):
                to_process.append(new)
        if to_process:
            func(ctx, to_process)
