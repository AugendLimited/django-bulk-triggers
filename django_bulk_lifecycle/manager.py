from django.db import transaction
from django_lifecycle import AFTER_DELETE
from django_lifecycle import BEFORE_DELETE
from django_lifecycle import BEFORE_UPDATE
from queryable_properties.managers import QueryablePropertiesManager

from . import engine
from .constants import AFTER_INSERT
from .constants import AFTER_UPDATE
from .constants import BEFORE_INSERT
from .context import TriggerContext


class BulkLifecycleManager(QueryablePropertiesManager):
    CHUNK_SIZE = 200

    @transaction.atomic
    def bulk_update(self, objs, fields, batch_size=None, bypass_hooks=False):
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(f"bulk_update expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}")

        if not bypass_hooks:
            originals = list(model_cls.objects.filter(pk__in=[obj.pk for obj in objs]))
            ctx = TriggerContext(model_cls)
            engine.run(model_cls, BEFORE_UPDATE, objs, originals, ctx=ctx)

        for i in range(0, len(objs), self.CHUNK_SIZE):
            chunk = objs[i : i + self.CHUNK_SIZE]
            super().bulk_update(chunk, fields, batch_size=batch_size)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_UPDATE, objs, originals, ctx=ctx)

        return objs

    @transaction.atomic
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, bypass_hooks=False):
        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}")

        result = []

        if not bypass_hooks:
            ctx = TriggerContext(model_cls)
            engine.run(model_cls, BEFORE_INSERT, objs, ctx=ctx)

        for i in range(0, len(objs), self.CHUNK_SIZE):
            chunk = objs[i : i + self.CHUNK_SIZE]
            result.extend(super().bulk_create(chunk, batch_size=batch_size, ignore_conflicts=ignore_conflicts))

        if not bypass_hooks:
            engine.run(model_cls, AFTER_INSERT, result, ctx=ctx)

        return result

    @transaction.atomic
    def bulk_delete(self, objs, batch_size=None, bypass_hooks=False):
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(f"bulk_delete expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}")

        ctx = TriggerContext(model_cls)

        if not bypass_hooks:
            engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)

        pks = [obj.pk for obj in objs if obj.pk is not None]
        model_cls.objects.filter(pk__in=pks).delete()

        if not bypass_hooks:
            engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

        return objs

    @transaction.atomic
    def update(self, **kwargs):
        objs = list(self.all())
        if not objs:
            return 0
        for key, value in kwargs.items():
            for obj in objs:
                setattr(obj, key, value)
        self.bulk_update(objs, fields=list(kwargs.keys()))
        return len(objs)

    @transaction.atomic
    def delete(self):
        objs = list(self.all())
        if not objs:
            return 0
        self.model.objects.bulk_delete(objs)
        return len(objs)

    @transaction.atomic
    def save(self, obj):
        if obj.pk:
            self.bulk_update([obj], fields=[field.name for field in obj._meta.fields if field.name != "id"])
        else:
            self.bulk_create([obj])
        return obj
