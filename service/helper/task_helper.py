"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 13.08.19

"""
from celery import Task


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