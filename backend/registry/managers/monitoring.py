from django.db import models
from django.db.models import Exists, OuterRef


class MonitoringRunQuerySet(models.QuerySet):
    """QuerySet for all `MonitoringRun` models which annotates the success
    state of the runs based on the results of the probes of the run.
    """

    def for_monitoring_task(self):
        """Read plan of the ``run_{wms,wfs,csw}_monitoring`` tasks for one run.

        The tasks read the run's own columns and its ``setting``: the setting
        is what they ask for the probes to dispatch, so it is the only
        relation joined in. The probe lists themselves stay lazy reads of the
        setting's two probe relations — they are read once per kind and their
        relation names differ per concrete model, so they do not belong into a
        plan shared by all run models (#1397, cf. the monitoring family of
        ``celery-task-orm-audit``).

        Cardinality: 1 row (the tasks select one run by pk). Every concrete
        run model resolves the join against its own ``setting`` relation, the
        base model has no ``setting`` field and answers none.
        """
        return self.select_related("setting")

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

    def for_monitoring_task(self):
        """Queryset of this model's runs with the read plan of the monitoring
        tasks (see `MonitoringRunQuerySet.for_monitoring_task`)."""
        return self.get_queryset().for_monitoring_task()

    def with_is_successful(self):
        """QuerySet of all runs of this model with annotated success state."""
        return self.get_queryset().with_is_successful()


class ProbeResultQuerySet(models.QuerySet):
    """QuerySet for all `ProbeResult` models which carries the read plan of
    the retention sweep over the stored response artifacts.
    """

    def for_cleanup_batch(self):
        """Read plan of the artifact retention sweep for one result model.

        The projection of ``purge_expired_probe_response_artifacts``: the
        rows which still name a stored body, answered as
        ``("pk", "response_body")`` pairs. The sweep needs the name to take
        the file back and the pk to clear the row - never the check answers
        or the hydrated row (#1394, cf. the monitoring family of
        ``celery-task-orm-audit``).

        Cardinality: the expired rows of one model, which the sweep windows
        with ``[:N]`` as a named call-site operation; the plan stays lazy
        and chainable, so the sweep still filters its retention cutoff on
        top. Every concrete result model resolves it against its own table,
        which carries the inherited ``response_body`` column.
        """
        return self.exclude(response_body='').exclude(
            response_body=None).values_list('pk', 'response_body')


class ProbeResultManager(models.Manager):
    """Manager for all `ProbeResult` models, which provides the read plan of
    the retention sweep over the stored response artifacts.
    """

    def get_queryset(self):
        return ProbeResultQuerySet(self.model, using=self._db)

    def for_cleanup_batch(self):
        """Queryset of this model's results which still name a stored body
        (see `ProbeResultQuerySet.for_cleanup_batch`)."""
        return self.get_queryset().for_cleanup_batch()
