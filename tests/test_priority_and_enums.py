"""
Tests for the priority and enums modules.
"""

import pytest
from django.test import TestCase

from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.priority import Priority


class TestPriority(TestCase):
    """Test the Priority enum."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_priority_values(self):
        """Test that priority values are correct."""
        self.assertEqual(Priority.HIGHEST, 0)
        self.assertEqual(Priority.HIGH, 25)
        self.assertEqual(Priority.NORMAL, 50)
        self.assertEqual(Priority.LOW, 75)
        self.assertEqual(Priority.LOWEST, 100)

    def test_priority_comparison(self):
        """Test priority comparison operations."""
        # Test less than
        self.assertTrue(Priority.HIGHEST < Priority.HIGH)
        self.assertTrue(Priority.HIGH < Priority.NORMAL)
        self.assertTrue(Priority.NORMAL < Priority.LOW)
        self.assertTrue(Priority.LOW < Priority.LOWEST)

        # Test greater than
        self.assertTrue(Priority.LOWEST > Priority.LOW)
        self.assertTrue(Priority.LOW > Priority.NORMAL)
        self.assertTrue(Priority.NORMAL > Priority.HIGH)
        self.assertTrue(Priority.HIGH > Priority.HIGHEST)

        # Test equal
        self.assertEqual(Priority.HIGHEST, 0)
        self.assertEqual(Priority.HIGH, 25)
        self.assertEqual(Priority.NORMAL, 50)
        self.assertEqual(Priority.LOW, 75)
        self.assertEqual(Priority.LOWEST, 100)

    def test_priority_sorting(self):
        """Test that priorities can be sorted correctly."""
        priorities = [
            Priority.HIGH,
            Priority.LOW,
            Priority.LOWEST,
            Priority.NORMAL,
            Priority.HIGHEST,
        ]
        sorted_priorities = sorted(priorities)

        expected_order = [
            Priority.HIGHEST,
            Priority.HIGH,
            Priority.NORMAL,
            Priority.LOW,
            Priority.LOWEST,
        ]
        self.assertEqual(sorted_priorities, expected_order)

    def test_priority_arithmetic(self):
        """Test priority arithmetic operations."""
        # Test addition
        self.assertEqual(Priority.HIGH + Priority.NORMAL, 75)
        self.assertEqual(Priority.LOW + Priority.HIGH, 100)

        # Test subtraction
        self.assertEqual(Priority.LOW - Priority.NORMAL, 25)
        self.assertEqual(Priority.LOWEST - Priority.HIGH, 75)

        # Test multiplication
        self.assertEqual(Priority.NORMAL * 2, 100)
        self.assertEqual(Priority.HIGH * 3, 75)

    def test_priority_string_representation(self):
        """Test priority string representation."""
        self.assertEqual(str(Priority.HIGHEST), "0")
        self.assertEqual(str(Priority.HIGH), "25")
        self.assertEqual(str(Priority.NORMAL), "50")
        self.assertEqual(str(Priority.LOW), "75")
        self.assertEqual(str(Priority.LOWEST), "100")

    def test_priority_repr(self):
        """Test priority repr representation."""
        self.assertEqual(repr(Priority.HIGHEST), "<Priority.HIGHEST: 0>")
        self.assertEqual(repr(Priority.HIGH), "<Priority.HIGH: 25>")
        self.assertEqual(repr(Priority.NORMAL), "<Priority.NORMAL: 50>")
        self.assertEqual(repr(Priority.LOW), "<Priority.LOW: 75>")
        self.assertEqual(repr(Priority.LOWEST), "<Priority.LOWEST: 100>")


class TestConstants(TestCase):
    """Test the constants module."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_constant_values(self):
        """Test that constant values are correct."""
        self.assertEqual(BEFORE_CREATE, "before_create")
        self.assertEqual(AFTER_CREATE, "after_create")
        self.assertEqual(BEFORE_UPDATE, "before_update")
        self.assertEqual(AFTER_UPDATE, "after_update")
        self.assertEqual(BEFORE_DELETE, "before_delete")
        self.assertEqual(AFTER_DELETE, "after_delete")

    def test_constant_strings(self):
        """Test that constants are strings."""
        self.assertIsInstance(BEFORE_CREATE, str)
        self.assertIsInstance(AFTER_CREATE, str)
        self.assertIsInstance(BEFORE_UPDATE, str)
        self.assertIsInstance(AFTER_UPDATE, str)
        self.assertIsInstance(BEFORE_DELETE, str)
        self.assertIsInstance(AFTER_DELETE, str)

    def test_constant_format(self):
        """Test that constants follow the expected format."""
        self.assertTrue(BEFORE_CREATE.startswith("before_"))
        self.assertTrue(AFTER_CREATE.startswith("after_"))
        self.assertTrue(BEFORE_UPDATE.startswith("before_"))
        self.assertTrue(AFTER_UPDATE.startswith("after_"))
        self.assertTrue(BEFORE_DELETE.startswith("before_"))
        self.assertTrue(AFTER_DELETE.startswith("after_"))

        self.assertTrue(BEFORE_CREATE.endswith("_create"))
        self.assertTrue(AFTER_CREATE.endswith("_create"))
        self.assertTrue(BEFORE_UPDATE.endswith("_update"))
        self.assertTrue(AFTER_UPDATE.endswith("_update"))
        self.assertTrue(BEFORE_DELETE.endswith("_delete"))
        self.assertTrue(AFTER_DELETE.endswith("_delete"))


