"""
Field operations for TriggerQuerySetMixin.

This module contains field detection, comparison, and manipulation methods
that were extracted from queryset.py for better maintainability and testing.
"""

import logging
from typing import List, Set, Tuple, Optional

logger = logging.getLogger(__name__)


class FieldOperationsMixin:
    """
    Mixin containing field detection and manipulation methods.

    This mixin provides functionality for:
    - Detecting changed fields between objects
    - Preparing fields for updates
    - Handling auto_now fields
    - Applying field transformations
    """

    def _detect_changed_fields(self, objs):
        """
        Auto-detect which fields have changed by comparing objects with database values.
        Returns a set of field names that have changed across all objects.
        """
        if not objs:
            return set()

        model_cls = self.model
        changed_fields = set()

        # Get primary key field names
        pk_fields = [f.name for f in model_cls._meta.pk_fields]
        if not pk_fields:
            pk_fields = ["pk"]

        # Get all object PKs
        obj_pks = []
        for obj in objs:
            if hasattr(obj, "pk") and obj.pk is not None:
                obj_pks.append(obj.pk)
            else:
                # Skip objects without PKs
                continue

        if not obj_pks:
            return set()

        # Fetch current database values for all objects
        existing_objs = {
            obj.pk: obj for obj in model_cls.objects.filter(pk__in=obj_pks)
        }

        # Compare each object's current values with database values
        for obj in objs:
            if obj.pk not in existing_objs:
                continue

            db_obj = existing_objs[obj.pk]

            # Check all concrete fields for changes
            for field in model_cls._meta.concrete_fields:
                field_name = field.name

                # Skip primary key fields
                if field_name in pk_fields:
                    continue

                # Get current value from object
                current_value = getattr(obj, field_name, None)
                # Get database value
                db_value = getattr(db_obj, field_name, None)

                # Compare values (handle None cases)
                if current_value != db_value:
                    changed_fields.add(field_name)

        return changed_fields

    def _prepare_update_fields(self, changed_fields):
        """
        Determine the final set of fields to update, including auto_now
        fields and custom fields that require pre_save() on updates.

        Args:
            changed_fields (Iterable[str]): Fields detected as changed.

        Returns:
            tuple:
                fields_set (set): All fields that should be updated.
                auto_now_fields (list[str]): Fields that require auto_now behavior.
                custom_update_fields (list[Field]): Fields with pre_save triggers to call.
        """
        model_cls = self.model
        fields_set = set(changed_fields)
        pk_field_names = [f.name for f in model_cls._meta.pk_fields]

        auto_now_fields = []
        custom_update_fields = []

        for field in model_cls._meta.local_concrete_fields:
            # Handle auto_now fields
            if getattr(field, "auto_now", False):
                if field.name not in fields_set and field.name not in pk_field_names:
                    fields_set.add(field.name)
                    if field.name != field.attname:  # handle attname vs name
                        fields_set.add(field.attname)
                    auto_now_fields.append(field.name)
                    logger.debug("Added auto_now field %s to update set", field.name)

            # Skip auto_now_add (only applies at creation time)
            elif getattr(field, "auto_now_add", False):
                continue

            # Handle custom pre_save fields
            elif hasattr(field, "pre_save"):
                if field.name not in fields_set and field.name not in pk_field_names:
                    custom_update_fields.append(field)
                    logger.debug(
                        "Marked custom field %s for pre_save update", field.name
                    )

        logger.debug(
            "Prepared update fields: fields_set=%s, auto_now_fields=%s, custom_update_fields=%s",
            fields_set,
            auto_now_fields,
            [f.name for f in custom_update_fields],
        )

        return fields_set, auto_now_fields, custom_update_fields

    def _apply_auto_now_fields(self, objs, auto_now_fields, add=False):
        """
        Apply the current timestamp to all auto_now fields on each object.

        Args:
            objs (list[Model]): The model instances being processed.
            auto_now_fields (list[str]): Field names that require auto_now behavior.
            add (bool): Whether this is for creation (add=True) or update (add=False).
        """
        if not auto_now_fields:
            return

        from django.utils import timezone

        current_time = timezone.now()

        logger.debug(
            "Setting auto_now fields %s to %s for %d objects (add=%s)",
            auto_now_fields,
            current_time,
            len(objs),
            add,
        )

        for obj in objs:
            for field_name in auto_now_fields:
                setattr(obj, field_name, current_time)

    def _handle_auto_now_fields(self, objs, add=False):
        """
        Handle auto_now and auto_now_add fields for objects.

        Args:
            objs (list[Model]): The model instances being processed.
            add (bool): Whether this is for creation (add=True) or update (add=False).

        Returns:
            list[str]: Names of auto_now fields that were handled.
        """
        model_cls = self.model
        handled_fields = []

        for obj in objs:
            for field in model_cls._meta.local_fields:
                # Handle auto_now_add only during creation
                if add and hasattr(field, "auto_now_add") and field.auto_now_add:
                    if getattr(obj, field.name) is None:
                        field.pre_save(obj, add=True)
                    handled_fields.append(field.name)
                # Handle auto_now during creation or update
                elif hasattr(field, "auto_now") and field.auto_now:
                    field.pre_save(obj, add=add)
                    handled_fields.append(field.name)

        return list(set(handled_fields))  # Remove duplicates
