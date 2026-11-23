"""The dashboard of #1391 and the series it reads have to agree on the contract.

The exporter publishes into a log store and the Grafana dashboard selects the
records back out of it with LogsQL written by hand, so the two ends of one
contract live in two languages and nothing but a test keeps them together.
What a panel can select or aggregate is exactly what the exporter wrote as a
``key=value`` token of the message tail, so the assertions below read the
shipped dashboard file and check every query against the field names and the
event tokens of ``system.task_performance``.

These are not render tests and they do not start Grafana: they catch the
drift which is otherwise invisible until a dashboard quietly shows nothing -
a panel filtering on an event which was renamed, aggregating a field the
exporter never publishes, or selecting a datasource which is not provisioned.
"""

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from system.task_performance import (EVENT_CLASS_BUCKET, EVENT_FLEET,
                                     EVENT_SAMPLE)

MARKER = "Celery task performance"


def _provisioning_dir(*parts):
    """The provisioning dir of the stack, wherever this run can see it.

    Two answers, because the tests run from two roots. Inside the image the
    test container of the stack mounts ``backend`` as its root and knows the
    deployment through the read-only bind above it, named by
    ``MRMAP_GRAFANA_PROVISIONING_DIR`` (docker-compose.dev.yml); outside a
    container the checkout is searched upward from this file, since a
    developer runs the suite from ``backend``, one level below the root.
    """
    candidates = []
    named = os.environ.get("MRMAP_GRAFANA_PROVISIONING_DIR")
    if named:
        candidates.append(Path(named).joinpath(*parts))
    for base in Path(__file__).resolve().parents:
        candidates.append(base.joinpath("docker", "grafana", "provisioning",
                                        *parts))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise AssertionError(
        "the provisioning of the stack is neither at %s nor above %s - inside"
        " the test container it is mounted by docker-compose.dev.yml"
        % (candidates[0], Path(__file__).resolve()))


DASHBOARD = _provisioning_dir("dashboards", "jsons",
                              "mrmap_celery_task_performance.json")
DATASOURCES = _provisioning_dir("datasources")

#: every event the exporter can publish; a panel of anything else reads a
#: record which will never arrive
EVENTS = {EVENT_FLEET, EVENT_CLASS_BUCKET, EVENT_SAMPLE}

#: a numeric role in a LogsQL ``extract`` of these fields is what a panel
#: aggregates; a text role is what it groups by
NUMERIC_FIELDS = (
    "executions", "slot_seconds", "succeeded", "failed", "retried", "revoked",
    "uncertain_open", "uncertain_abandoned", "active_p50", "active_p95",
    "active_p99", "active_max", "wait_p50", "wait_p95", "wait_max",
    "wait_samples", "wait_coverage", "buckets", "window_seconds",
    "attempt_no", "active_seconds", "wait_seconds",
)

TEXT_FIELDS = ("event", "task_class", "queue", "worker", "periodic_name",
               "root_id", "task_name", "task_id", "outcome", "source",
               "resumed_from", "truncated")


def _dashboard():
    return json.loads(DASHBOARD.read_text())


def _targets():
    for panel in _dashboard()["panels"]:
        for target in panel["targets"]:
            yield panel, target


class DashboardFileTests(SimpleTestCase):

    def test_the_dashboard_provisions_where_grafana_looks(self):
        self.assertTrue(DASHBOARD.is_file(),
                        "Grafana provisions from jsons/ next to the slow "
                        "request dashboard; the file has to be there")
        self.assertEqual(_dashboard()["uid"], "mrmap-celery-task-performance")
        self.assertIn("mrmap", _dashboard()["tags"],
                      "so it lands in the MrMap folder like the other "
                      "dashboards of the stack")

    def test_it_selects_the_provisioned_datasource(self):
        provisioned = set()
        for name in DATASOURCES.iterdir():
            if name.suffix in (".yml", ".yaml"):
                provisioned.add(name.read_text())
        uid = _dashboard()["panels"][0]["datasource"]["uid"]
        self.assertTrue(any("uid: %s" % uid in text for text in provisioned),
                        "the datasource %r of the panels is not provisioned"
                        % uid)

    def test_every_panel_selects_the_series_and_a_datasource(self):
        for panel, target in _targets():
            self.assertEqual(target["datasource"]["uid"],
                             panel["datasource"]["uid"],
                             "panel %s mixes datasources" % panel["id"])
            self.assertEqual(target["editorMode"], "code",
                             "the queries are the documentation of the "
                             "contract and have to be visible in the panel")
            self.assertIn('"%s"' % MARKER, target["expr"],
                          "panel %s of the series has no filter on the "
                          "marker, so any log of the deployment could reach "
                          "it" % panel["id"])


