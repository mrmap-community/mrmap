"""Makes `python3 -m agent_supervisor` work, so the package can be run from
inside `scripts/` without the wrapper in front of it."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
