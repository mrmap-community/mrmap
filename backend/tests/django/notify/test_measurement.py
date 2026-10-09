"""Mess-Harness fuer die Kosten des BackgroundProcess-Aktualisierungspfads.

Diese Datei aendert kein Verhalten, sie misst nur und gibt die Ergebnisse via
print aus (mit `-v 3` sichtbar). Die Tests sind bewusst NICHT gegen post_save
gemockt - sonst wird der teure Teil des Pfads (Signal + Serializer + channel
layer) nicht mitgemessen, anders als in test_tasks.py.

Gemessen im Testcontainer (postgis 18-3.6, Einzelprozess, Tests unter
TestCase-Isolation). Erste Spalte vor den Aenderungen, zweite Spalte danach
(2026-10-09, beide Läufe mit diesem Harness):

    [STEP-UPDATE]   5 -> 2 Statements pro Schritt
                    (vorher: SAVEPOINT, UPDATE, RELEASE, 2x SELECT derselben
                    Zeile; jetzt: UPDATE + ein annotiertes SELECT)
    [NOOP-UPDATE]   5 -> 1 Statement und keine WebSocket-Nachricht
                    (task_prerun schreibt RUNNING fuer einen laufenden Prozess)
    [BURST-100]     500 Statements / 846 ms -> 200 Statements / ~600 ms
    [LIST-10]       10 Statements fuer 10 Objekte (N+1 auf ContentType) -> 0,
                    seit process_info() related_resource_type per JOIN holt
    [PAYLOAD]       1 -> 0 zusaetzliche Abfrage pro WebSocket-Payload
    [PRECISION]     1/3 -> 33.0 (Round precision=0 wegen 'precission') -> 33.33

Ausfuehren:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test tests.django.notify.test_measurement \
        -v 3 --noinput
"""

from collections import OrderedDict
from time import perf_counter
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from notify.tasks import BackgroundProcessBased
from notify.utils import build_action_payload
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords


