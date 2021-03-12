"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 09.11.20

"""


class AbortedException (Exception):
    """
    Class for asynchronous task abortion.

    This class should only be used for identifying manually aborted
    asynchronous classes, e.g. shared_task.
    """
    pass
