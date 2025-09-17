"""
Validation and setup operations for TriggerQuerySetMixin.

This module contains validation, setup, and utility methods that were extracted
from queryset.py for better maintainability and testing.
"""

import logging

from django_bulk_triggers.context import TriggerContext

logger = logging.getLogger(__name__)


class ValidationOperationsMixin:
    """
    Mixin containing validation and setup methods for bulk operations.

    This mixin provides functionality for:
    - Validating objects for bulk operations
    - Setting up bulk operation contexts
    - Building value maps for triggers
    - Filtering Django kwargs
    - Logging bulk operations
    """

    def _validate_objects(self, objs, require_pks=False, operation_name="bulk_update"):
        """
        Validate that all objects are instances of this queryset's model.

        Args:
            objs (list): Objects to validate
            require_pks (bool): Whether to validate that objects have primary keys
            operation_name (str): Name of the operation for error messages
        """
        model_cls = self.model

        # Type check
        invalid_types = {
            type(obj).__name__ for obj in objs if not isinstance(obj, model_cls)
        }
        if invalid_types:
            raise TypeError(
                f"{operation_name} expected instances of {model_cls.__name__}, "
                f"but got {invalid_types}"
            )

        # Primary key check (optional, for operations that require saved objects)
        if require_pks:
            missing_pks = [obj for obj in objs if obj.pk is None]
            if missing_pks:
                raise ValueError(
                    f"{operation_name} cannot operate on unsaved {model_cls.__name__} instances. "
                    f"{len(missing_pks)} object(s) have no primary key."
                )

        logger.debug(
            "Validated %d %s objects for %s",
            len(objs),
            model_cls.__name__,
            operation_name,
        )

    def _setup_bulk_operation(
        self,
        objs,
        operation_name,
        require_pks=False,
        bypass_triggers=False,
        bypass_validation=False,
        **log_kwargs,
    ):
        """
        Common setup logic for bulk operations.

        Args:
            objs (list): Objects to operate on
            operation_name (str): Name of the operation for logging and validation
            require_pks (bool): Whether objects must have primary keys
            bypass_triggers (bool): Whether to bypass triggers
            bypass_validation (bool): Whether to bypass validation
            **log_kwargs: Additional parameters to log

        Returns:
            tuple: (model_cls, ctx, originals)
        """
        # Log operation start
        self._log_bulk_operation_start(operation_name, objs, **log_kwargs)

        # Validate objects
        self._validate_objects(
            objs, require_pks=require_pks, operation_name=operation_name
        )

        # Initialize trigger context
        ctx, originals = self._init_trigger_context(
            bypass_triggers, objs, operation_name
        )

        return self.model, ctx, originals

    def _init_trigger_context(
        self, bypass_triggers: bool, objs, operation_name="bulk_update"
    ):
        """
        Initialize the trigger context for bulk operations.

        Args:
            bypass_triggers (bool): Whether to bypass triggers
            objs (list): List of objects being operated on
            operation_name (str): Name of the operation for logging

        Returns:
            (TriggerContext, list): The trigger context and a placeholder list
            for 'originals', which can be populated later if needed for
            after_update triggers.
        """
        model_cls = self.model

        if bypass_triggers:
            logger.debug(
                "%s: triggers bypassed for %s", operation_name, model_cls.__name__
            )
            ctx = TriggerContext(model_cls, bypass_triggers=True)
        else:
            logger.debug(
                "%s: triggers enabled for %s", operation_name, model_cls.__name__
            )
            ctx = TriggerContext(model_cls, bypass_triggers=False)

        # Keep `originals` aligned with objs to support later trigger execution.
        originals = [None] * len(objs)

        return ctx, originals

    def _build_value_map(self, objs, fields_set, auto_now_fields):
        """
        Build a mapping of {pk -> {field_name: raw_value}} for trigger processing.

        Expressions are not included; only concrete values assigned on the object.
        """
        value_map = {}
        logger.debug(
            "DEBUG: Building value_map for %d objects with fields: %s",
            len(objs),
            list(fields_set),
        )

        for obj in objs:
            if obj.pk is None:
                logger.debug("DEBUG: Skipping object with no pk")
                continue  # skip unsaved objects
            field_values = {}
            logger.debug("DEBUG: Processing object pk=%s", obj.pk)

            for field_name in fields_set:
                value = getattr(obj, field_name)
                field_values[field_name] = value
                logger.debug(
                    "DEBUG: Object %s field %s = %s (type: %s)",
                    obj.pk,
                    field_name,
                    value,
                    type(value).__name__,
                )

                if field_name in auto_now_fields:
                    logger.debug("Object %s %s=%s", obj.pk, field_name, value)

            if field_values:
                value_map[obj.pk] = field_values
                logger.debug(
                    "DEBUG: Added value_map entry for pk=%s with %d fields",
                    obj.pk,
                    len(field_values),
                )
            else:
                logger.debug("DEBUG: No field values for object pk=%s", obj.pk)

        logger.debug("Built value_map for %d objects", len(value_map))
        logger.debug("DEBUG: Final value_map keys: %s", list(value_map.keys()))
        for pk, values in value_map.items():
            logger.debug("DEBUG: value_map[%s] = %s", pk, list(values.keys()))
        return value_map

    def _filter_django_kwargs(self, kwargs):
        """
        Remove unsupported arguments before passing to Django's bulk_update.
        """
        unsupported = {
            "unique_fields",
            "update_conflicts",
            "update_fields",
            "ignore_conflicts",
        }
        passthrough = {}
        for k, v in kwargs.items():
            if k in unsupported:
                logger.warning(
                    f"Parameter '{k}' is not supported for the current operation. "
                    f"It will be ignored."
                )
            else:
                passthrough[k] = v
        return passthrough

    def _log_bulk_operation_start(self, operation_name, objs, **kwargs):
        """
        Log the start of a bulk operation with consistent formatting.

        Args:
            operation_name (str): Name of the operation (e.g., "bulk_create")
            objs (list): Objects being operated on
            **kwargs: Additional parameters to log
        """
        model_cls = self.model

        # Build parameter string for additional kwargs
        param_str = ""
        if kwargs:
            param_parts = []
            for key, value in kwargs.items():
                if isinstance(value, (list, tuple)):
                    param_parts.append(f"{key}={value}")
                else:
                    param_parts.append(f"{key}={value}")
            param_str = f", {', '.join(param_parts)}"

        logger.debug(
            f"{operation_name} called for {model_cls.__name__} with {len(objs)} objects{param_str}"
        )
