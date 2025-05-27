from django.db import models

from django_bulk_lifecycle import engine
from django_bulk_lifecycle.constants import AFTER_INSERT, AFTER_UPDATE
from django_bulk_lifecycle.context import TriggerContext

class BulkLifecycleManager(models.Manager):
    def bulk_update(self, objs, fields, batch_size=None, bypass_hooks=False):
        if not objs:
            return []

        model_cls = self.model
        if not bypass_hooks:
            originals = list(model_cls.objects.filter(pk__in=[obj.pk for obj in objs]))

        result = super().bulk_update(objs, fields, batch_size=batch_size)

        if not bypass_hooks:
            ctx = TriggerContext(model_cls)
            engine.run(model_cls, AFTER_UPDATE, objs, originals, ctx=ctx)

        return result

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, bypass_hooks=False):
        model_cls = self.model
        result = super().bulk_create(objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts)

        if not bypass_hooks:
            ctx = TriggerContext(model_cls)
            engine.run(model_cls, AFTER_INSERT, result, ctx=ctx)

        return result