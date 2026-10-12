from django.db import models
from django.db.models import Exists, OuterRef


class MonitoringRunQuerySet(models.QuerySet):
    """QuerySet for all `MonitoringRun` models which annotates the success
    state of the runs based on the results of the probes of the run.
    """

    def with_is_successful(self):
        """Annotate the success state of the runs, based on the results of
        the probes of the run.

        Every probe check which is described by the `failing_probe_checks()`
        of the run model is annotated with the name of the check. The run is
        successful if none of this checks matched a result.
        """
        failing_probe_checks = self.model.failing_probe_checks()
        annotations = {
            annotation: Exists(
                result_model.objects.filter(
                    run_id=OuterRef('pk')
                ).filter(query)
            )
            for annotation, (result_model, query)
            in failing_probe_checks.items()
        }
        failing = None
        for annotation in failing_probe_checks:
            check = models.Q(**{annotation: True})
            failing = check if failing is None else failing | check
        queryset = self.annotate(**annotations)
        if failing is None:
            return queryset.annotate(success=models.Value(True))
        return queryset.annotate(success=~failing)


class MonitoringRunManager(models.Manager):
    """Manager for all `MonitoringRun` models, which provide the annotated
    queries for the success state of the runs.
    """

    def get_queryset(self):
        return MonitoringRunQuerySet(self.model, using=self._db)

    def with_is_successful(self):
        """QuerySet of all runs of this model with annotated success state."""
        return self.get_queryset().with_is_successful()
