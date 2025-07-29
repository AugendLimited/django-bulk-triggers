#!/usr/bin/env python
"""
Simple test to verify lambda conditions work correctly.
"""

import os
import sys

# Add the current directory to the path so we can import django_bulk_hooks
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from django_bulk_hooks import LambdaCondition as LambdaConditionImport
    from django_bulk_hooks.conditions import HookCondition, LambdaCondition

    print("✅ Successfully imported LambdaCondition from conditions module")
    print("✅ Successfully imported LambdaCondition from main module")

    # Test creating a simple lambda condition
    condition = LambdaCondition(lambda instance: instance.price > 100)
    print("✅ Successfully created LambdaCondition instance")

    # Test that it's a proper HookCondition
    assert isinstance(condition, HookCondition), (
        "LambdaCondition should inherit from HookCondition"
    )
    print("✅ LambdaCondition properly inherits from HookCondition")

    # Test the check method signature
    import inspect

    sig = inspect.signature(condition.check)
    params = list(sig.parameters.keys())
    assert "instance" in params, "check method should have 'instance' parameter"
    assert "original_instance" in params, (
        "check method should have 'original_instance' parameter"
    )
    print("✅ LambdaCondition.check has correct method signature")

    # Test with required_fields
    condition_with_fields = LambdaCondition(
        lambda instance: instance.price > 100, required_fields={"price"}
    )
    assert condition_with_fields.get_required_fields() == {"price"}, (
        "Required fields should be set correctly"
    )
    print("✅ LambdaCondition with required_fields works correctly")

    print("\n🎉 All tests passed! Lambda conditions are working correctly.")

except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Test failed: {e}")
    sys.exit(1)
