"""
Debug utilities for tracking N+1 queries and database performance.
"""

import logging
import time
from functools import wraps
from django.db import connection
from django.conf import settings

logger = logging.getLogger(__name__)


def track_queries(func):
    """
    Decorator to track database queries during function execution.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Reset query count
        initial_queries = len(connection.queries)
        initial_time = time.time()

        logger.debug(
            f"QUERY DEBUG: Starting {func.__name__} - initial query count: {initial_queries}"
        )

        try:
            result = func(*args, **kwargs)

            final_queries = len(connection.queries)
            final_time = time.time()
            query_count = final_queries - initial_queries
            duration = final_time - initial_time

            logger.debug(
                f"QUERY DEBUG: Completed {func.__name__} - queries executed: {query_count}, duration: {duration:.4f}s"
            )

            # Log all queries executed during this function
            if query_count > 0:
                logger.debug(f"QUERY DEBUG: Queries executed in {func.__name__}:")
                for i, query in enumerate(connection.queries[initial_queries:], 1):
                    logger.debug(
                        f"QUERY DEBUG:   {i}. {query['sql'][:100]}... (time: {query['time']})"
                    )

            return result

        except Exception as e:
            final_queries = len(connection.queries)
            query_count = final_queries - initial_queries
            logger.debug(
                f"QUERY DEBUG: Exception in {func.__name__} - queries executed: {query_count}"
            )
            raise

    return wrapper


def log_query_count(context=""):
    """
    Log the current query count with optional context.
    """
    query_count = len(connection.queries)
    logger.debug(f"QUERY DEBUG: Query count at {context}: {query_count}")


def log_recent_queries(count=5, context=""):
    """
    Log the most recent database queries.
    """
    recent_queries = connection.queries[-count:] if connection.queries else []
    logger.debug(f"QUERY DEBUG: Recent {len(recent_queries)} queries at {context}:")
    for i, query in enumerate(recent_queries, 1):
        logger.debug(
            f"QUERY DEBUG:   {i}. {query['sql'][:100]}... (time: {query['time']})"
        )


class QueryTracker:
    """
    Context manager for tracking database queries.
    """

    def __init__(self, context_name="QueryTracker"):
        self.context_name = context_name
        self.initial_queries = 0
        self.start_time = 0

    def __enter__(self):
        self.initial_queries = len(connection.queries)
        self.start_time = time.time()
        logger.debug(
            f"QUERY DEBUG: Starting {self.context_name} - initial query count: {self.initial_queries}"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        final_queries = len(connection.queries)
        final_time = time.time()
        query_count = final_queries - self.initial_queries
        duration = final_time - self.start_time

        logger.debug(
            f"QUERY DEBUG: Completed {self.context_name} - queries executed: {query_count}, duration: {duration:.4f}s"
        )

        if query_count > 0:
            logger.debug(f"QUERY DEBUG: Queries executed in {self.context_name}:")
            for i, query in enumerate(connection.queries[self.initial_queries :], 1):
                logger.debug(
                    f"QUERY DEBUG:   {i}. {query['sql'][:100]}... (time: {query['time']})"
                )

        return False  # Don't suppress exceptions


def enable_django_query_logging():
    """
    Enable Django's built-in query logging.
    """
    if not settings.DEBUG:
        logger.warning("Django query logging can only be enabled in DEBUG mode")
        return

    # Enable query logging
    settings.LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
            },
        },
        "loggers": {
            "django.db.backends": {
                "level": "DEBUG",
                "handlers": ["console"],
            },
        },
    }

    logger.info("Django query logging enabled")
