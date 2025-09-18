    def update(self, **kwargs):
        """
        Update QuerySet with trigger support.
        This method handles Subquery objects and complex expressions properly.
        """
        logger.debug(f"Entering update method with {len(kwargs)} kwargs")
        instances = list(self)
        if not instances:
            return 0