class QueryContractTests(SimpleTestCase):
    """Every query of every panel reads the series as the exporter writes it."""

    def test_every_event_filter_is_an_event_the_exporter_publishes(self):
        for panel, target in _targets():
            for event in re.findall(r'"event=([a-z_]+)"', target["expr"]):
                self.assertIn(event, EVENTS,
                              "panel %s filters on event=%s, which the "
                              "exporter never publishes"
                              % (panel["id"], event))

    def test_every_extracted_field_is_a_field_of_the_record_it_selects(self):
        published = published_fields()
        for panel, target in _targets():
            events = re.findall(r'"event=([a-z_]+)"', target["expr"])
            fields = re.findall(r"extract `([a-z_]+)=<", target["expr"])
            self.assertTrue(fields,
                            "panel %s selects the series but reads no field "
                            "of it" % panel["id"])
            for field in fields:
                self.assertIn(field, TEXT_FIELDS + NUMERIC_FIELDS,
                              "panel %s reads %s, which is not part of the "
                              "contract of #1391" % (panel["id"], field))
                for event in events:
                    self.assertIn(
                        field, published[event],
                        "panel %s reads %s off a %s record, which does not "
                        "carry it" % (panel["id"], field, event))

    def test_an_extract_pattern_ends_where_the_store_can_stop(self):
        # ``extract `key=<value> ```` is a greedy placeholder; without the
        # trailing space it swallows the rest of the line, which is the
        # difference between a panel which sums and a panel which shows NaN
        for panel, target in _targets():
            for pattern in re.findall(r"extract `([^`]*)`", target["expr"]):
                self.assertTrue(
                    pattern.endswith(" ") or pattern.endswith(">"),
                    "the extract pattern of panel %s is greedy and will "
                    "swallow the rest of the line: %r"
                    % (panel["id"], pattern))

    def test_the_series_is_aggregated_not_listed_except_where_it_is_a_table(self):
        # the point of #1391 is that a dashboard refresh never becomes a query
        # per attempt, so a panel of the series either aggregates or is a
        # bounded table of the drill-down records
        for panel, target in _targets():
            if panel["type"] == "table" and EVENT_SAMPLE in target["expr"]:
                continue
            self.assertIn("stats", target["expr"],
                          "panel %s lists the series instead of aggregating "
                          "it" % panel["id"])


def published_fields():
    """The fields each event can carry, read off the builders themselves.

    The builders are called with an answer shaped like the one
    ``capacity_measures`` returns, because that is what a record is built
    from; an empty window answers with the fields which are always there,
    and the optional ones are added below as the ones a measured window may
    carry.
    """
    from datetime import timedelta

    from django.utils import timezone

    from system.task_performance import (_bucket_records, _fleet_record,
                                         _sample_records)

    now = timezone.now()
    window = {"since": now - timedelta(minutes=5), "until": now}
    fleet = dict(
        executions=1, slot_seconds=1.0, succeeded=1, failed=0, retried=0,
        revoked=0, active_p50=1.0, active_p95=1.0, active_p99=1.0,
        active_max=1.0, wait_p50=None, wait_p95=None, wait_max=None,
        wait_samples=0)
    uncertain = {"open_without_end": 0, "abandoned": 0}
    answer = {
        "window": window,
        "fleet": fleet,
        "coverage": {"wait_coverage": None},
        "uncertain": uncertain,
        "buckets": [],
        "truncated": False,
        "source": "measured_worker",
    }
    fleet_fields = set(_fleet_record(answer, "cursor"))
    bucket = dict(fleet, task_class="registry.tasks", queue="default",
                  uncertain_open=0, uncertain_abandoned=0)
    answer["buckets"] = [bucket]
    bucket_fields = set(_bucket_records(answer, "cursor")[0])
    # the sample builder reads its rows from capacity_measures; a SimpleTestCase
    # has no database, so the row it would have been handed is answered here and
    # the builder itself still decides which of its columns reach a record
    row = dict(
        task_class="registry.tasks", task_name="registry.tasks.harvest",
        queue="default", worker="celery@worker-1", periodic_name="harvest hourly",
        root_id="root-1", task_id="task-1", attempt_no=1, outcome="failure",
        active_seconds=1.0, wait_seconds=None, started_at=now, finished_at=now)
    with patch("system.task_performance.drilldown_samples",
               return_value=[row]):
        sample_fields = set(_sample_records(answer, ["registry.tasks"],
                                            "cursor")[0])
    return {
        EVENT_FLEET: fleet_fields,
        EVENT_CLASS_BUCKET: bucket_fields,
        EVENT_SAMPLE: sample_fields,
    }
