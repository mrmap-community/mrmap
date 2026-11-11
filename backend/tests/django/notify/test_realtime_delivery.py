"""Delivery of background-process notifications over real websocket connections.

These are the acceptance tests of the notification transport behind the
Background Job surfaces (epic #1203, issue #1209). They run the whole chain:
a model save fires the notify signals, the signal publishes through the channel
layer and the DefaultConsumer of the real ASGI application (origin validator,
token auth, routing) delivers to the websocket frames a client reads. Only the
channel layer is replaced - with the in-memory one; the debounce of the
consumer is real time, so these tests assert what a client observably
experiences, not which functions were called.

What they pin down, in the order of the epic's acceptance criteria:

* a connection receives exactly the topics it subscribed to - a thousand
  running processes stay silent for a connection that watches none of them
  (no flooding, no obscuring of the user at the transport level),
* a progress burst of one process collapses into the debounce window while the
  message of its terminal state never does (important failures stay
  discoverable),
* the creates of 1000+ processes reach the overview subscriber complete,
* a reconnection starts with clean per-connection state: the first update
  after the reconnect arrives immediately (reconnect/reload behavior),
* concurrent harvesting runs keep their announcements apart on one connection.

Run with:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test \
        tests.django.notify.test_realtime_delivery -v 3 --noinput
"""

import asyncio
import json
import time
from collections import Counter, OrderedDict

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils.timezone import now
from knox.models import AuthToken
from MrMap.asgi import application
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.utils import group_name
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

# capacity of the in-memory layer is 100 per channel by default; the flood test
# publishes more than that to one connection and must not lose a message to
# ChannelFull while the consumer drains the same queue on the test loop
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
        "CONFIG": {"capacity": 5000},
    },
}

ORIGIN = (b"origin", b"http://127.0.0.1:8000")

# the consumer collapses repeated progress messages of one topic within
# 1000 ms of each other (notify/consumers.py); the tests never sleep across it
FLOOD_SIZE = 1000


