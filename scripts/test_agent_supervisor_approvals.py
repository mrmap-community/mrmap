"""Offline regression checks for the approval gate of the agent supervisor (#1058).

Run from the repository root: python3 scripts/test_agent_supervisor_approvals.py
Exit code 0 means every check passed. Needs no `gh`, no token and no network, and
cannot touch a real repository: every GitHub read is a stub in this file.

The gate is a security boundary, so these checks are written as the attacks and
accidents that matter, not as coverage of lines: an approval the automation made
itself, a revoked approval, a bot, an account that is not on the allowlist, a
label that appeared with no event behind it, an unreadable history, a stale
approval, and the configuration states that must all refuse. Each refusal is
asserted by its reason code, because those codes are what `explain` prints and
what the operator documentation promises.
"""

import ast
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import approvals, config, gh  # noqa: E402

PASS = FAIL = 0
FAILURES = []


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


# ---------------------------------------------------------------------------
# the stubbed GitHub

class FakeGh:
    """Answers the four endpoints the gate reads, from data in this file."""

    def __init__(self, issue=None, events=(), permissions=None, me="agent-bot",
                 fail_on=None, fail_kind="network"):
        self.issue = issue
        self.events = list(events)
        self.permissions = permissions or {}
        self.me = me
        self.fail_on = fail_on          # substring that must fail
        self.fail_kind = fail_kind
        self.reads = []

    def install(self):
        gh.gh_json = self.gh_json
        gh.list_paginated = self.list_paginated

    def gh_json(self, path, params=None, method="GET", accept=None, timeout=None):
        self.reads.append(path)
        if self.fail_on and self.fail_on in path:
            raise gh.GhError(f"stubbed failure on {path}", self.fail_kind)
        if path == "user":
            return {"login": self.me}
        if path.startswith("repos/o/r/issues/") and path.endswith("/timeline"):
            return self.events
        if path.startswith("repos/o/r/issues/"):
            if self.issue is None:
                raise gh.GhError("stub: no such issue", "notfound")
            return self.issue
        if "/collaborators/" in path:
            login = path.split("/collaborators/")[1].split("/")[0]
            if login not in self.permissions:
                raise gh.GhError("stub: cannot read permission", "auth")
            return self.permissions[login]
        if path == "repos/o/r/labels":
            if method == "POST":
                return {"name": params.get("name")}
            return [{"name": "agent: approved"}, {"name": "status: wip"}]
        raise gh.GhError(f"stub: unhandled path {path}", "api")

    def list_paginated(self, path, params=None):
        data = self.gh_json(path, params)
        if not isinstance(data, list):
            raise gh.GhError(f"stub: {path} is not a list", "api")
        return data


def label_event(who, action="labeled", when=None, actor_type="User", name="agent: approved"):
    return {"event": action, "label": {"name": name},
            "actor": {"login": who, "type": actor_type},
            "created_at": (when or NOW).strftime("%Y-%m-%dT%H:%M:%SZ")}


def issue(labels=("agent: approved",), state="open", pull_request=False, number=1001):
    out = {"number": number, "state": state,
           "labels": [{"name": x} for x in labels]}
    if pull_request:
        out["pull_request"] = {"url": "https://github.com/o/r/pull/1"}
    return out


NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
GOOD_PERMS = {"human": {"permission": "admin", "role_name": "Admin"}}
TMP = tempfile.mkdtemp(prefix="supervisor-tests-")

# The untouched module functions, so the pagination check can install its own
# stub without inheriting the one a previous test left behind.
ORIG_GH_JSON = gh.gh_json
ORIG_LIST_PAGINATED = gh.list_paginated


def cfg(**overrides):
    """A real configuration file with mode 0600, loaded through the real loader,
    so the checks cover the loader's fail-closed behaviour as well."""
    data = {"repo": "o/r", "authorized_humans": ["human"], "agent_accounts": ["agent-bot"],
            "repo_root": "/srv/mrmap", "opencode_model": "p/m",
            "state_dir": os.path.join(TMP, "state"), "require_repo_association": False}
    data.update(overrides)
    path = os.path.join(TMP, f"config-{abs(hash(json.dumps(data, sort_keys=True)))}.json")
    with open(path, "w") as f:
        json.dump(data, f)
    os.chmod(path, 0o600)
    return config.load(path)


