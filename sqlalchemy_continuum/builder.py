from copy import copy

import sqlalchemy as sa
from sqlalchemy_utils.functions import declarative_base

from .table_builder import TableBuilder
from .model_builder import ModelBuilder
from .relationship_builder import RelationshipBuilder


class Builder(object):
    def build_tables(self):
        """
        Build tables for history models based on classes that were collected
        during class instrumentation process.
        """
        for cls in self.manager.pending_classes:
            if not self.manager.option(cls, 'versioning'):
                continue

            inherited_table = None
            for class_ in self.manager.tables:
                if (issubclass(cls, class_) and
                        cls.__table__ == class_.__table__):
                    inherited_table = self.manager.tables[class_]
                    break

            builder = TableBuilder(
                self.manager,
                cls.__table__,
                model=cls
            )
            if inherited_table is not None:
                self.manager.tables[class_] = builder(inherited_table)
            else:
                table = builder()
                self.manager.tables[cls] = table

    def closest_matching_table(self, model):
        """
        Returns the closest matching table from the generated tables dictionary
        for given model. First tries to fetch an exact match for given model.
        If no table was found then tries to match given model as a subclass.

        :param model: SQLAlchemy declarative model class.
        """
        if model in self.manager.tables:
            return self.manager.tables[model]
        for cls in self.manager.tables:
            if issubclass(model, cls):
                return self.manager.tables[cls]

    def build_models(self):
        """
        Build declarative history models based on classes that were collected
        during class instrumentation process.
        """
        if self.manager.pending_classes:
            cls = self.manager.pending_classes[0]
            self.manager.declarative_base = declarative_base(cls)
            self.manager.create_transaction_log()
            self.manager.plugins.after_build_tx_class(self.manager)

            for cls in self.manager.pending_classes:
                if not self.manager.option(cls, 'versioning'):
                    continue

                table = self.closest_matching_table(cls)
                if table is not None:
                    builder = ModelBuilder(self.manager, cls)
                    history_cls = builder(
                        table,
                        self.manager.transaction_log_cls
                    )

                    self.manager.plugins.after_history_class_built(
                        cls,
                        history_cls
                    )

        self.manager.plugins.after_build_models(self.manager)

    def build_relationships(self, history_classes):
        """
        Builds relationships for all history classes.

        :param history_classes: list of generated history classes
        """
        for cls in history_classes:
            if not self.manager.option(cls, 'versioning'):
                continue

            for prop in sa.inspect(cls).iterate_properties:
                if prop.key == 'versions':
                    continue
                builder = RelationshipBuilder(self.manager, cls, prop)
                builder()

    def instrument_versioned_classes(self, mapper, cls):
        """
        Collect versioned class and add it to pending_classes list.

        :mapper mapper: SQLAlchemy mapper object
        :cls cls: SQLAlchemy declarative class
        """
        if not self.manager.options['versioning']:
            return

        if hasattr(cls, '__versioned__'):
            if (not cls.__versioned__.get('class')
                    and cls not in self.manager.pending_classes):
                self.manager.pending_classes.append(cls)
                self.manager.metadata = cls.metadata

    def configure_versioned_classes(self):
        """
        Configures all versioned classes that were collected during
        instrumentation process. The configuration has 4 steps:

        1. Build tables for history models.
        2. Build the actual history model declarative classes.
        3. Build relationships between these models.
        4. Empty pending_classes list so that consecutive mapper configuration
           does not create multiple history classes
        5. Assign all versioned attributes to use active history.
        """
        if not self.manager.options['versioning']:
            return

        self.build_tables()
        self.build_models()

        # Create copy of all pending versioned classes so that we can inspect
        # them later when creating relationships.
        pending_copy = copy(self.manager.pending_classes)
        self.manager.pending_classes = []
        self.build_relationships(pending_copy)

        for cls in pending_copy:
            # set the "active_history" flag
            for prop in sa.inspect(cls).iterate_properties:
                getattr(cls, prop.key).impl.active_history = True