class RealtimeTransportMixin:
    """Connection handling shared by the delivery test classes.

    A subscribe frame and a disconnect are processed by the consumer on a
    worker thread, while the publishes of a test run from another one; the
    group membership of the channel layer is therefore the only place where
    a test can see that the (un)subscription has actually happened. Every
    test subscribes or disconnects right before it saves, so without the
    membership wait a publish could outrun the join and the test would flake
    on the transport instead of failing on the code.
    """

    def setUp(self):
        _, token = AuthToken.objects.create(
            get_user_model().objects.get(username="User1"))
        self.token = token
        # the notify receivers only announce while a request is bound to the
        # simple_history context - in production the web request or
        # extras/tasks.py of a celery task provides it; the publish helpers
        # bind it themselves because they run on a worker thread

    def tearDown(self):
        if hasattr(HistoricalRecords.context, "request"):
            del HistoricalRecords.context.request

    # -- transport helpers ----------------------------------------------------

    async def connect(self):
        communicator = WebsocketCommunicator(
            application=application,
            path=f"/ws/default/?token={self.token}",
            headers=[ORIGIN])
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected, f"websocket refused with code {exit_code}")
        self.addCleanup(communicator.disconnect)
        return communicator

    async def subscribe(self, communicator, topic):
        await communicator.send_json_to(
            {"action": "subscribe", "topic": topic})
        await self.wait_for_membership(topic, joined=True)

    async def wait_for_membership(self, topic, joined, timeout=10):
        """Waits until the layer really carries (or lost) the subscription."""
        layer = get_channel_layer()
        name = group_name(topic)
        deadline = time.monotonic() + timeout
        while bool(layer.groups.get(name)) != joined:
            if time.monotonic() > deadline:
                self.fail(
                    f"group {name} never reached membership state {joined}")
            await asyncio.sleep(0.01)

    def bind_request(self, path):
        """Binds the request the notify receivers build their payload with.

        Mirrors what extras/tasks.py does for every celery task; setting it
        here rather than in setUp is what carries it into the worker thread
        the publish helper runs on.
        """
        request = APIRequestFactory().get(path)
        request.query_params = OrderedDict()
        HistoricalRecords.context.request = request

    async def fresh_layer(self):
        """Starts the test on an empty in-memory layer.

        The layer lives as long as the class, while a test's event loop dies
        with it: a group which still holds a channel of a previous test
        turns every later publish into a send onto a channel nobody will
        ever read with a closed loop behind it - which is how one leaked
        connection poisons the deliveries of the tests which follow.
        """
        await get_channel_layer().flush()

    async def drain(self, communicator, idle=1.5, deadline=60):
        """Reads everything the connection has received.

        asgiref's ``receive_output`` cancels the application task when a
        read times out, so a drain may not end on a read timeout: it reads
        the communicator's output queue directly and returns once the queue
        has stayed empty for ``idle`` seconds. Exact expectations should
        still use ``receive_json_from`` - it fails with the application's
        own error, not just with missing frames.
        """
        queue = communicator.output_queue
        messages = []
        start = time.monotonic()
        last = start
        while True:
            while not queue.empty():
                frame = queue.get_nowait()
                messages.append(json.loads(frame["text"]))
                last = time.monotonic()
            if time.monotonic() - last >= idle:
                return messages
            if time.monotonic() - start >= deadline:
                self.fail(
                    f"the socket was still delivering after {deadline} s")
            await asyncio.sleep(0.05)


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
class RealtimeDeliveryTests(RealtimeTransportMixin, TransactionTestCase):
    """The transport a browser experiences, end to end, without a browser."""

    fixtures = ['test_users.json']

    # -- helpers ------------------------------------------------------------

    def request_for_publish(self):
        self.bind_request("/api/notify/background-processes/")

    def create_processes_sync(self, count):
        self.request_for_publish()
        created = [
            BackgroundProcess.objects.create(
                phase="started",
                process_type=ProcessNameEnum.MONITORING.value,
                description=f"flood process {i}")
            for i in range(count)
        ]
        # re-read inside this sync context: the caller awaits this from an
        # async test and may not touch the ORM itself
        return [BackgroundProcess.objects.get(pk=p.pk) for p in created]

    # -- tests ---------------------------------------------------------------

    async def test_a_connection_receives_only_the_topics_it_subscribed_to(self):
        """Fan-out follows the subscriptions, not the traffic of the deployment.

        The overview screen listens on the resource-wide topic and sees the
        creates; an open process screen listens on the topic of its process and
        sees its updates; a connection that subscribed to nothing - the app
        shell before it opens a background surface - receives neither. This is
        what keeps a thousand running processes from reaching every open tab.
        """
        await self.fresh_layer()
        overview = await self.connect()
        await self.subscribe(overview, "resource/BackgroundProcess")

        first, second = await database_sync_to_async(
            self.create_processes_sync)(2)

        watcher = await self.connect()
        await self.subscribe(watcher, f"resource/BackgroundProcess/{first.pk}")
        bare = await self.connect()

        def touch(process):
            self.request_for_publish()
            process.done_steps = 1
            process.status = ProcessStatusEnum.RUNNING
            process.save()

        await database_sync_to_async(touch)(first)
        await database_sync_to_async(touch)(second)

        # exactly the two creates - and the payload ids carry the raw pk,
        # only the records are in the JSON:API shape with string ids
        seen = [
            await overview.receive_json_from(timeout=10)
            for _ in range(2)
        ]
        self.assertEqual(
            [str(process.pk) for process in (first, second)],
            [str(message["event"]["payload"]["ids"][0])
             for message in seen],
            "the overview subscriber must see exactly the two creates")
        self.assertEqual(
            {"created"}, {message["event"]["type"] for message in seen})
        self.assertTrue(
            await overview.receive_nothing(timeout=1),
            "updates belong to the per-process topic and must not surface "
            "where a client only asked for the creates")

        seen = await watcher.receive_json_from(timeout=10)
        self.assertEqual(
            f"resource/BackgroundProcess/{first.pk}", seen["topic"])
        self.assertEqual("updated", seen["event"]["type"])
        self.assertEqual(
            "running",
            seen["event"]["payload"]["records"][0]["attributes"]["status"])
        self.assertTrue(
            await watcher.receive_nothing(timeout=1),
            "the watcher subscribed to one topic and saw its one update")

        self.assertTrue(
            await bare.receive_nothing(timeout=1),
            "a connection without a subscription must stay silent while two "
            "processes are announced - that is the transport-level answer to "
            "the flood the epic set out to stop")

        for connection in (overview, watcher, bare):
            await connection.disconnect()

    async def test_a_progress_burst_is_bounded_but_the_failure_always_arrives(self):
        """A failing process is never collapsed away by the debounce window.

        A process reports on every step; the consumer keeps one message per
        topic per second because every payload carries the complete record.
        The message that carries the terminal state is flagged immediate by
        the notify signal - missing it would leave a client showing a process
        that never finishes, which is the failure mode #1209 must keep fixed.
        """
        await self.fresh_layer()
        process = (await database_sync_to_async(
            self.create_processes_sync)(1))[0]

        connection = await self.connect()
        await self.subscribe(connection, f"resource/BackgroundProcess/{process.pk}")

        def step(index):
            self.request_for_publish()
            process.done_steps = index
            process.status = ProcessStatusEnum.RUNNING
            process.description = f"step {index}"
            process.save()

        def fail():
            self.request_for_publish()
            process.status = ProcessStatusEnum.FAILED
            process.description = "probe refused the capabilities document"
            process.done_at = now()
            process.save()

        steps = 20
        await database_sync_to_async(
            lambda: [step(i) for i in range(steps)])()
        # the terminal transition follows within the same window: an
        # immediate message survives the debounce no matter how recent the
        # last collapsed one was
        await database_sync_to_async(fail)()

        delivered = await self.drain(connection)
        self.assertLess(
            len(delivered), steps + 1,
            "twenty-one saves of one second must not arrive as twenty-one "
            "messages - every payload is the whole record")

        failures = [
            message for message in delivered
            if message["event"]["payload"]["records"][0]["attributes"]["status"]
            == "failed"
        ]
        self.assertEqual(1, len(failures), "the failure was announced once")
        self.assertIs(delivered[-1], failures[0],
                      "the failure of a process must reach the subscribed "
                      "client, no matter when the last collapsed message was "
                      "sent")
        self.assertEqual(
            "probe refused the capabilities document",
            failures[0]["event"]["payload"]["records"][0]["attributes"]
            ["description"])

        await connection.disconnect()

    async def test_the_creates_of_a_thousand_processes_arrive_complete(self):
        """1000+ jobs announced at once do not lose or blur the announcement.

        Every create is immediate (a client which misses a create never learns
        of that work), so the overview subscriber receives all of them - and
        still nothing but them. The bounded display in front of this stream is
        the frontend's job and pinned in its specs (panel perPage = 10).
        """
        await self.fresh_layer()
        overview = await self.connect()
        await self.subscribe(overview, "resource/BackgroundProcess")
        bare = await self.connect()

        created = await database_sync_to_async(
            self.create_processes_sync)(FLOOD_SIZE)

        delivered = await self.drain(overview, idle=2, deadline=120)

        self.assertEqual(
            len(created), len(delivered),
            "a create which never arrived leaves work the overview will "
            "never show until a reload")
        counts = Counter(
            str(message["event"]["payload"]["ids"][0])
            for message in delivered)
        self.assertTrue(
            all(c == 1 for c in counts.values()),
            "the transport delivers each announcement exactly once to a "
            "subscription; duplicates: %s of %s frames, e.g. %s" % (
                sum(c - 1 for c in counts.values()), len(delivered),
                counts.most_common(3)))
        self.assertEqual(
            {str(process.pk) for process in created}, set(counts),
            "every create's announcement must arrive exactly once")
        self.assertEqual(
            {"created"}, {message["event"]["type"] for message in delivered})
        self.assertTrue(
            await bare.receive_nothing(timeout=1),
            "the flood may not reach connections that subscribed to nothing")

        await overview.disconnect()
        await bare.disconnect()

    async def test_a_reconnect_is_delivered_to_immediately(self):
        """The debounce window belongs to the connection, not the process.

        After a dropped connection the client reloads its views and subscribes
        again over a new socket. If the last send of the old connection still
        suppressed the topic, the reloaded screen would wait out the window
        before its next update - the reconnect bug this pins closed (it is
        what per-connection state is for, see notify/consumers.py).
        """
        await self.fresh_layer()
        process = (await database_sync_to_async(
            self.create_processes_sync)(1))[0]
        topic = f"resource/BackgroundProcess/{process.pk}"

        first = await self.connect()
        await self.subscribe(first, topic)

        def touch(description):
            self.request_for_publish()
            process.description = description
            process.status = ProcessStatusEnum.RUNNING
            process.save()

        await database_sync_to_async(touch)("before the drop")
        self.assertEqual(
            "before the drop",
            (await first.receive_json_from(timeout=10))["event"]["payload"]
            ["records"][0]["attributes"]["description"])

        # a second message inside the debounce window: the dying connection
        # proves the window is really closed before the reconnect test starts
        await database_sync_to_async(touch)("dropped mid window")
        self.assertTrue(
            await first.receive_nothing(timeout=0.5),
            "the premise of the reconnect: the debounce window is active")

        await first.disconnect()
        # the disconnect handler leaves the group on a worker thread; the new
        # connection may only join a group whose membership wait is meaningful
        await self.wait_for_membership(topic, joined=False)

        second = await self.connect()
        await self.subscribe(second, topic)
        await database_sync_to_async(touch)("after the reload")

        delivered = await second.receive_json_from(timeout=10)
        self.assertEqual(
            "after the reload",
            delivered["event"]["payload"]["records"][0]["attributes"]["description"],
            "the reconnected subscription must be served right away - a "
            "debounce state shared across connections would silence it")
        self.assertTrue(
            await second.receive_nothing(timeout=0.5),
            "the new connection received exactly the one pending update")

        await second.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
