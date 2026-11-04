"""The celery queue names of the deployment, declared in one place.

The names are used by three things which must not drift apart: the ``Queue``
declarations of ``MrMap/settings.py``, the ``queue=`` of the task
declarations (this project routes through the task declarations, there are
no ``CELERY_TASK_ROUTES``) and the broker introspection of the harvest
(``registry.tasks.harvest.HARVEST_BROKER_QUEUES``). What the workers
actually consume is the ``-Q`` list of their celery command in the
docker-compose files; a queue declared here must be in that list or its
messages are never read - the starvation of #970 is what a queue without a
consumer on the other end turns into.
"""

# Everything which is neither bulk work nor bound to a protocol step.
DEFAULT = "default"
# The download backlog of a harvest: one message per catalogue round trip.
# Floodable, which is why it has long had a queue of its own already.
DOWNLOAD = "download"
# Database work which has to answer quickly: the control messages which build
# and rebuild a harvest's import chord, the callbacks which end harvests and
# background processes, and the beat-scheduled periodic tasks. A catalogue
# must not be able to fill this queue (#970).
DB_ROUTINES = "db-routines"
# The import backlog of a harvest: one message per stored metadata file or
# per chunk of them. This is the queue a real catalogue fills - the 411k
# record harvest of the demo measured a 17 h drain here, which is exactly
# what the messages of DB_ROUTINES must not wait behind (#970).
HARVEST_IMPORT = "harvest-import"
# Service monitoring round trips.
MONITORING = "monitoring"
# The update jobs of registered services.
UPDATE = "update"
