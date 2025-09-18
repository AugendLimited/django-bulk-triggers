import logging

from django.db import models, transaction

from django_bulk_triggers.bulk_operations import BulkOperationsMixin
from django_bulk_triggers.core import TriggerEngine
from django_bulk_triggers.field_operations import FieldOperationsMixin
from django_bulk_triggers.mti_operations import MTIOperationsMixin
from django_bulk_triggers.trigger_operations import TriggerOperationsMixin
from django_bulk_triggers.validation_operations import ValidationOperationsMixin

logger = logging.getLogger(__name__)


class TriggerQuerySetMixin(
    BulkOperationsMixin,
    FieldOperationsMixin,
    MTIOperationsMixin,
    TriggerOperationsMixin,
    ValidationOperationsMixin,
):
    """
    A mixin that provides bulk trigger functionality to any QuerySet.
    This can be dynamically injected into querysets from other managers.
    """
    
    @property
    def trigger_engine(self):
        """Get the TriggerEngine instance for this queryset's model."""
        if not hasattr(self, '_trigger_engine'):
            self._trigger_engine = TriggerEngine(self.model)
        return self._trigger_engine

    @transaction.atomic
    def delete(self):
        objs = list(self)
        if not objs:
            return 0

        # Use TriggerEngine to handle all trigger execution
        def delete_operation():
            return super().delete()
        
        return self.trigger_engine.execute_delete_triggers(objs, delete_operation)

    @transaction.atomic
    def update(self, **kwargs):
        """
        Update QuerySet with trigger support.
        This method handles Subquery objects and complex expressions properly.
        """
        instances = list(self)
        if not instances:
            return 0

        # Use TriggerEngine to handle all trigger execution and complex update logic
        def update_operation(**update_kwargs):
            return super().update(**update_kwargs)
        
        return self.trigger_engine.execute_update_triggers(instances, update_operation, **kwargs)


class TriggerQuerySet(TriggerQuerySetMixin, models.QuerySet):
    """
    A QuerySet that provides bulk trigger functionality.
    This is the traditional approach for backward compatibility.
    """

    pass
