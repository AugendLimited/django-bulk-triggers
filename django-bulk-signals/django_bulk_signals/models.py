from django.db import models

from django_bulk_signals.manager import BulkSignalManager


class BulkSignalModel(models.Model):
    objects = BulkSignalManager()

    class Meta:
        abstract = True

    def save(self, *args, skip_signals=False, **kwargs):
        if skip_signals:
            return super().save(*args, **kwargs)

        if self.pk is None:
            self.__class__.objects.bulk_create([self])
        else:
            # Use automatic field detection for single object updates
            self.__class__.objects.bulk_update([self])

    def delete(self, *args, skip_signals=False, **kwargs):
        if skip_signals:
            return super().delete(*args, **kwargs)

        if self.pk is None:
            self.__class__.objects.bulk_delete([self])
        else:
            self.__class__.objects.bulk_delete([self])
