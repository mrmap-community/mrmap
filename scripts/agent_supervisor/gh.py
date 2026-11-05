"""GitHub access for the supervisor - always through the host's ``gh``.

Why the CLI and not HTTP: the host already holds a scoped, rotating credential
in the ``gh`` keyring, the repository's own tooling (``scripts/wip``) works the
same way, and routing every call through one command gives the offline tests one
place to stub. The supervisor stores no token of its own and nothing here reads
one.

Only read operations live here, plus the two label writes of #1058. There is
deliberately no function in this module that approves, merges, enqueues, closes
review threads or pushes.

Errors are classified instead of retried here: a supervisor tick that hits a
rate limit defers its own work rather than sleeping in a loop, which keeps one
misbehaving call from blocking the process.
"""

import json
import subprocess

PER_PAGE = 100
PAGE_LIMIT = 30          # 3000 items: no MrMap issue has that many comments
TIMEOUT_S = 60


class GhError(Exception):
    """A GitHub call that did not answer as expected.

    `kind` is one of ``ratelimit``, ``auth``, ``notfound``, ``network``,
    ``api`` - callers branch on it to decide whether to retry later or to fail
    closed, so the classification is part of the security model: an unreadable
    approval history is a denial, not a retry.
    """

    def __init__(self, message, kind="api"):
        super().__init__(message)
        self.kind = kind


def classify(stderr):
    """Map ``gh api`` stderr onto a kind, without pretending to be exhaustive."""
    text = (stderr or "").lower()
    if "rate limit" in text or "secondary rate limit" in text:
        return "ratelimit"
    if "authentication" in text or "bad credential" in text or "401" in text \
            or "requires authentication" in text:
        return "auth"
    if "404" in text or "not found" in text or "could not be resolved" in text:
        return "notfound"
    if "could not resolve host" in text or "timed out" in text or "connection" in text:
        return "network"
    return "api"


def gh_json(path, params=None, method="GET", accept=None, timeout=TIMEOUT_S):
    """One ``gh api`` call, parsed. Raises GhError with a kind on any failure."""
    cmd = ["gh", "api", path, "--method", method]
    if accept:
        cmd += ["--header", f"Accept: {accept}"]
    for key, value in sorted((params or {}).items()):
        cmd += ["--field", f"{key}={value}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise GhError("gh is not installed on this host", "network")
    except subprocess.TimeoutExpired:
        raise GhError(f"gh api {path} timed out after {timeout}s", "network")
    if r.returncode != 0:
        raise GhError(f"gh api {path}: {(r.stderr or '').strip()[:400]}",
                      classify(r.stderr))
    out = (r.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        raise GhError(f"gh api {path} did not answer JSON", "api")


def graphql(query, variables=None, timeout=TIMEOUT_S):
    """One GraphQL *query* through ``gh api graphql``, parsed.

    Needed because review threads - the unit a human's inline feedback actually
    lives in, and the thing that carries ``isResolved`` - exist only in the GraphQL
    schema; no REST endpoint answers "is this thread resolved".

    Refuses any text containing ``mutation``. That is a stronger promise than a
    rule about which helper a module is allowed to call: nothing reachable from
    this function can change GitHub, and a check can assert it without knowing
    what a query body looks like. ``errors`` in the answer is an error too: a
    partial read that looked like an empty result is how a resolved thread gets
    invented out of a typo in a field name.
    """
    if "mutation" in query.lower():
        raise GhError("graphql() reads: a mutation was refused", "api")
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in sorted((variables or {}).items()):
        cmd += ["-f", f"{key}={value}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise GhError("gh is not installed on this host", "network")
    except subprocess.TimeoutExpired:
        raise GhError(f"gh api graphql timed out after {timeout}s", "network")
    if r.returncode != 0:
        raise GhError(f"gh api graphql: {(r.stderr or '').strip()[:400]}",
                      classify(r.stderr))
    try:
        answer = json.loads((r.stdout or "").strip() or "{}")
    except ValueError:
        raise GhError("gh api graphql did not answer JSON", "api")
    if answer.get("errors"):
        raise GhError(f"graphql answered errors: {str(answer['errors'])[:300]}", "api")
    return answer.get("data")


def list_paginated(path, params=None):
    """Every page of a list endpoint, read with explicit page numbers.

    Explicit paging rather than ``--paginate`` because the pages of that flag
    are printed one after another, which is not one JSON document; and because
    knowing the page count lets a caller notice a history it could not finish
    reading - which for an approval check must fail closed, not look short.
    """
    items = []
    page = 1
    while page <= PAGE_LIMIT:
        merged = dict(params or {})
        merged.update({"per_page": PER_PAGE, "page": page})
        data = gh_json(path, merged)
        if data is None:
            break
        if not isinstance(data, list):
            raise GhError(f"{path} answered an object where a list was expected", "api")
        items.extend(data)
        if len(data) < PER_PAGE:
            return items
        page += 1
    raise GhError(f"{path}: more than {PAGE_LIMIT} pages, refusing a partial read", "api")


def whoami():
    """The login this host's gh acts as, or None if it cannot be asked.

    The approval gate treats this login as an *agent* account: whatever a human
    does with the same credential their agents push with is not an independent
    approval. Unaskable means unprovable, so the caller decides what to do with
    None - see approvals.decide().
    """
    try:
        me = gh_json("user")
    except GhError:
        return None
    return (me or {}).get("login")


def label_exists(repo, name):
    for label in list_paginated(f"repos/{repo}/labels", {"per_page": 100}):
        if label.get("name") == name:
            return True
    return False


def create_label(repo, name, color, description):
    """Create one label; return "created", "exists" or raise GhError."""
    try:
        gh_json(f"repos/{repo}/labels", {"name": name, "color": color,
                                         "description": description}, method="POST")
        return "created"
    except GhError as exc:
        if exc.kind == "api" and "already_exists" in str(exc).lower():
            return "exists"
        if "already exists" in str(exc).lower() or "label already exists" in str(exc).lower():
            return "exists"
        raise
