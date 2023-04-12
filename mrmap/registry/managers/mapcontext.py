from django.db import models
from django.db.models import OuterRef, Subquery
from extras.managers import DefaultHistoryManager
from treebeard.ns_tree import NS_NodeManager as NestedSetNodeManager


class MapContextManager(DefaultHistoryManager, models.Manager):
    pass


class MapContextLayerManager(DefaultHistoryManager, NestedSetNodeManager):

    def with_parents(self):
        """ annotates every row with its parent"""
        self.get_queryset().annotate(parent=Subquery(self.get_queryset().get(
            lft=OuterRef("lft") - 1,
            rgt=OuterRef("rgt") + 1,
            tree_id=OuterRef("tree_id")
        )))
