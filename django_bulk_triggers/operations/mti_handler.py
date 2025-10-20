"""
Multi-table inheritance (MTI) handler service.

Handles detection and coordination of multi-table inheritance operations.
"""

import logging

logger = logging.getLogger(__name__)


class MTIHandler:
    """
    Handles multi-table inheritance (MTI) operations.
    
    This service detects MTI models and provides the inheritance chain
    for coordinating parent/child table operations.
    """
    
    def __init__(self, model_cls):
        """
        Initialize MTI handler for a specific model.
        
        Args:
            model_cls: The Django model class
        """
        self.model_cls = model_cls
        self._inheritance_chain = None
    
    def is_mti_model(self):
        """
        Determine if the model uses multi-table inheritance.
        
        Returns:
            bool: True if model has concrete parent models
        """
        for parent in self.model_cls._meta.all_parents:
            if parent._meta.concrete_model != self.model_cls._meta.concrete_model:
                return True
        return False
    
    def get_inheritance_chain(self):
        """
        Get the complete inheritance chain from root to child.
        
        Returns:
            list: Model classes ordered from root parent to current model
                 Returns empty list if not MTI model
        """
        if self._inheritance_chain is None:
            self._inheritance_chain = self._compute_chain()
        return self._inheritance_chain
    
    def _compute_chain(self):
        """
        Compute the inheritance chain by walking up the parent hierarchy.
        
        Returns:
            list: Model classes in order [RootParent, Parent, Child]
        """
        chain = []
        current_model = self.model_cls
        
        while current_model:
            if not current_model._meta.proxy:
                chain.append(current_model)
            
            # Get concrete parent models
            parents = [
                parent
                for parent in current_model._meta.parents.keys()
                if not parent._meta.proxy
            ]
            
            current_model = parents[0] if parents else None
        
        # Reverse to get root-to-child order
        chain.reverse()
        return chain
    
    def get_parent_models(self):
        """
        Get all parent models in the inheritance chain.
        
        Returns:
            list: Parent model classes (excludes current model)
        """
        chain = self.get_inheritance_chain()
        if len(chain) <= 1:
            return []
        return chain[:-1]  # All except current model
    
    def get_local_fields_for_model(self, model_cls):
        """
        Get fields defined directly on a specific model in the chain.
        
        Args:
            model_cls: Model class to get fields for
            
        Returns:
            list: Field objects defined on this model
        """
        return list(model_cls._meta.local_fields)

