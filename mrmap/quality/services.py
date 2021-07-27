from quality.models import ConformityCheckRun
from .tasks import run_quality_check, complete_validation, complete_validation_error


def schedule_check_run(run: ConformityCheckRun):
    print(f'Scheduling check run with id {run.id}')

    # success_callback = complete_validation.s()
    # error_callback = complete_validation_error.s(user_id=user_id,
    #                                              config_id=config_id,
    #                                              metadata_id=resource_id)
    # run_quality_check.apply_async(args=(run.id),
    #                               link=success_callback,
    #                               link_error=error_callback)

    success_callback = complete_validation.s()
    error_callback = complete_validation_error.s(run_id=run.id)
    run_quality_check.apply_async(args=(run.id, ''),
                                  link=success_callback,
                                  link_error=error_callback)

# TODO is this still needed?
# def get_latest(request, metadata_id: str):
#     metadata = get_object_or_404(Metadata, pk=metadata_id)
#
#     try:
#         latest_run = ConformityCheckRun.objects.get_latest_check(metadata)
#         latest = {
#             "passed": latest_run.passed,
#             "running": latest_run.is_running(),
#         }
#     except ConformityCheckRun.DoesNotExist:
#         latest = {
#             "passed": None,
#             "running": None,
#         }
#
#     return JsonResponse(latest)
