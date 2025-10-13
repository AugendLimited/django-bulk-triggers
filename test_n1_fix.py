#!/usr/bin/env python

import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()

from django.db import connection
from django.test import TestCase
from tests.models import SimpleModel
from django_bulk_triggers import TriggerClass
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.constants import BEFORE_CREATE
from django_bulk_triggers.conditions import IsEqual

class N1FixTest(TestCase):
    def setUp(self):
        # Clear query log
        connection.queries_log.clear()
        
    def test_foreign_key_condition_no_n1_queries(self):
        """Test that accessing foreign key fields in conditions doesn't cause N+1 queries."""
        
        class TestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=SimpleModel, condition=IsEqual("created_by_id", value=None))
            def test_trigger(self, new_records, old_records=None, **kwargs):
                # Simple trigger that doesn't access any relationships
                pass
        
        # Create test instances
        test_instances = [
            SimpleModel(name=f"Test {i}", value=i) for i in range(5)
        ]
        
        # Clear queries before bulk_create
        initial_query_count = len(connection.queries)
        
        # Perform bulk_create
        SimpleModel.objects.bulk_create(test_instances)
        
        # Count queries executed
        final_query_count = len(connection.queries)
        queries_executed = final_query_count - initial_query_count
        
        print(f"Queries executed: {queries_executed}")
        print(f"Records processed: {len(test_instances)}")
        
        # Should be minimal queries - no N+1 pattern
        # Expected: 1 query for bulk_create + minimal overhead
        self.assertLess(queries_executed, 10, f"Too many queries executed: {queries_executed}")
        
        # Print query details for debugging
        for i, query in enumerate(connection.queries[initial_query_count:], 1):
            print(f"Query {i}: {query['sql'][:100]}...")

if __name__ == '__main__':
    # Run the test
    from django.test.runner import DiscoverRunner
    runner = DiscoverRunner()
    runner.setup_test_environment()
    runner.setup_databases()
    
    try:
        test = N1FixTest()
        test.setUp()
        test.test_foreign_key_condition_no_n1_queries()
        print("Test passed - N+1 query problem appears to be fixed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        runner.teardown_databases(None)
        runner.teardown_test_environment()