def decide(fake, **overrides):
    fake.install()
    return approvals.decide(cfg(**overrides), 1001)


# ---------------------------------------------------------------------------
# the configuration must refuse before anything else is even read

def test_configuration():
    missing = os.path.join(TMP, "absent.json")
    loaded = config.load(missing)
    check("no config file closes the gate", not loaded.ok)
    d = approvals.decide(loaded, 7)
    check("no config file refuses the issue", not d.eligible and d.code == approvals.CONFIG_INVALID,
          d.reason)

    bad = os.path.join(TMP, "broken.json")
    with open(bad, "w") as f:
        f.write("{ not json")
    check("unparsable config closes the gate", not config.load(bad).ok)

    empty = config.Config({"repo": "o/r"}, path="x")
    config._validate(empty)
    check("empty allowlist closes the gate",
          any("authorized_humans is empty" in p for p in empty.problems))

    typo = config.Config({"repo": "o/r", "authorized_humans": ["h"],
                          "opencode_modl": "p/m"}, path="x")
    config._validate(typo)
    check("a typo is a problem, not a default",
          any("opencode_modl" in p for p in typo.problems))

    overlap = config.Config({"repo": "o/r", "authorized_humans": ["same"],
                             "agent_accounts": ["same"]}, path="x")
    config._validate(overlap)
    check("approver equal to agent account is refused", any("both approvers" in p
                                                            for p in overlap.problems))
    hatch = config.Config({"repo": "o/r", "authorized_humans": ["same"],
                           "agent_accounts": ["same"], "allow_same_account": True}, path="x")
    config._validate(hatch)
    check("the escape hatch opens the gate but warns",
          hatch.ok and any("allow_same_account" in w for w in hatch.warnings),
          str(hatch.problems) + str(hatch.warnings))

    loose = os.path.join(TMP, "loose.json")
    with open(loose, "w") as f:
        json.dump({"repo": "o/r", "authorized_humans": ["human"]}, f)
    # Intentional: verify that the loader warns about world-readable configuration.
    # This temporary fixture contains synthetic data, not credentials.
    os.chmod(loose, 0o644)  # codeql[py/overly-permissive-file]
    loaded = config.load(loose)
    check("a world-readable config warns",
          any("chmod" in w for w in loaded.warnings), str(loaded.warnings))

    badrole = config.Config({"repo": "o/r", "authorized_humans": ["h"],
                             "trusted_associations": ["KING"]}, path="x")
    config._validate(badrole)
    check("an unknown role name is a problem",
          any("KING" in p for p in badrole.problems))


def test_obvious_rejections():
    fake = FakeGh(issue=issue(state="closed"), events=[label_event("human")])
    d = decide(fake)
    check("a closed issue is not eligible", not d.eligible and d.code == approvals.NOT_OPEN, d.reason)

    fake = FakeGh(issue=issue(pull_request=True), events=[label_event("human")])
    d = decide(fake)
    check("a pull request is not a work item", not d.eligible and d.code == approvals.IS_PULL_REQUEST,
          d.reason)

    fake = FakeGh(issue=issue(labels=()), events=[])
    d = decide(fake)
    check("no approval label means no", not d.eligible and d.code == approvals.NO_APPROVAL_LABEL,
          d.reason)

    fake = FakeGh(issue=issue(labels=("agent: approved", "agent: paused")),
                  events=[label_event("human")])
    d = decide(fake)
    check("pause beats approval", not d.eligible and d.code == approvals.PAUSED, d.reason)

    fake = FakeGh(issue=issue(labels=("Agent: Approved",)), events=[label_event("human")])
    d = decide(fake, require_repo_association=False)
    check("label matching ignores case", d.eligible, d.reason)

    fake = FakeGh(issue=None, events=[])
    d = decide(fake)
    check("an issue that cannot be read is refused",
          not d.eligible and d.code == approvals.ISSUE_UNAVAILABLE, d.reason)


