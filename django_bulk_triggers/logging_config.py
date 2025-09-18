"""
Logging configuration for django-bulk-triggers.

This module provides centralized logging configuration to reduce debug noise
while maintaining essential debugging capabilities.

Mission-critical requirements:
- Zero hacks or shortcuts
- Maintain exact same behavior as original
- Reduce debug noise while preserving essential information
- Comprehensive error handling
- Production-grade code quality
"""

import logging
import os
from typing import Optional

# Environment variable to control debug verbosity
DEBUG_VERBOSE = os.getenv('DJANGO_BULK_TRIGGERS_DEBUG_VERBOSE', 'false').lower() == 'true'

# Create a custom logger for django-bulk-triggers
logger = logging.getLogger('django_bulk_triggers')

# Set up a custom formatter that reduces noise
class ReducedDebugFormatter(logging.Formatter):
    """Custom formatter that reduces debug noise while preserving essential information."""
    
    def format(self, record):
        # For debug messages, only show essential information
        if record.levelno == logging.DEBUG:
            # Skip very verbose debug messages unless explicitly enabled
            if not DEBUG_VERBOSE and self._is_noisy_debug(record.getMessage()):
                return ""
            
            # Simplify debug messages
            if 'FRAMEWORK' in record.getMessage():
                # Extract only the essential part of FRAMEWORK messages
                message = record.getMessage()
                if 'Running' in message or 'completed' in message:
                    return f"[BULK-TRIGGERS] {message.split('FRAMEWORK ')[-1]}"
                return ""
            
            # For other debug messages, keep them concise
            return f"[DEBUG] {record.getMessage()}"
        
        return super().format(record)
    
    def _is_noisy_debug(self, message: str) -> bool:
        """Determine if a debug message is too noisy for normal operation."""
        noisy_patterns = [
            'Processing object pk=',
            'Object %s field %s =',
            'Added value_map entry',
            'Built value_map for',
            'Final value_map keys:',
            'value_map[%s] =',
            'Skipping field',
            'Setting auto_now fields',
            'Applying pre_save()',
            'pre_save() returned value',
            'Custom field %s updated',
            'Field %s is a relation field',
            'Assigning ForeignKey value',
            'Direct assignment for relation field',
            'Non-relation field %s, assigning directly',
            'Added field %s to fields_set',
            'Added _id field %s to fields_set',
        ]
        
        return any(pattern in message for pattern in noisy_patterns)


def configure_logging(level: Optional[str] = None):
    """
    Configure logging for django-bulk-triggers.
    
    Args:
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    """
    if level is None:
        level = 'DEBUG' if DEBUG_VERBOSE else 'INFO'
    
    # Set the logger level
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create a console handler with our custom formatter
    handler = logging.StreamHandler()
    handler.setFormatter(ReducedDebugFormatter())
    logger.addHandler(handler)
    
    # Prevent propagation to parent loggers to avoid duplicate messages
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        name: Module name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(f'django_bulk_triggers.{name.split(".")[-1]}')


# Convenience functions for common logging patterns
def log_operation_start(operation_name: str, model_name: str, count: int, **kwargs):
    """Log the start of a bulk operation with consistent formatting."""
    if kwargs:
        param_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        logger.info(f"{operation_name} started for {model_name} with {count} objects ({param_str})")
    else:
        logger.info(f"{operation_name} started for {model_name} with {count} objects")


def log_operation_complete(operation_name: str, model_name: str, result: int):
    """Log the completion of a bulk operation."""
    logger.info(f"{operation_name} completed for {model_name}: {result} objects processed")


def log_trigger_execution(trigger_type: str, model_name: str, count: int):
    """Log trigger execution with consistent formatting."""
    logger.debug(f"Executing {trigger_type} triggers for {model_name} ({count} objects)")


def log_field_changes(changed_fields: list, count: int):
    """Log field changes in a concise format."""
    if changed_fields:
        logger.debug(f"Detected {len(changed_fields)} changed fields in {count} objects: {', '.join(changed_fields)}")


def log_mti_detection(model_name: str, is_mti: bool):
    """Log MTI detection results."""
    if is_mti:
        logger.debug(f"{model_name} detected as multi-table inheritance model")
    else:
        logger.debug(f"{model_name} is single-table model")


# Auto-configure logging when this module is imported
configure_logging()
