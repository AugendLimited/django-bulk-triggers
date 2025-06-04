class TriggerContext:
    def __init__(self, model_cls, metadata=None):
        self.model_cls = model_cls
        self.metadata = metadata or {}
