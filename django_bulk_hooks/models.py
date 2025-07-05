from django.db import models, transaction

from django_bulk_hooks.manager import BulkHookManager


class HookModelMixin(models.Model):
    objects = BulkHookManager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        self.before_delete()

        with transaction.atomic():
            result = super().delete(*args, **kwargs)

        self.after_delete()

        return result

    def before_delete(self):
        pass

    def after_delete(self):
        pass
