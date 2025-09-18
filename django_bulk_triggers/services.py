"""
Service layer for django-bulk-triggers using Python's native dependency injection.

This module provides clean service access using Python's built-in lazy loading
and module-level caching to eliminate circular imports.

Mission-critical requirements:
- Zero hacks or shortcuts
- Maintain exact same behavior as original
- Use Python's native DI capabilities
- Comprehensive error handling
- Production-grade code quality
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Module-level cache for services
_services_cache: Dict[str, Any] = {}


def get_engine_module():
    """Get the engine module with lazy import and caching."""
    if 'engine_module' not in _services_cache:
        from django_bulk_triggers import engine
        _services_cache['engine_module'] = engine
        logger.debug("Lazy-loaded engine module")
    return _services_cache['engine_module']


def get_context_module():
    """Get the context module with lazy import and caching."""
    if 'context_module' not in _services_cache:
        from django_bulk_triggers.context import (
            TriggerContext,
            get_bulk_update_active,
            get_bypass_triggers,
            get_bulk_update_value_map,
        )
        _services_cache['context_module'] = {
            'TriggerContext': TriggerContext,
            'get_bulk_update_active': get_bulk_update_active,
            'get_bypass_triggers': get_bypass_triggers,
            'get_bulk_update_value_map': get_bulk_update_value_map,
        }
        logger.debug("Lazy-loaded context module")
    return _services_cache['context_module']


def get_mti_operations():
    """Get MTI operations with minimal interface to avoid circular imports."""
    if 'mti_operations' not in _services_cache:
        class MTIInterface:
            def detect_modified_fields(self, new_instances, original_instances):
                """
                Detect fields that were modified during BEFORE_UPDATE triggers.
                
                This is extracted from MTIOperationsMixin._detect_modified_fields
                to avoid circular imports while maintaining exact functionality.
                """
                if not original_instances:
                    return set()

                modified_fields = set()

                # Since original_instances is now ordered to match new_instances, we can zip them directly
                for new_instance, original in zip(new_instances, original_instances):
                    if new_instance.pk is None or original is None:
                        continue

                    # Compare all fields to detect changes
                    for field in new_instance._meta.fields:
                        if field.name == "id":
                            continue

                        # Get the new value to check if it's an expression object
                        new_value = getattr(new_instance, field.name)

                        # Skip fields that contain expression objects - these are not in-memory modifications
                        # but rather database-level expressions that should not be applied to instances
                        from django.db.models import Subquery

                        if isinstance(new_value, Subquery) or hasattr(
                            new_value, "resolve_expression"
                        ):
                            logger.debug(
                                f"Skipping field {field.name} with expression value: {type(new_value).__name__}"
                            )
                            continue

                        # Handle different field types appropriately
                        if field.is_relation:
                            # Compare by raw id values to catch cases where only <fk>_id was set
                            original_pk = getattr(original, field.attname, None)
                            if new_value != original_pk:
                                modified_fields.add(field.name)
                        else:
                            original_value = getattr(original, field.name)
                            if new_value != original_value:
                                modified_fields.add(field.name)

                return modified_fields
        
        _services_cache['mti_operations'] = MTIInterface()
        logger.debug("Lazy-loaded MTI operations")
    return _services_cache['mti_operations']


def clear_cache():
    """Clear the services cache. Useful for testing."""
    global _services_cache
    _services_cache.clear()
    logger.debug("Cleared services cache")