class ConcurrentHarvestingDeliveryTests(RealtimeTransportMixin,
                                        TransactionTestCase):
    """Two catalogues harvesting at once stay apart on one connection."""

    fixtures = ['test_users.json']

    # -- helpers ------------------------------------------------------------

    def request_for_publish(self):
        self.bind_request("/api/registry/harvesting/harvesting-jobs/")

    def create_jobs_sync(self):
        self.request_for_publish()
        return [
            HarvestingJob.objects.create(
                total_records=10, max_step_size=5,
                phase=Phase.DOWNLOAD_RECORDS.value)
            for _ in range(2)
        ]

    def save_job_sync(self, pk, phase):
        """Saves the phase transition of one run, as the harvesting task does."""
        self.request_for_publish()
        job = HarvestingJob.objects.get(pk=pk)
        job.phase = phase
        if phase in (Phase.COMPLETED.value, Phase.ABORTED.value):
            job.done_at = now()
        job.save()
        return pk

    # -- tests ---------------------------------------------------------------

    async def test_two_runs_keep_their_announcements_apart(self):
        """Every message of a job's topic carries exactly that job's record.

        A single client watching both runs (the list of harvesting runs shows
        all of them) must be able to tell the runs apart by the record they
        push: interleaved saves of two jobs may never cross their topics, and
        the completion of one run must arrive even while the other keeps the
        connection busy.
        """
        await self.fresh_layer()
        jobs = await database_sync_to_async(self.create_jobs_sync)()
        first, second = jobs

        connection = await self.connect()
        for job in jobs:
            await self.subscribe(
                connection, f"resource/HarvestingJob/{job.pk}")

        # interleaved: run A advances, run B starts reporting, run A completes
        await database_sync_to_async(self.save_job_sync)(
            first.pk, Phase.RECORDS_TO_DB.value)
        await database_sync_to_async(self.save_job_sync)(
            second.pk, Phase.RECORDS_TO_DB.value)
        await database_sync_to_async(self.save_job_sync)(
            first.pk, Phase.COMPLETED.value)

        delivered = await self.drain(connection)
        by_topic = {}
        for message in delivered:
            by_topic.setdefault(message["topic"], []).append(message)

        first_topic = f"resource/HarvestingJob/{first.pk}"
        second_topic = f"resource/HarvestingJob/{second.pk}"
        self.assertEqual(
            {first_topic, second_topic}, set(by_topic),
            "both runs announced over the connection the client opened for "
            "the list of runs")

        for topic, job in ((first_topic, first), (second_topic, second)):
            for message in by_topic[topic]:
                record = message["event"]["payload"]["records"][0]
                self.assertEqual(
                    str(job.pk), record["id"],
                    "a push on the topic of a run carries a record of another "
                    "run - the client would overwrite the wrong row")

        last_of_first = by_topic[first_topic][-1]
        self.assertEqual(
            Phase.COMPLETED.value,
            last_of_first["event"]["payload"]["records"][0]["attributes"]["phase"],
            "the completion of a run is terminal and immediate: it may not be "
            "collapsed behind the progress of the same or the other run")
        # while run B is mid-flight its terminal state is not reached; run A's
        # completion must have been the last thing announced
        self.assertEqual(
            first_topic, delivered[-1]["topic"],
            "the announcements of the two runs may not lose their order")

        await connection.disconnect()
