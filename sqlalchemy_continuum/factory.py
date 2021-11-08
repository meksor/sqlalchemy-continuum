class ModelFactory(object):
    model_name = None

    def __call__(self, manager):
        """
        Create model class but only if it doesn't already exist
        in declarative model registry.
        """
        for mapper in manager.declarative_base.registry.mappers:
            clsname = mapper.class_.__name__
            if self.model_name == clsname:
                return mapper.class_
        else:
            return self.create_class(manager)