class TestPriorityAndConstantsIntegration(TestCase):
    """Integration tests for priority and constants."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_priority_with_hook_events(self):
        """Test using priorities with hook events."""
        from django_bulk_hooks import HookClass
        from django_bulk_hooks.decorators import hook

        class HookModel:
            pass

        class TestHook(HookClass):
            @hook(BEFORE_CREATE, model=HookModel, priority=Priority.HIGH)
            def high_priority_method(self, new_records, old_records=None, **kwargs):
                pass

            @hook(BEFORE_CREATE, model=HookModel, priority=Priority.LOW)
            def low_priority_method(self, new_records, old_records=None, **kwargs):
                pass

        # Verify that the hook methods were created
        self.assertTrue(hasattr(TestHook, "high_priority_method"))
        self.assertTrue(hasattr(TestHook, "low_priority_method"))

    def test_event_validation(self):
        """Test that hook events are valid."""
        valid_events = [
            BEFORE_CREATE,
            AFTER_CREATE,
            BEFORE_UPDATE,
            AFTER_UPDATE,
            BEFORE_DELETE,
            AFTER_DELETE,
        ]

        for event in valid_events:
            self.assertIsInstance(event, str)

    def test_priority_ordering_in_hooks(self):
        """Test that priorities work correctly in hook ordering."""
        from django_bulk_hooks.registry import get_hooks, register_hook

        class HookModel:
            pass

        class Handler1:
            def method1(self):
                pass

        class Handler2:
            def method2(self):
                pass

        class Handler3:
            def method3(self):
                pass

        # Register hooks with different priorities
        register_hook(
            model=HookModel,
            event=BEFORE_CREATE,
            handler_cls=Handler2,
            method_name="method2",
            condition=None,
            priority=Priority.NORMAL,
        )

        register_hook(
            model=HookModel,
            event=BEFORE_CREATE,
            handler_cls=Handler1,
            method_name="method1",
            condition=None,
            priority=Priority.LOW,
        )

        register_hook(
            model=HookModel,
            event=BEFORE_CREATE,
            handler_cls=Handler3,
            method_name="method3",
            condition=None,
            priority=Priority.HIGH,
        )

        # Get hooks and verify ordering
        hooks = get_hooks(HookModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 3)

        # Check priority order (high priority first - lower numbers)
        priorities = [hook[3] for hook in hooks]
        self.assertEqual(priorities, [Priority.HIGH, Priority.NORMAL, Priority.LOW])

        # Check handler order matches priority order
        handlers = [hook[0] for hook in hooks]
        self.assertEqual(handlers, [Handler3, Handler2, Handler1])


class TestEdgeCases(TestCase):
    """Test edge cases for priority and constants."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_priority_edge_values(self):
        """Test priority edge values."""
        # Test that priorities are integers
        self.assertIsInstance(Priority.LOW, int)
        self.assertIsInstance(Priority.NORMAL, int)
        self.assertIsInstance(Priority.HIGH, int)
        self.assertIsInstance(Priority.LOWEST, int)

        # Test that priorities are positive
        self.assertGreaterEqual(Priority.LOW, 0)
        self.assertGreaterEqual(Priority.NORMAL, 0)
        self.assertGreaterEqual(Priority.HIGH, 0)
        self.assertGreaterEqual(Priority.LOWEST, 0)

        # Test that priorities are within reasonable range
        self.assertLess(Priority.LOWEST, 1000)

    def test_constant_edge_values(self):
        """Test constant edge values."""
        # Test that events are strings
        self.assertIsInstance(BEFORE_CREATE, str)
        self.assertIsInstance(AFTER_CREATE, str)
        self.assertIsInstance(BEFORE_UPDATE, str)
        self.assertIsInstance(AFTER_UPDATE, str)
        self.assertIsInstance(BEFORE_DELETE, str)
        self.assertIsInstance(AFTER_DELETE, str)

        # Test that events are not empty
        self.assertGreater(len(BEFORE_CREATE), 0)
        self.assertGreater(len(AFTER_CREATE), 0)
        self.assertGreater(len(BEFORE_UPDATE), 0)
        self.assertGreater(len(AFTER_UPDATE), 0)
        self.assertGreater(len(BEFORE_DELETE), 0)
        self.assertGreater(len(AFTER_DELETE), 0)

    def test_priority_immutability(self):
        """Test that priority values are immutable."""
        # Test that we can't modify priority values
        with self.assertRaises(AttributeError):
            Priority.LOW = 999

    def test_priority_hashability(self):
        """Test that priority values are hashable."""
        # Test that priorities can be used as dictionary keys
        priority_dict = {
            Priority.LOW: "low",
            Priority.NORMAL: "normal",
            Priority.HIGH: "high",
            Priority.LOWEST: "lowest",
        }
        self.assertEqual(priority_dict[Priority.LOW], "low")
        self.assertEqual(priority_dict[Priority.NORMAL], "normal")

        # Test that constants can be used as dictionary keys
        event_dict = {
            BEFORE_CREATE: "before_create",
            AFTER_CREATE: "after_create",
            BEFORE_UPDATE: "before_update",
            AFTER_UPDATE: "after_update",
            BEFORE_DELETE: "before_delete",
            AFTER_DELETE: "after_delete",
        }
        self.assertEqual(event_dict[BEFORE_CREATE], "before_create")
        self.assertEqual(event_dict[AFTER_CREATE], "after_create")
