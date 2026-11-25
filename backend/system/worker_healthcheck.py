"""Worker healthcheck of the deployment (#1616), run as ``python -m``.

Celery's own directed inspect ping, without initializing Django or loading
the CLI or MrMap's task registry. ``docker-compose.yml`` runs it for
``celery-worker``; the measurement which justified the change is
``docs/source/development/celery-healthcheck-overhead.rst``.
"""

import os
import socket
import sys
from urllib.parse import quote

from celery import Celery


def ping(destination):
    # Match MrMap.settings.BROKER_URL without loading the application. The
    # stock deployment uses Celery's default control exchange and JSON. The
    # password is the same variable settings reads (#1473) and joins the URL
    # the same way: kombu percent-decodes the userinfo, so the password is
    # encoded here; empty means the plain host:port form of no auth.
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD", "")
    userinfo = f":{quote(password, safe='!$&()*+,;=')}@" if password else ""
    with Celery("healthcheck", broker=f"redis://{userinfo}{host}:{port}",
                fixups=[], set_as_current=False) as app:
        app.conf.update(
            broker_connection_timeout=2,
            broker_transport_options={
                "socket_connect_timeout": 2, "socket_timeout": 2,
            },
        )
        with app.connection_for_write() as connection:
            connection.ensure_connection(max_retries=0)
            replies = app.control.inspect(
                destination=[destination], timeout=2,
                connection=connection,
            ).ping()
    # Another worker's answer must never make this container healthy.
    return bool(replies and replies.get(destination) == {"ok": "pong"})


def main():
    destination = f"celery@{socket.gethostname()}"
    try:
        healthy = ping(destination)
    except Exception as error:
        # Health output is visible in docker inspect. Keep credentials and
        # broker URLs out of it, including third-party exception messages.
        print(f"worker ping failed: {type(error).__name__}", file=sys.stderr)
        return 1
    if not healthy:
        print("local worker did not return pong", file=sys.stderr)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
