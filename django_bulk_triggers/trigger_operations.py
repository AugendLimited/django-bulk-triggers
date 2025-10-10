"""
Trigger execution operations for TriggerQuerySetMixin.

This module contains trigger execution and context management methods
that were extracted from queryset.py for better maintainability and testing.
"""

import logging

from django_bulk_triggers import engine
from django_bulk_triggers.constants import (
    AFTER_DELETE,
    BEFORE_DELETE,
    VALIDATE_DELETE,
)

logger = logging.getLogger(__name__)


class TriggerOperationsMixin:
    """
    Mixin containing trigger execution and context management methods.

    This mixin provides functionality for:
    - Executing triggers around database operations
    - Managing trigger contexts
    - Special handling for delete operations with field caching
    """

    def _execute_triggers_with_operation(
        self,
        operation_func,
        validate_trigger,
        before_trigger,
        after_trigger,
        objs,
        originals=None,
        ctx=None,
        bypass_triggers=False,
        bypass_validation=False,
    ):
        """
        Execute the complete trigger lifecycle around a database operation.

        Args:
            operation_func (callable): The database operation to execute
            validate_trigger: Trigger constant for validation
            before_trigger: Trigger constant for before operation
            after_trigger: Trigger constant for after operation
            objs (list): Objects being operated on
            originals (list, optional): Original objects for comparison triggers
            ctx: Trigger context
            bypass_triggers (bool): Whether to skip triggers
            bypass_validation (bool): Whether to skip validation triggers

        Returns:
            The result of the database operation
        """
        model_cls = self.model

        # Run validation triggers first (if not bypassed)
        if not bypass_validation and validate_trigger:
            engine.run(model_cls, validate_trigger, objs, ctx=ctx)

        # Run before triggers (if not bypassed)
        if not bypass_triggers and before_trigger:
            engine.run(model_cls, before_trigger, objs, originals, ctx=ctx)

        # Execute the database operation
        result = operation_func()

        # Run after triggers (if not bypassed)
        if not bypass_triggers and after_trigger:
            engine.run(model_cls, after_trigger, objs, originals, ctx=ctx)

        return result

    def _execute_delete_triggers_with_operation(
        self,
        operation_func,
        objs,
        ctx=None,
        bypass_triggers=False,
        bypass_validation=False,
    ):
        """
        Execute triggers for delete operations with special field caching logic.
        
        Handles both simple models and Multi-Table Inheritance (MTI) models.
        For MTI models, triggers are fired for both the child and all parent models.

        Args:
            operation_func (callable): The delete operation to execute
            objs (list): Objects being deleted
            ctx: Trigger context
            bypass_triggers (bool): Whether to skip triggers
            bypass_validation (bool): Whether to skip validation triggers

        Returns:
            The result of the delete operation
        """
        model_cls = self.model

        # Check if this is an MTI model and get inheritance chain
        is_mti = self._is_multi_table_inheritance() if hasattr(self, '_is_multi_table_inheritance') else False
        inheritance_chain = []
        
        if is_mti:
            # Build inheritance chain from base to child
            inheritance_chain = self._get_inheritance_chain() if hasattr(self, '_get_inheritance_chain') else [model_cls]
            logger.debug(f"MTI delete detected for {model_cls.__name__}, chain: {[m.__name__ for m in inheritance_chain]}")

        # Run validation triggers first (if not bypassed)
        if not bypass_validation:
            engine.run(model_cls, VALIDATE_DELETE, objs, ctx=ctx)
            
            # For MTI, also run validation for parent models
            if is_mti:
                for parent_model in inheritance_chain[:-1]:  # Exclude the child model (last in chain)
                    from django_bulk_triggers.context import TriggerContext
                    parent_ctx = TriggerContext(parent_model)
                    engine.run(parent_model, VALIDATE_DELETE, objs, ctx=parent_ctx)

        # Run before triggers (if not bypassed)
        if not bypass_triggers:
            engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)
            
            # For MTI, also run before triggers for parent models
            if is_mti:
                for parent_model in inheritance_chain[:-1]:  # Exclude the child model (last in chain)
                    from django_bulk_triggers.context import TriggerContext
                    parent_ctx = TriggerContext(parent_model)
                    engine.run(parent_model, BEFORE_DELETE, objs, ctx=parent_ctx)

            # Before deletion, ensure all related fields are properly cached
            # to avoid DoesNotExist errors in AFTER_DELETE triggers
            for obj in objs:
                if obj.pk is not None:
                    # Cache all foreign key relationships by accessing them
                    for field in model_cls._meta.fields:
                        if (
                            field.is_relation
                            and not field.many_to_many
                            and not field.one_to_many
                        ):
                            try:
                                # Access the related field to cache it before deletion
                                getattr(obj, field.name)
                            except Exception:
                                # If we can't access the field (e.g., already deleted, no permission, etc.)
                                # continue with other fields
                                pass

        # Execute the database operation
        result = operation_func()

        # Run after triggers (if not bypassed)
        if not bypass_triggers:
            engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)
            
            # For MTI, also run after triggers for parent models
            if is_mti:
                for parent_model in inheritance_chain[:-1]:  # Exclude the child model (last in chain)
                    from django_bulk_triggers.context import TriggerContext
                    parent_ctx = TriggerContext(parent_model)
                    engine.run(parent_model, AFTER_DELETE, objs, ctx=parent_ctx)

        return result
