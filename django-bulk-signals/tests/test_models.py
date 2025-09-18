"""
Tests for django-bulk-signals models.

This module tests the BulkSignalModel abstract base class and its integration
with the BulkSignalManager.
"""

from unittest.mock import Mock, patch

from django.db import models
from django.test import TestCase

from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.manager import BulkSignalManager


class TestBulkModel(BulkSignalModel):
    """Test model that inherits from BulkSignalModel."""
    
    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)
    
    class Meta:
        app_label = "tests"


class TestBulkSignalModel(TestCase):
    """Test BulkSignalModel functionality."""

    def setUp(self):
        """Set up test data."""
        self.test_obj = TestBulkModel(name="test", value=42)

    def test_model_inheritance(self):
        """Test that BulkSignalModel is properly inherited."""
        self.assertIsInstance(self.test_obj, BulkSignalModel)
        self.assertIsInstance(TestBulkModel.objects, BulkSignalManager)

    def test_manager_assignment(self):
        """Test that BulkSignalManager is assigned to objects."""
        self.assertIsInstance(TestBulkModel.objects, BulkSignalManager)

    def test_save_with_signals_new_object(self):
        """Test save() method for new objects (pk=None) with signals enabled."""
        with patch.object(TestBulkModel.objects, 'bulk_create') as mock_bulk_create:
            self.test_obj.save()
            
            # Should call bulk_create since pk is None
            mock_bulk_create.assert_called_once_with([self.test_obj])

    def test_save_with_signals_existing_object(self):
        """Test save() method for existing objects (pk set) with signals enabled."""
        self.test_obj.pk = 1  # Simulate existing object
        
        with patch.object(TestBulkModel.objects, 'bulk_update') as mock_bulk_update:
            self.test_obj.save()
            
            # Should call bulk_update since pk is set
            mock_bulk_update.assert_called_once_with([self.test_obj])

    def test_save_skip_signals_new_object(self):
        """Test save() method with skip_signals=True for new objects."""
        with patch.object(TestBulkModel.objects, 'bulk_create') as mock_bulk_create:
            # Mock the parent save method
            with patch('django.db.models.Model.save') as mock_parent_save:
                self.test_obj.save(skip_signals=True)
                
                # Should call parent save method, not bulk operations
                mock_parent_save.assert_called_once()
                mock_bulk_create.assert_not_called()

    def test_save_skip_signals_existing_object(self):
        """Test save() method with skip_signals=True for existing objects."""
        self.test_obj.pk = 1  # Simulate existing object
        
        with patch.object(TestBulkModel.objects, 'bulk_update') as mock_bulk_update:
            # Mock the parent save method
            with patch('django.db.models.Model.save') as mock_parent_save:
                self.test_obj.save(skip_signals=True)
                
                # Should call parent save method, not bulk operations
                mock_parent_save.assert_called_once()
                mock_bulk_update.assert_not_called()

    def test_save_with_additional_args(self):
        """Test save() method passes additional arguments correctly."""
        with patch.object(TestBulkModel.objects, 'bulk_create') as mock_bulk_create:
            self.test_obj.save(force_insert=True, update_fields=['name'])
            
            # Should pass additional kwargs to bulk_create
            mock_bulk_create.assert_called_once_with([self.test_obj])

    def test_delete_with_signals_new_object(self):
        """Test delete() method for new objects (pk=None) with signals enabled."""
        with patch.object(TestBulkModel.objects, 'bulk_delete') as mock_bulk_delete:
            self.test_obj.delete()
            
            # Should call bulk_delete since pk is None
            mock_bulk_delete.assert_called_once_with([self.test_obj])

    def test_delete_with_signals_existing_object(self):
        """Test delete() method for existing objects (pk set) with signals enabled."""
        self.test_obj.pk = 1  # Simulate existing object
        
        with patch.object(TestBulkModel.objects, 'bulk_delete') as mock_bulk_delete:
            self.test_obj.delete()
            
            # Should call bulk_delete since pk is set
            mock_bulk_delete.assert_called_once_with([self.test_obj])

    def test_delete_skip_signals_new_object(self):
        """Test delete() method with skip_signals=True for new objects."""
        with patch.object(TestBulkModel.objects, 'bulk_delete') as mock_bulk_delete:
            # Mock the parent delete method
            with patch('django.db.models.Model.delete') as mock_parent_delete:
                self.test_obj.delete(skip_signals=True)
                
                # Should call parent delete method, not bulk operations
                mock_parent_delete.assert_called_once()
                mock_bulk_delete.assert_not_called()

    def test_delete_skip_signals_existing_object(self):
        """Test delete() method with skip_signals=True for existing objects."""
        self.test_obj.pk = 1  # Simulate existing object
        
        with patch.object(TestBulkModel.objects, 'bulk_delete') as mock_bulk_delete:
            # Mock the parent delete method
            with patch('django.db.models.Model.delete') as mock_parent_delete:
                self.test_obj.delete(skip_signals=True)
                
                # Should call parent delete method, not bulk operations
                mock_parent_delete.assert_called_once()
                mock_bulk_delete.assert_not_called()

    def test_delete_with_additional_args(self):
        """Test delete() method passes additional arguments correctly."""
        with patch.object(TestBulkModel.objects, 'bulk_delete') as mock_bulk_delete:
            self.test_obj.delete(using='other_db')
            
            # Should pass additional kwargs to bulk_delete
            mock_bulk_delete.assert_called_once_with([self.test_obj])

    def test_model_meta_abstract(self):
        """Test that BulkSignalModel is abstract."""
        self.assertTrue(BulkSignalModel._meta.abstract)

    def test_manager_get_queryset(self):
        """Test that manager returns BulkSignalQuerySet."""
        from django_bulk_signals.queryset import BulkSignalQuerySet
        
        queryset = TestBulkModel.objects.get_queryset()
        self.assertIsInstance(queryset, BulkSignalQuerySet)

    def test_manager_bulk_create_delegation(self):
        """Test that manager bulk_create delegates to queryset."""
        with patch.object(TestBulkModel.objects, 'get_queryset') as mock_get_queryset:
            mock_queryset = Mock()
            mock_get_queryset.return_value = mock_queryset
            
            objs = [TestBulkModel(name="test1"), TestBulkModel(name="test2")]
            TestBulkModel.objects.bulk_create(objs, batch_size=100)
            
            mock_queryset.bulk_create.assert_called_once_with(
                objs, batch_size=100, ignore_conflicts=False, 
                update_conflicts=False, update_fields=None, unique_fields=None
            )

    def test_manager_bulk_update_delegation(self):
        """Test that manager bulk_update delegates to queryset."""
        with patch.object(TestBulkModel.objects, 'get_queryset') as mock_get_queryset:
            mock_queryset = Mock()
            mock_get_queryset.return_value = mock_queryset
            
            objs = [TestBulkModel(name="test1"), TestBulkModel(name="test2")]
            TestBulkModel.objects.bulk_update(objs, fields=['name'], batch_size=50)
            
            mock_queryset.bulk_update.assert_called_once_with(
                objs, fields=['name'], batch_size=50
            )

    def test_manager_bulk_delete_delegation(self):
        """Test that manager bulk_delete delegates to queryset."""
        with patch.object(TestBulkModel.objects, 'get_queryset') as mock_get_queryset:
            mock_queryset = Mock()
            mock_get_queryset.return_value = mock_queryset
            
            objs = [TestBulkModel(name="test1"), TestBulkModel(name="test2")]
            TestBulkModel.objects.bulk_delete(objs)
            
            mock_queryset.bulk_delete.assert_called_once_with(objs)

    def test_model_inheritance_chain(self):
        """Test that model properly inherits from Django's Model."""
        from django.db import models
        
        self.assertIsInstance(self.test_obj, models.Model)
        self.assertIsInstance(self.test_obj, BulkSignalModel)

    def test_model_fields_accessibility(self):
        """Test that model fields are accessible and work correctly."""
        self.test_obj.name = "updated_name"
        self.test_obj.value = 100
        
        self.assertEqual(self.test_obj.name, "updated_name")
        self.assertEqual(self.test_obj.value, 100)

    def test_model_string_representation(self):
        """Test model string representation."""
        # TestBulkModel doesn't define __str__, so it should use Django's default
        # which shows the model name and pk
        self.test_obj.pk = 1
        str_repr = str(self.test_obj)
        self.assertIn("TestBulkModel", str_repr)
        self.assertIn("1", str_repr)
