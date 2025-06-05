from django.db import models, transaction
from django.db.models.manager import BaseManager


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

        BaseManager.bulk_update(
            self.model._base_manager,
            instances,
            fields=list(kwargs.keys()),
        )

        return len(instances)
