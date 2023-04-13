from django.db import models
from django.db.models import OuterRef, Q, Subquery
from django.db.models.functions import JSONObject
from extras.managers import DefaultHistoryManager
from treebeard.ns_tree import NS_NodeManager as NestedSetNodeManager


class MapContextManager(DefaultHistoryManager, models.Manager):
    pass


class MapContextLayerManager(DefaultHistoryManager, NestedSetNodeManager):

    def get_parent_query(self, lft, rgt, tree_id):
        return Q(
            lft=lft-1,
            rgt=rgt+1,
            tree_id=tree_id
        )

    def get_parent(self):
        return self.get_queryset().filter(
            self.get_parent_query(
                OuterRef("lft"),
                OuterRef("rgt"),
                OuterRef("tree_id")
            )
        ).values(
            data=JSONObject(
                pk="pk",
                lft="lft",
                rgt="rgt",
                depth="depth",
            )
        )[:1]

    def with_parents(self):
        """Fetches parent for every node"""
        return self.get_queryset().annotate(parent=Subquery(self.get_parent()))
