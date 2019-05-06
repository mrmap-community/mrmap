"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 17.04.19

"""


def execute_threads(thread_list):
    """ Executes a list of threads

    Args:
        thread_list (list): A list of threads
    Returns: nothing
    """
    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()
