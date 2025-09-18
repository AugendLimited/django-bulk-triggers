from django.db import models
from django_bulk_signals.manager import BulkSignalManager


class BulkSignalModelMixin(models.Model):
    objects = BulkSignalManager()

    class Meta:
        abstract = True

    def save(self, *args, skip_signals=False, **kwargs):
        if skip_signals:
            return super().save(*args, **kwargs)

        if self.pk is None:
            self.objects.bulk_create([self])
        else:
            self.objects.bulk_update([self])

    def delete(self, *args, skip_signals=False, **kwargs):
        if skip_signals:
            return super().delete(*args, **kwargs)

        if self.pk is None:
            self.objects.bulk_delete([self])
        else:
            self.objects.bulk_delete([self])
