"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 13.08.19

"""
from celery import Task
from celery.result import AsyncResult


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
        print(task.request)
        exit(-1)


def update_progress(task: Task, new_status: int):
    """ Set the current progress for the task object (celery)

    Args:
        task (Task):
        new_status (int): The progress bar
    :return:
    """
    if new_status < 0 or new_status > 100:
        raise ValueError("new_status must be in range [0, 100]")
    task.update_state(state='PROGRESS',
                      meta={
                          'current': new_status,
                          'total': 100,
                      }
                      )