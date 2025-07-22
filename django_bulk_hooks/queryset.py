from django.db import models, transaction
from django_bulk_hooks.context import is_in_bulk_operation


class HookQuerySet(models.QuerySet):
    @transaction.atomic
    def delete(self):
        objs = list(self)
        if not objs:
            return 0
        return self.model.objects.bulk_delete(objs)

    @transaction.atomic
    def update(self, **kwargs):
        instances = list(self)
        if not instances:
            return 0

        model_cls = self.model
        pks = [obj.pk for obj in instances]

        # Load originals for hook comparison
        originals = list(model_cls.objects.filter(pk__in=pks))
        originals_by_pk = {obj.pk: obj for obj in originals}

        # Apply field updates to instances
        for obj in instances:
            for field, value in kwargs.items():
                setattr(obj, field, value)

        # Run BEFORE_UPDATE hooks
        from django_bulk_hooks import engine
        from django_bulk_hooks.context import HookContext

        ctx = HookContext(model_cls)
        engine.run(model_cls, "before_update", instances, originals, ctx=ctx)

        # Use Django's built-in update logic directly
        # Set flag to prevent recursion during the actual update
        from django_bulk_hooks.context import set_bulk_operation_flag
        set_bulk_operation_flag(True)
        try:
            queryset = self.model.objects.filter(pk__in=pks)
            update_count = queryset.update(**kwargs)
        finally:
            set_bulk_operation_flag(False)

        # Run AFTER_UPDATE hooks
        engine.run(model_cls, "after_update", instances, originals, ctx=ctx)

        return update_count
