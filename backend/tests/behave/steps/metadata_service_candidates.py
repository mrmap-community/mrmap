""" Domain steps of the service candidates endpoints of a metadata record.

    Discovery reads the stored document of the record; the validation asks one
    endpoint which that document advertised. Both are guarded here: an upstream
    answer is prepared by the scenario and every call is recorded, so a
    scenario can assert that discovery performed no request at all and that a
    validation asked exactly the one advertised endpoint.

    What the two answer for the registration is guarded here too: a delivering
    endpoint names the qualified url the create serializer of a service accepts,
    and what a caller learns about an endpoint is told apart from what it may
    register.
"""

from unittest.mock import patch

from behave import given, then
from django.contrib.auth import get_user_model
from registry.models.metadata import DatasetMetadataRecord
from requests import Response
from requests.sessions import Session

#: the record of ``test_datasetmetadata.json`` whose detail page asks for the
#: candidates; ``environment.load_fixtures`` stores ``RBSN_RR.xml`` for it, so
#: the advertised endpoints of the scenarios are the ones of that document
RECORD = "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"

#: the reader of the candidates which may register nothing; like the users of
#: ``test_users.json`` its password equals its name, and it is removed by its
#: own step because the fixtures of a feature are not restored
READER = "Reader1"

#: What an endpoint nobody prepared answers: content which is no capabilities
#: document, so a scenario which expects no request can not pass by accident.
NOT_A_SERVICE = b"<html><body>no service</body></html>"


def _response(content):
    """ A consumed response, like a read of a small document ends. """
    response = Response()
    response.status_code = 200
    response._content = content
    response._content_consumed = True
    response.headers["Content-Type"] = "application/xml"
    return response


@given("no upstream answer is prepared")
def guard_upstream(context):
    context.candidates_answers = {}
    context.candidates_asked = []

    def answer(request, **kwargs):
        context.candidates_asked.append(request.url)
        return _response(context.candidates_answers.get(request.url,
                                                        NOT_A_SERVICE))

    mock = patch.object(Session, "send", side_effect=answer)
    mock.start()
    context.add_cleanup(mock.stop)


@given("the stored document of the record is gone")
def remove_stored_document(context):
    """ Takes the stored document away, like a lost media directory would.

        The record holds no readable document any more, which is the state a
        resolution must answer instead of failing on the read. The reference is
        restored afterwards, because the fixture of the feature is loaded once
        and the other scenarios read the same record.
    """
    record = DatasetMetadataRecord.objects.get(pk=RECORD)
    name = record.xml_backup_file.name
    record.xml_backup_file.name = ""
    record.save()

    def restore():
        record.xml_backup_file.name = name
        record.save()

    context.add_cleanup(restore)


@given('the endpoint "{url}" answers these capabilities:')
def prepare_answer(context, url):
    context.candidates_answers[url] = context.text.strip().encode()
    context.candidates_answered = url


@then("the resolution has not contacted upstream")
def assert_no_upstream(context):
    context.test.assertEqual([], context.candidates_asked)


@then("only the endpoint the record advertised was asked")
def assert_asked_the_advertised_endpoint(context):
    context.test.assertEqual(
        [context.candidates_answered], context.candidates_asked)


@then("the answer names no url to register")
def assert_no_registration_url(context):
    """ Nothing is handed over for an endpoint which did not deliver.

        Only a document which announced a service the registry can create
        completes the asked url to the qualified request the create serializer
        takes; an endpoint which refused answers none, so no form is prefilled
        with an endpoint which can not finish.
    """
    context.test.assertIsNone(
        context.response.json().get("registration_url"))


@given("a user which may read records but may not register services")
def create_reader_without_registration_right(context):
    """ A user in no group at all, which sees the candidates of the record.

        Reading a record asks the view permission of the record, registering one
        of its endpoints is the create of another resource and asks the add
        permission of that resource. The scenario uses this user for both: what
        it learns about an endpoint is not what it may register.
    """
    user, _ = get_user_model().objects.get_or_create(username=READER)
    user.groups.clear()
    user.set_password(READER)
    user.save()
    context.add_cleanup(user.delete)
