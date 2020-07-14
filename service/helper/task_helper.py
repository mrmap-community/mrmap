"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 13.08.19

"""
import json

from celery import Task
from celery.result import AsyncResult
from django.core.exceptions import ObjectDoesNotExist

from structure.models import PendingTask


def update_service_description(task: Task, service: str, phase_descr: str):
    """ Set a new value to the 'service' element of the pending task description

    Args:
        task (Task): The asynchronous celery task object
        step (float): The relative step
    Returns:
        nothing
    """
    id = task.request.id
    try:
        pend_task = PendingTask.objects.get(task_id=id)
        descr_dict = json.loads(pend_task.description)
        descr_dict["service"] = service if service is not None else descr_dict["service"]
        descr_dict["phase"] = phase_descr if phase_descr is not None else descr_dict["phase"]
        pend_task.description = json.dumps(descr_dict)
        pend_task.save()
    except ObjectDoesNotExist:
        pass


def update_progress_by_step(task: Task, step: float):
    """ Increase only by a relative amount

    Args:
        task (Task): The asynchronous celery task object
        step (float): The relative step
    Returns:
        nothing
    """

    # get current status
    try:
        curr = AsyncResult(task.request.id).info.get("current", 100)
        curr += step
        # update with new progress
        update_progress(task, curr)
    except ValueError:
        pass


def update_progress(task: Task, new_status: int):
    """ Set the current progress for the task object (celery)

    Args:
        task (Task):
        new_status (int): The progress bar
    Returns:

    """
    if new_status < 0 or new_status > 100:
        raise ValueError("new_status must be in range [0, 100]")

    task.update_state(
        state='PROGRESS',
        meta={
            'current': new_status,
            'total': 100,
        }
    )