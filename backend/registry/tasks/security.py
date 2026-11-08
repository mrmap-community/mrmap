from celery import shared_task


@shared_task(name="async_analyze_log")
def async_analyze_log(http_response_log_id, response_log_model, **kwargs):
    """Analyze the content of one response the security proxy logged.

    Args:
        http_response_log_id (int): primary key of the logged response
        response_log_model (str): label of the response log model the row belongs
            to. The log models are abstract base classes with one concrete model
            per service type, so the primary key alone does not say which table to
            read and an abstract model cannot be instantiated (#1153)

    Returns:
        bool: whether the analysis computed something to store
    """
    from django.apps import apps

    response_log = apps.get_model(response_log_model).objects.get(
        pk=http_response_log_id)

    # the analysis of a response belongs to the service type which answered it,
    # so its model is the one which answers for this response
    analyzed_log_model = response_log._meta.get_field(
        "analyzed_response").related_model
    analyzed_response_log = analyzed_log_model(response=response_log)
    analyzed_response_log.analyze_response()

    if analyzed_response_log.entity_count is None:
        # the analysis found nothing to count: the response is no image, or the
        # analysis of this service type is not implemented yet. A row without a
        # count is no statement, so nothing is stored.
        return False

    analyzed_response_log.save()
    return True
