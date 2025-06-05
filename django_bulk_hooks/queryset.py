from django.db import models, transaction


class LifecycleQuerySet(models.QuerySet):
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

        for obj in instances:
            for field, value in kwargs.items():
                setattr(obj, field, value)

        # Bypass manager to avoid recursive call to hooks
        from django.db.models import Model
        Model.objects.bulk_update(instances, fields=list(kwargs.keys()))
        return len(instances)
