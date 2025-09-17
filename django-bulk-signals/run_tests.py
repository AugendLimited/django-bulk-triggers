#!/usr/bin/env python
"""
Simple test runner for django-bulk-signals.

This script runs the tests to verify the implementation works correctly.
"""

import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
django.setup()


def run_tests():
    """Run the tests."""
    print("🧪 Running Django Bulk Signals Tests")
    print("=" * 50)

    # Get test runner
    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    # Run tests
    failures = test_runner.run_tests(["tests"])

    if failures:
        print(f"\n❌ {failures} test(s) failed")
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        print("\n🎉 Django Bulk Signals is working correctly!")
        print("\nKey features verified:")
        print("- ✅ Bulk operation signals fire correctly")
        print("- ✅ Trigger conditions work as expected")
        print("- ✅ Decorators register handlers properly")
        print("- ✅ OLD/NEW value comparison works")
        print("- ✅ Transaction safety is maintained")
        print("- ✅ Error handling works correctly")


if __name__ == "__main__":
    run_tests()