def dump_queries(context, limit=150):
    for query in context.captured_queries:
        print("    ", query['sql'][:limit])


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class BackgroundProcessCostTests(TestCase):
    """Zaehlt Statements bzw. Zeit fuer einen einzelnen Update-Schritt."""

    def setUp(self):
        # Der post_save-Receiver steigt ohne request im simple-history-Kontext
        # frueh aus -> ohne dieses Setup waere die Messung zu klein.
        request = APIRequestFactory().get("/api/notify/background-processes/")
        request.query_params = OrderedDict()
        HistoricalRecords.context.request = request

        self.request = request
        self.process = BackgroundProcess.objects.create(
            process_type='registering', phase='queued',
            total_steps=1000, done_steps=0)
        self.task = BackgroundProcessBased()
        self.task.background_process_pk = self.process.pk

    def tearDown(self):
        if hasattr(HistoricalRecords.context, "request"):
            del HistoricalRecords.context.request

    def test_measure_one_step_update(self):
        """Statements pro update_background_process(step_done=True)."""
        self.task.update_background_process()
        with CaptureQueriesContext(connection) as ctx:
            self.task.update_background_process(step_done=True)

        print(f"\n[STEP-UPDATE] statements={len(ctx.captured_queries)} "
              f"(2 seit dem Fix: UPDATE + annotiertes SELECT)")
        dump_queries(ctx)
        self.assertEqual(
            len(ctx.captured_queries), 2,
            "erwartet ist ein UPDATE plus ein SELECT fuer den Payload; jedes "
            "Statement mehr ist ein zusaetzlicher Roundtrip pro Task-Schritt")

    def test_measure_noop_running_update(self):
        """Der task_prerun-Hook schreibt status=RUNNING bei JEDEM Taskstart."""
        self.task.update_background_process()
        with patch('notify.tasks.post_save.send') as send, \
                CaptureQueriesContext(connection) as ctx:
            self.task.update_background_process()

        print(f"\n[NOOP-UPDATE] statements={len(ctx.captured_queries)} "
              f"(ein UPDATE ohne Treffer, keine Nachricht, kein Reload)")
        dump_queries(ctx)
        self.assertEqual(
            len(ctx.captured_queries), 1,
            "der task_prerun-Hook soll fuer einen bereits laufenden Prozess "
            "kein Reload und keinen Payload bauen, das UPDATE selbst laeuft")
        self.assertFalse(
            send.called,
            "ohne geaenderte Zeile darf keine WebSocket-Nachricht folgen")

    def test_measure_ws_payload_cost(self):
        """build_action_payload() ist genau das, was das Signal pro Update baut."""
        self.process.related_resource_type = ContentType.objects.get_for_model(
            BackgroundProcess)
        self.process.related_id = '00000000-0000-0000-0000-000000000001'
        self.process.save(update_fields=['related_resource_type', 'related_id'])

        instance = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)
        with CaptureQueriesContext(connection) as ctx:
            build_action_payload(
                request=self.request, instance=instance,
                resource_type="BackgroundProcess",
                serializer_cls=BackgroundProcessSerializer, action="updated")

        print(f"\n[PAYLOAD] statements={len(ctx.captured_queries)} "
              f"(0: process_info() holt related_resource_type per JOIN)")
        dump_queries(ctx)
        self.assertEqual(
            len(ctx.captured_queries), 0,
            "der Payload eines einzelnen Objekts darf keine zusaetzliche Abfrage "
            "ausloesen; die ContentType-Abfrage war der N+1-Fall")

    def test_measure_burst_of_100(self):
        """Naeherung fuer einen Chord mit 100 fetch_remote_metadata_xml Tasks."""
        self.task.update_background_process()
        started = perf_counter()
        with CaptureQueriesContext(connection) as ctx:
            for _ in range(100):
                self.task.update_background_process(step_done=True)
        elapsed_ms = (perf_counter() - started) * 1000

        print(f"\n[BURST-100] statements={len(ctx.captured_queries)} "
              f"elapsed={elapsed_ms:.1f}ms "
              f"-> {len(ctx.captured_queries) / 100:.1f} statements/step")
        self.assertEqual(
            len(ctx.captured_queries), 200,
            "ein Schritt soll genau ein UPDATE und ein SELECT kosten")

    def test_measure_list_select_related(self):
        """related_resource_type wird als JSON:API-Relationship geparst."""
        content_type = ContentType.objects.get_for_model(BackgroundProcess)
        for step in range(10):
            BackgroundProcess.objects.create(
                process_type='registering', phase='x', total_steps=step,
                related_resource_type=content_type,
                related_id='00000000-0000-0000-0000-000000000001')

        without = list(BackgroundProcess.objects.process_info()
                       .filter(related_resource_type__isnull=False)[:10])
        with CaptureQueriesContext(connection) as ctx:
            BackgroundProcessSerializer(
                instance=without, many=True,
                context={"request": self.request}).data
        print(f"\n[LIST-10] statements={len(ctx.captured_queries)} "
              f"(0: process_info() haengt related_resource_type per JOIN an)")
        dump_queries(ctx, 110)
        self.assertEqual(
            len(ctx.captured_queries), 0,
            "die Serialisierung einer Liste darf keine Abfrage pro Objekt "
            "ausloesen (ContentType war der N+1-Fall)")

        with_prefetch = list(
            BackgroundProcess.objects.process_info()
            .filter(related_resource_type__isnull=False)
            .select_related("related_resource_type")[:10])
        with CaptureQueriesContext(connection) as ctx:
            BackgroundProcessSerializer(
                instance=with_prefetch, many=True,
                context={"request": self.request}).data
        print(f"[LIST-10 + select_related] statements={len(ctx.captured_queries)}")
        self.assertEqual(len(ctx.captured_queries), 0,
                         "das zusaetzliche select_related ist überflüssig, "
                         "process_info bringt es bereits mit")

    def test_measure_progress_precision(self):
        """Der Annotation-Tippfehler 'precission' wurde zu precision korrigiert."""
        self.process.total_steps = 3
        self.process.done_steps = 1
        self.process.save(update_fields=['total_steps', 'done_steps'])

        progress = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk).progress
        print(f"\n[PRECISION] 1/3 -> progress={progress} (33.33 erwartet)")
        self.assertAlmostEqual(
            progress, 33.33, places=2,
            msg="Round(..., precision=2) in notify/managers.py: war 'precission' "
                "und landete in **extra, dadurch blieb precision auf 0 und "
                "progress wurde ganzzahlig gerundet")

    def test_measure_default_ordering_statement(self):
        """process_info() ordnet nach -date_created (seit 0004 indexiert)."""
        for _ in range(50):
            BackgroundProcess.objects.create(
                process_type='registering', phase='x', total_steps=1)

        with CaptureQueriesContext(connection) as ctx:
            list(BackgroundProcess.objects.process_info()[:10])
        print(f"\n[DEFAULT-ORDER] statements={len(ctx.captured_queries)}")
        dump_queries(ctx, 400)

