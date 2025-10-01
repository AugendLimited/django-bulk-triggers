"""
Test case for MTI upsert with mixed new and existing records.

This tests the fix for the issue where in a Multi-Table Inheritance (MTI) scenario,
when performing a bulk upsert with a list containing both new and existing records,
new records would end up with id: None because the zip logic was incorrectly pairing
batch objects with child objects.
"""

import pytest
from django.db import models
from django.test import TestCase

from django_bulk_triggers.models import TriggerModelMixin


class Company(TriggerModelMixin):
    """Root parent model with auto-generated fields."""
    name = models.CharField(max_length=255)
    cif_number = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'tests'


class Business(Company):
    """Child model inheriting from Company."""
    industry = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        app_label = 'tests'


class MTIUpsertMixedTest(TestCase):
    """Test MTI bulk upsert with mixed new and existing records."""
    
    databases = {'default'}
    
    def setUp(self):
        """Set up test data."""
        # Create some existing records
        Business.objects.bulk_create([
            Business(name='Existing 1', cif_number='EX001', industry='Tech'),
            Business(name='Existing 2', cif_number='EX002', industry='Finance'),
            Business(name='Existing 3', cif_number='EX003', industry='Retail'),
        ])
    
    def test_upsert_mixed_new_and_existing_records(self):
        """
        Test that when upserting a mix of new and existing records in MTI,
        all records get their IDs and auto-generated fields properly set.
        """
        # Create a list with both existing (matched by cif_number) and new records
        # The order is: existing, existing, new, existing, new, new
        upsert_objects = [
            Business(name='Existing 1 Updated', cif_number='EX001', industry='Tech Updated'),
            Business(name='Existing 2 Updated', cif_number='EX002', industry='Finance Updated'),
            Business(name='New 1', cif_number='NEW001', industry='Healthcare'),
            Business(name='Existing 3 Updated', cif_number='EX003', industry='Retail Updated'),
            Business(name='New 2', cif_number='NEW002', industry='Education'),
            Business(name='New 3', cif_number='NEW003', industry='Energy'),
        ]
        
        # Perform upsert
        result = Business.objects.bulk_create(
            upsert_objects,
            update_conflicts=True,
            update_fields=['name', 'industry'],
            unique_fields=['cif_number']
        )
        
        # Verify all records have IDs
        for i, obj in enumerate(result):
            assert obj.id is not None, f"Object at index {i} (cif_number={obj.cif_number}) has id=None"
            assert obj.pk is not None, f"Object at index {i} (cif_number={obj.cif_number}) has pk=None"
        
        # Verify all records have auto-generated timestamps
        for i, obj in enumerate(result):
            assert obj.created_at is not None, (
                f"Object at index {i} (cif_number={obj.cif_number}) has created_at=None"
            )
            assert obj.updated_at is not None, (
                f"Object at index {i} (cif_number={obj.cif_number}) has updated_at=None"
            )
        
        # Verify existing records kept their IDs
        existing_1 = Business.objects.get(cif_number='EX001')
        existing_2 = Business.objects.get(cif_number='EX002')
        existing_3 = Business.objects.get(cif_number='EX003')
        
        # The existing records should have the same IDs as before
        assert existing_1.name == 'Existing 1 Updated'
        assert existing_1.industry == 'Tech Updated'
        
        assert existing_2.name == 'Existing 2 Updated'
        assert existing_2.industry == 'Finance Updated'
        
        assert existing_3.name == 'Existing 3 Updated'
        assert existing_3.industry == 'Retail Updated'
        
        # Verify new records were created with proper IDs
        new_1 = Business.objects.get(cif_number='NEW001')
        assert new_1.id is not None
        assert new_1.name == 'New 1'
        assert new_1.industry == 'Healthcare'
        assert new_1.created_at is not None
        assert new_1.updated_at is not None
        
        new_2 = Business.objects.get(cif_number='NEW002')
        assert new_2.id is not None
        assert new_2.name == 'New 2'
        assert new_2.industry == 'Education'
        assert new_2.created_at is not None
        assert new_2.updated_at is not None
        
        new_3 = Business.objects.get(cif_number='NEW003')
        assert new_3.id is not None
        assert new_3.name == 'New 3'
        assert new_3.industry == 'Energy'
        assert new_3.created_at is not None
        assert new_3.updated_at is not None
        
        # Verify total count
        total_count = Business.objects.count()
        assert total_count == 6, f"Expected 6 total records, got {total_count}"
    
    def test_upsert_all_new_records(self):
        """Test upsert with all new records (no existing matches)."""
        new_objects = [
            Business(name='All New 1', cif_number='AN001', industry='A'),
            Business(name='All New 2', cif_number='AN002', industry='B'),
            Business(name='All New 3', cif_number='AN003', industry='C'),
        ]
        
        result = Business.objects.bulk_create(
            new_objects,
            update_conflicts=True,
            update_fields=['name', 'industry'],
            unique_fields=['cif_number']
        )
        
        # All should have IDs and timestamps
        for obj in result:
            assert obj.id is not None
            assert obj.created_at is not None
            assert obj.updated_at is not None
    
    def test_upsert_all_existing_records(self):
        """Test upsert with all existing records (all matches)."""
        existing_objects = [
            Business(name='Updated 1', cif_number='EX001', industry='New Industry 1'),
            Business(name='Updated 2', cif_number='EX002', industry='New Industry 2'),
            Business(name='Updated 3', cif_number='EX003', industry='New Industry 3'),
        ]
        
        result = Business.objects.bulk_create(
            existing_objects,
            update_conflicts=True,
            update_fields=['name', 'industry'],
            unique_fields=['cif_number']
        )
        
        # All should have IDs and timestamps
        for obj in result:
            assert obj.id is not None
            assert obj.created_at is not None
            assert obj.updated_at is not None
        
        # Verify updates were applied
        updated_1 = Business.objects.get(cif_number='EX001')
        assert updated_1.name == 'Updated 1'
        assert updated_1.industry == 'New Industry 1'

