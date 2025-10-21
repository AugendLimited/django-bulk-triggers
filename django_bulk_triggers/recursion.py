"""
Recursion detection and prevention for trigger execution.

Provides thread-safe recursion tracking to prevent infinite loops,
similar to Salesforce's trigger recursion limits.
"""

import threading
from typing import List, Tuple, Type


class RecursionGuard:
    """
    Thread-safe recursion detection for triggers.

    Prevents infinite loops by tracking:
    1. Call stack (detects cycles like A:AFTER → B:BEFORE → A:AFTER)
    2. Depth per (model, event) pair (prevents deep recursion)

    Similar to Salesforce's trigger recursion limits.
    """

    _thread_local = threading.local()
    MAX_DEPTH_PER_EVENT = 10

    @classmethod
    def enter(cls, model_cls: Type, event: str) -> int:
        """
        Track entering a dispatch context with cycle detection.

        Args:
            model_cls: The Django model class
            event: The event name (e.g., 'after_update')

        Returns:
            Current depth for this (model, event) pair

        Raises:
            RuntimeError: If a cycle is detected or max depth exceeded
        """
        if not hasattr(cls._thread_local, "stack"):
            cls._thread_local.stack = []
        if not hasattr(cls._thread_local, "depth"):
            cls._thread_local.depth = {}

        key = (model_cls, event)

        # Check for cycles in the call stack
        if key in cls._thread_local.stack:
            cycle_path = " → ".join(
                f"{m.__name__}:{e}" for m, e in cls._thread_local.stack
            )
            cycle_path += f" → {model_cls.__name__}:{event}"
            raise RuntimeError(
                f"Trigger recursion cycle detected: {cycle_path}. "
                f"This indicates an infinite loop in your trigger chain."
            )

        # Check depth threshold
        cls._thread_local.depth[key] = cls._thread_local.depth.get(key, 0) + 1
        depth = cls._thread_local.depth[key]

        if depth > cls.MAX_DEPTH_PER_EVENT:
            raise RuntimeError(
                f"Maximum trigger depth ({cls.MAX_DEPTH_PER_EVENT}) exceeded "
                f"for {model_cls.__name__}.{event}. "
                f"This likely indicates infinite recursion in your triggers."
            )

        # Add to call stack
        cls._thread_local.stack.append(key)

        return depth

    @classmethod
    def exit(cls, model_cls: Type, event: str) -> None:
        """
        Track exiting a dispatch context.

        Args:
            model_cls: The Django model class
            event: The event name
        """
        key = (model_cls, event)

        # Remove from call stack
        if hasattr(cls._thread_local, "stack") and cls._thread_local.stack:
            if cls._thread_local.stack[-1] == key:
                cls._thread_local.stack.pop()

        # Decrement depth
        if hasattr(cls._thread_local, "depth") and key in cls._thread_local.depth:
            cls._thread_local.depth[key] -= 1

    @classmethod
    def get_current_depth(cls, model_cls: Type, event: str) -> int:
        """
        Get current recursion depth for a (model, event) pair.

        Args:
            model_cls: The Django model class
            event: The event name

        Returns:
            Current depth (0 if not in any dispatch)
        """
        if not hasattr(cls._thread_local, "depth"):
            return 0
        key = (model_cls, event)
        return cls._thread_local.depth.get(key, 0)

    @classmethod
    def get_call_stack(cls) -> List[Tuple[Type, str]]:
        """
        Get current call stack for debugging.

        Returns:
            List of (model_cls, event) tuples in call order
        """
        if not hasattr(cls._thread_local, "stack"):
            return []
        return list(cls._thread_local.stack)

    @classmethod
    def reset(cls) -> None:
        """
        Reset all recursion tracking state.

        Useful for testing to ensure clean state between tests.
        WARNING: This should only be called in tests, not production code.
        """
        if hasattr(cls._thread_local, "stack"):
            cls._thread_local.stack.clear()
        if hasattr(cls._thread_local, "depth"):
            cls._thread_local.depth.clear()
