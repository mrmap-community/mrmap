"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 10.11.20

"""
from celery import Task


def runs_as_async_task() -> bool:
    """Check if a method is currently running in a worker.

    This method can be called in any method to check if this method
    was called from an async celery worker.

    Code taken from: https://stackoverflow.com/a/34335221

    Returns
        True, if method was called async. False otherwise.
    """
    from celery import current_task
    if not current_task:
        return False
    elif current_task.request.id is None:
        return False
    else:
        return True


def get_task_id() -> Task:
    """Get the id of the current_task."""
    from celery import current_task
    return current_task.request.id