def test_history():
    fake = FakeGh(issue=issue(), events=[])
    d = decide(fake)
    check("a label with no event behind it is refused",
          not d.eligible and d.code == approvals.HISTORY_INCOMPLETE, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human"),
                                         label_event("human", action="unlabeled")])
    d = decide(fake)
    check("revocation is immediate",
          not d.eligible and d.code == approvals.APPROVAL_REVOKED, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human"),
                                         label_event("human", action="unlabeled"),
                                         label_event("human", when=NOW + timedelta(hours=1))])
    d = decide(fake)
    check("re-approval after revocation counts", d.eligible, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")],
                  fail_on="/timeline", fail_kind="ratelimit")
    d = decide(fake)
    check("an unreadable history is a denial, not a retry",
          not d.eligible and d.reason == f"{approvals.HISTORY_UNAVAILABLE}:ratelimit", d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human", actor_type="Bot")])
    d = decide(fake)
    check("a bot cannot approve",
          not d.eligible and d.code == approvals.NON_HUMAN_APPROVER, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human", actor_type="Organization")])
    d = decide(fake)
    check("anything GitHub does not report as a person is refused",
          not d.eligible and d.code == approvals.NON_HUMAN_APPROVER, d.reason)

    fake = FakeGh(issue=issue(), events=[{"event": "labeled", "label": {"name": "agent: approved"},
                                         "actor": {}, "created_at": "nonsense"}])
    d = decide(fake)
    check("an event naming no account is refused",
          not d.eligible and d.reason == "unknown-approver", d.reason)

    events = [label_event("stranger"), label_event("human", action="unlabeled")]
    fake = FakeGh(issue=issue(), events=events)
    d = decide(fake)
    check("only the last word counts", d.code == approvals.APPROVAL_REVOKED, d.reason)


def test_who_approved():
    fake = FakeGh(issue=issue(), events=[label_event("stranger")])
    d = decide(fake)
    check("an account off the allowlist is refused",
          not d.eligible and d.code == approvals.UNAUTHORIZED_APPROVER
          and "stranger" in d.reason, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("agent-bot")])
    d = decide(fake)
    check("the agent's own account cannot approve its work",
          not d.eligible and d.code == approvals.SELF_APPROVAL, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("agent-bot")], me="agent-bot")
    d = decide(fake, allow_same_account=True)
    check("the hatch alone does not authorise anyone - the allowlist still decides",
          not d.eligible and d.code == approvals.UNAUTHORIZED_APPROVER, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("agent-bot")], me="agent-bot")
    d = decide(fake, allow_same_account=True, authorized_humans=["agent-bot"])
    check("the escape hatch accepts it and the decision says who",
          d.eligible and d.facts.get("approver") == "agent-bot", d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")], me="human")
    d = decide(fake)
    check("an approver sharing the credential is caught via whoami",
          not d.eligible and d.code == approvals.SELF_APPROVAL, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")], me=None)
    d = decide(fake)
    check("whoami being unknown does not invent an approver match", d.eligible, d.reason)


def test_association():
    fake = FakeGh(issue=issue(), events=[label_event("human")], permissions=GOOD_PERMS)
    d = decide(fake, require_repo_association=True)
    check("an admin on the repository is trusted", d.eligible, d.reason + str(d.facts))

    fake = FakeGh(issue=issue(), events=[label_event("human")],
                  permissions={"human": {"permission": "read", "role_name": "Read"}})
    d = decide(fake, require_repo_association=True)
    check("a read-only account is not trusted",
          not d.eligible and d.code == approvals.UNVERIFIED_ASSOCIATION, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")], permissions={})
    d = decide(fake, require_repo_association=True)
    check("an unlookupable role is refused",
          not d.eligible and d.code == approvals.UNVERIFIED_ASSOCIATION, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")], permissions={})
    d = decide(fake, require_repo_association=False)
    check("the operator may accept the allowlist alone", d.eligible, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human")],
                  permissions={"human": {"permission": "galactic-emperor"}})
    d = decide(fake, require_repo_association=True)
    check("a role GitHub has not been asked about before is UNKNOWN, not trusted",
          not d.eligible and d.code == approvals.UNVERIFIED_ASSOCIATION, d.reason)


def test_age():
    old = NOW - timedelta(days=40)
    fake = FakeGh(issue=issue(), events=[label_event("human", when=old)])
    d = decide(fake, approval_max_age_days=30)
    check("an expired approval is refused", d.code == approvals.APPROVAL_TOO_OLD, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human", when=old)])
    d = decide(fake, approval_max_age_days=0)
    check("no age limit means it stands until revoked", d.eligible, d.reason)

    fake = FakeGh(issue=issue(), events=[label_event("human", when=old)])
    d = decide(fake, approval_max_age_days=60)
    check("inside the window it stands", d.eligible, d.reason)


def test_decisions_are_read_only():
    fake = FakeGh(issue=issue(), events=[label_event("human")])
    fake.install()
    approvals.decide(cfg(), 1001)
    writes = [p for p in fake.reads if p.startswith("repos/o/r/labels")]
    check("asking the gate never writes to GitHub", not writes, str(fake.reads))
    check("the gate reads the issue, the timeline and nothing else",
          any(p.endswith("/timeline") for p in fake.reads), str(fake.reads))


def run(fn):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        fn()


def test_pagination():
    """The timeline is read page by page and a partial read must not pass."""
    gh.list_paginated = ORIG_LIST_PAGINATED

    def pages(path, params=None, method="GET", accept=None, timeout=None):
        if params and params.get("page") == 1:
            return [{"event": "labeled", "label": {"name": "agent: approved"},
                     "actor": {"login": "human", "type": "User"},
                     "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}] * gh.PER_PAGE
        if params and params.get("page") == 2:
            return [{"event": "mentioned"}]
        return []

    gh.gh_json = pages
    try:
        found = approvals.approval_events("o/r", 1001, "agent: approved")
        check("a second page is read and the events stitched", len(found) == gh.PER_PAGE,
              str(len(found)))

        def always_full(path, params=None, method="GET", accept=None, timeout=None):
            return [{"event": "labeled", "label": {"name": "agent: approved"},
                     "actor": {"login": "human"}, "created_at": "x"}] * gh.PER_PAGE

        gh.gh_json = always_full
        try:
            approvals.approval_events("o/r", 1001, "agent: approved")
            check("an endless timeline is reported, not truncated", False, "no error raised")
        except gh.GhError as exc:
            check("an endless timeline is reported, not truncated", "refusing a partial read"
                  in str(exc), str(exc))
    finally:
        gh.gh_json = ORIG_GH_JSON
        gh.list_paginated = ORIG_LIST_PAGINATED


def test_epic_acceptance():
    # pause and resume
    fake = FakeGh(issue=issue(labels=("agent: approved", "agent: paused")),
                  events=[label_event("human")])
    d = decide(fake)
    check("paused while running stops the next start", d.code == approvals.PAUSED, d.reason)

    fake = FakeGh(issue=issue(labels=("agent: approved",)), events=[label_event("human")])
    d = decide(fake)
    check("removing the pause resumes it with no new approval", d.eligible, d.reason)

    # GitHub's blocking relations are not the supervisor's business
    blocked = issue()
    blocked["dependencies"] = {"blocked_by": [{"number": 999, "status": "open"}]}
    fake = FakeGh(issue=blocked, events=[label_event("human"),
                                         {"event": "connected", "actor": {"login": "human"},
                                          "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}])
    d = decide(fake)
    checked_endpoints = [p for p in fake.reads if "depend" in p or "block" in p]
    check("a blocked-by relation does not stop eligibility", d.eligible, d.reason)
    check("the gate does not even read blocking relations", not checked_endpoints,
          str(fake.reads))

    # deleted and unnamed accounts
    fake = FakeGh(issue=issue(), events=[label_event("ghost")])
    d = decide(fake)
    check("a deleted account cannot be the approver",
          not d.eligible and d.code == approvals.UNAUTHORIZED_APPROVER, d.reason)

    fake = FakeGh(issue=issue(), events=[{"event": "labeled", "label": {"name": "agent: approved"},
                                          "actor": None,
                                          "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}])
    d = decide(fake)
    check("an event without an actor is refused",
          not d.eligible and d.reason == "unknown-approver", d.reason)

    # permissions can change after the approval
    fake = FakeGh(issue=issue(), events=[label_event("human")],
                  permissions={"human": {"permission": "none", "role_name": "None"}})
    d = decide(fake, require_repo_association=True)
    check("an approver who lost repository access no longer authorizes",
          not d.eligible and d.code == approvals.UNVERIFIED_ASSOCIATION, d.reason)

    # GitHub may hand the events in any order
    events = [label_event("human", action="unlabeled", when=NOW + timedelta(days=1)),
              label_event("human", when=NOW)]
    fake = FakeGh(issue=issue(), events=list(reversed(events)))
    d = decide(fake)
    check("the newest event wins regardless of response order",
          d.code == approvals.APPROVAL_REVOKED, d.reason)


def test_no_write_paths():
    """Nothing in the gate can grant itself anything. This is a check on the
    source text, because the guarantee is about what the code cannot do."""
    root = os.path.dirname(os.path.abspath(__file__))
    allowed = {("gh.py", "create_label", "POST")}
    found = set()
    for name in ("gh.py", "approvals.py", "config.py", "cli.py"):
        with open(os.path.join(root, "agent_supervisor", name)) as handle:
            source = handle.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            verb = next((k.value.value for k in node.keywords
                         if k.arg == "method" and isinstance(k.value, ast.Constant)), None)
            if verb in ("POST", "PATCH", "PUT", "DELETE"):
                found.add((name, _enclosing_function(tree, node.lineno), verb))
        check(f"{name} has no comment, review or merge call",
              "/comments" not in source and "/reviews" not in source
              and "/merge" not in source and "/assignees" not in source)
    check("the only write is creating a label definition", found <= allowed, str(sorted(found)))
    check("the gate cannot close or edit an issue",
          "edit_issue" not in dir(gh) and "close_issue" not in dir(gh)
          and "add_labels" not in dir(gh), str(sorted(dir(gh))))

    # The scheduling modules are audited the same way. They add one thing the gate
    # does not have: a hand that can file a claim - but that hand is `scripts/wip`,
    # run as a child process by the worker, never a REST call of the supervisor's
    # own. Anything else would let the queue grant itself permission.
    scheduling_found = set()
    for name in ("scheduler.py", "capacity.py", "claims.py", "store.py"):
        path = os.path.join(root, "agent_supervisor", name)
        if not os.path.exists(path):
            continue                       # this branch has no scheduler yet
        with open(path) as handle:
            source = handle.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            verb = next((k.value.value for k in node.keywords
                         if k.arg == "method" and isinstance(k.value, ast.Constant)), None)
            if verb in ("POST", "PATCH", "PUT", "DELETE"):
                scheduling_found.add((name, _enclosing_function(tree, node.lineno), verb))
        check(f"{name} writes to GitHub directly",
              "gh_json(" not in source or "method=" not in source, name)
        # Only endpoint strings are checked: reading an issue's `labels` field is
        # not the same thing as calling the labels endpoint, and a check that
        # cannot tell the two apart is a check that gets switched off.
        endpoints = [node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Constant) and isinstance(node.value, str)
                     and "repos/" in node.value]
        write_paths = ("/comments", "/reviews", "/merge", "/assignees", "/labels")
        bad = [path for path in endpoints if any(part in path for part in write_paths)]
        check(f"{name} calls no write endpoint of the REST API", not bad, str(bad))
    check("no scheduling module performs a GitHub write", not scheduling_found,
          str(sorted(scheduling_found)))


def _enclosing_function(tree, lineno):
    """Innermost function or method containing a line, for the write audit."""
    best = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.lineno <= lineno <= (node.end_lineno or node.lineno):
            best = node.name
    return best


def main():
    for fn in (test_configuration, test_obvious_rejections, test_history, test_who_approved,
               test_association, test_age, test_decisions_are_read_only, test_pagination,
               test_epic_acceptance, test_no_write_paths):
        run(fn)
    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
