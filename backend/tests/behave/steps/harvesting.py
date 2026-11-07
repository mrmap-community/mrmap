"""Runs of a catalogue, written by the scenario which asks them and taken away again.

The harvesting scenarios of this feature ask the two jobs of `test_csw.json`, which belong to two
different catalogues and never ended. The harvesting screens of a catalogue want the runs of *one*
catalogue, and since #1079 filled the moment a run was made, the endpoint orders them by it - which
is what these two runs assert. They are written inside a transaction the cleanup rolls back, because
the fixture is loaded once for the whole feature and its counts belong to its sibling scenarios.
"""
from behave import given, then
from django.db import transaction
from django.utils.dateparse import parse_datetime
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob


def rollback_runs(atomic):
    transaction.set_rollback(True)
    atomic.__exit__(None, None, None)


@given("the catalogue {service_id} has two finished runs started at {older} and {newer}")
def two_runs_of_one_catalogue(context, service_id, older, newer):
    # Restores the fixture even when an assertion fails, as statistical.py does for its history.
    atomic = transaction.atomic()
    atomic.__enter__()
    context.add_cleanup(rollback_runs, atomic)

    older_moment, newer_moment = parse_datetime(older), parse_datetime(newer)
    runs = {}
    for name, started in (('older', older_moment), ('newer', newer_moment)):
        # Both runs ended: a service answers only one run without an end (#only_one_unfinished).
        # The starts are handed to the model on purpose - a run answers the moment it was made
        # since #1079, and the moment a client asks about has to be the one the scenario named.
        job = HarvestingJob.objects.create(
            service_id=service_id, date_created=started, done_at=started,
            phase=HarvestingPhaseEnum.COMPLETED.value)
        runs[name] = str(job.pk)
    context.harvesting_runs = runs
    context.newest_run_moment = newer_moment


@then("I expect the runs of the catalogue newest first")
def runs_newest_first(context):
    """The order of the answer and the moment it names for its newest run"""
    data = context.response.json()["data"]
    ids = [row["id"] for row in data]
    assert ids == [context.harvesting_runs["newer"], context.harvesting_runs["older"]], (
        f"sort=-dateCreated answered {ids}, not the newest run first")
    named = data[0]["attributes"]["dateCreated"]
    assert named is not None, (
        "the run which is the last of its catalogue answers no moment it was made - the card of "
        "the catalogue renders 'Started: —' for it")
    assert parse_datetime(named) == context.newest_run_moment, (
        f"the last run of the catalogue is named {named}, not the moment it was started")


@then("I expect the new run answers the moment it was made")
def new_run_answers_its_moment(context):
    """The answer which started the run carries its start.

    The client sends nothing but the catalogue, so the moment is answered by the model or by nobody
    - and the screen which shows the run reads it out of this very answer (#1079).
    """
    named = context.response.json()["data"]["attributes"]["dateCreated"]
    assert named is not None, (
        "the answer which started the run hides its start - the card of the catalogue renders "
        "'Started: —' and no elapsed time for it")
    assert parse_datetime(named) is not None, (
        f"the run names {named} as its start, which is no moment to order or measure by")


@then("I expect only the newer run of the catalogue")
def only_the_newer_run(context):
    """The run the time range the scenario asked is about"""
    ids = [row["id"] for row in context.response.json()["data"]]
    assert ids == [context.harvesting_runs["newer"]], (
        f"the time range answered {ids}, not only the run which starts inside it")
