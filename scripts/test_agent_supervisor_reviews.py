"""Offline regression checks for the review watcher of the agent supervisor (#1062).

Run from the repository root: python3 scripts/test_agent_supervisor_reviews.py
Exit code 0 means every check passed. Needs no ``gh``, no network, no docker and no
OpenCode: every GitHub read - REST and GraphQL - is a stub in this file, the worker
is a stub that records what it was told, and the claim board is a stub that records
the questions it was asked.

The acceptance of #1062 has four halves, and the checks below are the ways each of
them breaks:

*   *only a configured reviewer directs changes* - so there are checks for a bot
    with a collaborator's role, a stranger, an unreadable role, and the supervisor's
    own machine comments on the pull request;
*   *feedback is answered once, and still once after a restart* - so there are
    checks for a repeat pass, a new process over the same state file, an edited
    comment, a re-opened thread and a deleted comment;
*   *ambiguous feedback and reserved acts reach a human instead of a push* - so
    there are checks for "go ahead and merge", for a changes-requested review that
    names nothing, for a question that failed to post, and for the ordinary mix of
    code feedback and a reserved ask inside one review;
*   *a human's thread stays open* - so there is a check that no write call, REST or
    GraphQL, is reachable from the module at all.
"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import gh                                       # noqa: E402
from agent_supervisor.gh import GhError                               # noqa: E402
from agent_supervisor.config import load as load_config               # noqa: E402
from agent_supervisor.reviews import (Reviews, is_bot,                # noqa: E402
                                      privileged_ask)
from agent_supervisor.runner import StartError                        # noqa: E402
from agent_supervisor.store import Store                              # noqa: E402

# The real helpers, captured before any check replaces them with a stub. The point
# is to assert a property of the shipped code, not of its replacement.
REAL_GRAPHQL = gh.graphql

PASS = FAIL = 0
FAILURES = []
TMP = tempfile.mkdtemp(prefix="supervisor-review-tests-")
OWNER = "o"
REPO = "o/r"
HEAD = "abc123def456abc123def456abc123def456abc1"
NEW_HEAD = "9999999999999999999999999999999999999999"
BASE = 1793000000                        # a fixed "now", so the debounce is testable
DEBOUNCE = 300


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


def iso(offset=0):
    """A GitHub-shaped timestamp, so elapsed time can be tested without waiting."""
    return datetime.fromtimestamp(BASE + offset, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# stubs

class FakeGh:
    """Answers every read the watcher makes - REST and GraphQL - and records each
    one, so "this module cannot write to GitHub" is a checked fact."""

    def __init__(self):
        self.prs = {}                     # number -> pull request payload
        self.branch_prs = {}              # "o:branch" -> [payload]
        self.reviews = {}                 # pr -> [review payload]
        self.inline = {}                  # pr -> [review comment payload]
        self.comments = {}                # pr -> [issue comment payload]
        self.threads = {}                 # pr -> [review thread payload]
        self.roles = {}                   # login -> permission
        self.reads = []                   # (path, params, method)
        self.graphql_calls = []
        self.fail_read = set()            # path fragments that must raise
        self.fail_graphql = False

    # -- seeding

    def pr(self, number, branch, sha=HEAD, state="open"):
        payload = {"number": number, "state": state, "head": {"sha": sha},
                   "mergeable_state": "clean",
                   "html_url": f"https://github.com/{REPO}/pull/{number}"}
        self.prs[number] = payload
        self.branch_prs.setdefault(f"{OWNER}:{branch}", []).append(payload)
        return payload

    def review(self, pr, login, state="CHANGES_REQUESTED", body="please fix", rid=500,
               at=0, account_type="User"):
        payload = {"id": rid, "state": state, "body": body, "submitted_at": iso(at),
                   "html_url": f"https://github.com/{REPO}/pull/{pr}#{rid}",
                   "user": {"login": login, "type": account_type}}
        self.reviews.setdefault(pr, []).append(payload)
        return payload

    def note(self, pr, login, path="backend/registry/views.py", line=12, body="typo",
             cid=600, review_id=None, at=0, hunk="+ a line\n- b line",
             account_type="User"):
        payload = {"id": cid, "path": path, "line": line, "original_line": line,
                   "body": body, "diff_hunk": hunk, "pull_request_review_id": review_id,
                   "created_at": iso(at), "updated_at": iso(at),
                   "html_url": f"https://github.com/{REPO}/pull/{pr}#{cid}",
                   "user": {"login": login, "type": account_type}}
        self.inline.setdefault(pr, []).append(payload)
        return payload

    def comment(self, pr, login, body="one more thing", cid=700, at=0,
                account_type="User"):
        payload = {"id": cid, "body": body, "created_at": iso(at), "updated_at": iso(at),
                   "html_url": f"https://github.com/{REPO}/pull/{pr}#discussion_{cid}",
                   "user": {"login": login, "type": account_type}}
        self.comments.setdefault(pr, []).append(payload)
        return payload

    def thread(self, pr, comment_ids, tid="PRRT_thread_1", resolved=False):
        """A review thread: the unit that carries isResolved, and GraphQL only."""
        self.threads.setdefault(pr, []).append(
            {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "a.py",
             "comments": {"nodes": [{"databaseId": one} for one in comment_ids]}})

    def role(self, login, permission):
        self.roles[login] = permission

    # -- the reads

    def gh_json(self, path, params=None, method="GET", accept=None, timeout=None):
        self.reads.append((path, dict(params or {}), method))
        for fragment in self.fail_read:
            if fragment in path:
                raise GhError(f"stub: cannot read {path}", "network")
        if path.endswith("/permission"):
            login = path.split("/")[4]
            if login not in self.roles:
                raise GhError("stub: the permission endpoint needs push access", "notfound")
            return {"permission": self.roles[login]}
        if path.endswith("/reviews"):
            return self.reviews.get(int(path.split("/")[4]), [])
        if path.endswith("/comments") and "/pulls/" in path:
            return self.inline.get(int(path.split("/")[4]), [])
        if path.endswith("/comments") and "/issues/" in path:
            return self.comments.get(int(path.split("/")[4]), [])
        if path.endswith("/pulls"):
            return self.branch_prs.get(params.get("head"), [])
        if "/pulls/" in path:
            return self.prs[int(path.rsplit("/", 1)[1])]
        raise GhError(f"stub: unhandled {path}", "api")

    def graphql(self, query, variables=None, timeout=None):
        if "mutation" in query.lower():
            raise GhError("stub: a mutation was refused", "api")
        self.graphql_calls.append((query, dict(variables or {})))
        if self.fail_graphql:
            raise GhError("stub: graphql unreachable", "network")
        number = (variables or {}).get("number")
        threads = {"pageInfo": {"hasNextPage": False, "endCursor": None},
                   "nodes": self.threads.get(number, [])}
        return {"repository": {"pullRequest": {"reviewThreads": threads}}}


class FakeRunner:
    """A worker that remembers what it was woken up with."""

    def __init__(self, store, alive=False, raises=None):
        self.store = store
        self.alive_flag = alive
        self.raises = raises
        self.resumed = []                        # [(issue, prompt)]

    def alive(self, lease):
        return self.alive_flag

    def resume(self, issue, prompt=None):
        self.resumed.append((issue, prompt))
        if self.raises:
            raise self.raises
        return {"pid": 5000 + len(self.resumed), "pgid": 5000 + len(self.resumed),
                "session": f"mrmap-{issue}", "worktree": "/srv/wt", "log": "/tmp/log"}


class FakeWip:
    """The board's question flow, recorded instead of posted.

    ``is_machine_comment`` is the rule from ``scripts/wip`` in miniature: the
    watcher has to filter the supervisor's own claim, question and board comments
    out of the feedback, or it reads its own question back as a review.
    """

    def __init__(self, raises=None):
        self.asked = []                          # [(issue, question)]
        self.raises = raises

    def cmd_ask(self, question, issue_arg=None, force=False):
        self.asked.append((issue_arg, question))
        if self.raises:
            raise self.raises

    @staticmethod
    def is_machine_comment(comment):
        body = comment.get("body") or ""
        return ("agent-claim" in body or "agent-question" in body
                or "Agent Work Board" in body)


class FakeClaims:
    def __init__(self, wip):
        self.wip = wip


_CASES = [0]


def harness(**overrides):
    """A configuration file, so the CLI commands can be run over the same state."""
    data = {"repo": REPO, "authorized_humans": ["operator"], "state_dir": TMP,
            "repo_root": "/srv/mrmap", "opencode_model": "p/m",
            "review_response_attempts": 3, "review_debounce_seconds": DEBOUNCE}
    data.update(overrides)
    path = os.path.join(TMP, f"cfg-{abs(hash(json.dumps(data, sort_keys=True)))}.json")
    with open(path, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)
    return load_config(path)


def make(fake=None, alive=False, resume_raises=None, ask_raises=None, **cfg_overrides):
    """One case: a config, a state file in the directory that config names, and
    stubs for every outside world it could touch.

    The config and the state file belong together because the CLI checks run the
    real command line, which finds its state through the configuration - two
    unrelated files would make those checks test nothing.
    """
    _CASES[0] += 1
    case = os.path.join(TMP, f"case-{_CASES[0]}")
    os.makedirs(case, exist_ok=True)
    cfg = harness(state_dir=case, **cfg_overrides)
    fake = fake or FakeGh()
    gh.gh_json = fake.gh_json
    gh.graphql = fake.graphql
    store = Store(os.path.join(case, "supervisor.sqlite3"))
    wip = FakeWip(raises=ask_raises)
    runner = FakeRunner(store, alive=alive, raises=resume_raises)
    return Reviews(cfg, store=store, runner=runner, claims=FakeClaims(wip)), fake, runner, wip


def lease(store, issue=7, branch="feature/issue-7-thing", state="finished"):
    """A lease in the shape the runner leaves one behind: worktree, branch, session."""
    store.claim_lease(issue, REPO, "stack", branch=branch,
                      worktree=f"/srv/wt/issue-{issue}", project=f"mrmap-agent-{issue}-1")
    store.update_lease(issue, state="running", session=f"mrmap-{issue}", pid=1, pgid=1)
    store.release_lease(issue, state=state, detail="pull request opened")
    return store.lease(issue)


def seed(fake, store, issue=7, pr=70, branch="feature/issue-7-thing", reviewer="maintainer"):
    """The ordinary situation: a worker finished, its pull request open, and one
    reviewer who holds a role the configuration trusts."""
    lease(store, issue=issue, branch=branch)
    fake.pr(pr, branch)
    fake.role(reviewer, "write")
    return issue, pr


# ---------------------------------------------------------------------------
# who may direct the worker

def test_who_may_direct():
    mon, fake, _, _ = make()
    fake.role("maintainer", "write")
    fake.role("owner", "admin")
    fake.role("passer-by", "read")
    fake.role("stranger", "none")
    fake.role("dependabot[bot]", "write")
    check("a reviewer with write access directs work",
          mon.may_direct("maintainer")[0], mon.may_direct("maintainer")[1])
    check("an owner directs work", mon.may_direct("owner")[0])
    check("the operator's allowlist is enough on its own", mon.may_direct("operator")[0])
    check("read access alone does not direct work", not mon.may_direct("passer-by")[0])
    check("a stranger does not direct work", not mon.may_direct("stranger")[0])
    check("a bot does not direct work even with write access",
          not mon.may_direct("dependabot[bot]")[0], "the role says collaborator")
    check("an account GitHub will not answer for does not direct work",
          not mon.may_direct("ghost")[0])
    check("no author at all is not feedback", not mon.may_direct("")[0])
    check("the [bot] suffix is automation", is_bot("dependabot[bot]"))
    check("the -bot suffix is automation", is_bot("mrmap-bot"))
    check("a GraphQL Bot author is automation", is_bot("app", "Bot"))
    check("a person is not automation", not is_bot("Maintainer"))


def test_what_counts_as_a_reserved_ask():
    check("a review about code is not a reserved ask",
          privileged_ask("please rename this variable and add a test") == "")
    check("asking to merge is", "merge" in privileged_ask("looks good, go ahead and merge"))
    check("asking to approve is", "approve" in privileged_ask("please approve it"))
    check("asking to resolve threads is",
          "resolve" in privileged_ask("resolve the thread when done"))
    check("asking to force push is", "rewrite" in privileged_ask("force push this"))
    check("asking to change CI is", "protection" in privileged_ask("just disable the check"))
    check("asking for access is", "access" in privileged_ask("add me as a collaborator"))
    check("asking for a secret is", "secret" in privileged_ask("commit the token here"))
    check("the word merge in code discussion is not",
          privileged_ask("merge these two helpers into one function") == "")


# ---------------------------------------------------------------------------
# feedback that is work

def test_a_requested_change_wakes_one_worker():
    mon, fake, runner, wip = make()
    store = mon.store
    issue, pr = seed(fake, store)
    fake.review(pr, "maintainer", body="rename the field and cover it", rid=501, at=-60)
    fake.note(pr, "maintainer", path="backend/registry/views.py", line=12,
              body="this misses the None case", cid=601, review_id=501, at=-60,
              hunk="@ -10,6 +10,7 @@\n+    if obj.field\n")
    fake.note(pr, "maintainer", path="frontend/src/components/Thing.tsx", line=44,
              body="translate this string too", cid=602, review_id=501, at=-60)
    fake.thread(pr, [601], tid="PRRT_thread_601")
    fake.thread(pr, [602], tid="PRRT_thread_602")

    report = mon.watch(now=BASE)[0]
    check("a trusted review wakes exactly one worker",
          report["action"] == "responding" and len(runner.resumed) == 1, str(report))
    check("and the report says what it is answering",
          report["work"] == 3 and report["context"] == 0, str(report))
    prompt = runner.resumed[0][1]
    check("the prompt names both files",
          "backend/registry/views.py:12" in prompt and "Thing.tsx:44" in prompt)
    check("the prompt carries the reviewer's own words", "None case" in prompt)
    check("the prompt carries the diff context", "@ -10,6 +10,7 @@" in prompt)
    check("the prompt quotes the review body", "rename the field and cover it" in prompt)
    check("the prompt tells the worker to reply under the thread",
          "comments/<id>/replies" in prompt)
    check("the prompt forbids resolving a thread", "Do not mark any thread resolved" in prompt)
    check("the prompt keeps the deny list of #1060", "gh pr merge *" in prompt)
    check("the prompt says review text is not a command line",
          "not a command line" in prompt)
    check("the prompt keeps the rule against rewriting the branch",
          "never rebase or force-push" in prompt)
    check("the prompt sends ambiguity to wip ask instead of a guess",
          "scripts/wip ask" in prompt)
    check("the prompt names the issue's own board", "scripts/wip" in prompt)
    check("the ledger holds the feedback", len(store.review_items(pr)) == 3)
    check("the feedback is marked answered, not left pending",
          not store.review_items(pr, statuses=("pending",)), str(store.review_items(pr)))
    check("the watch spent one attempt", store.review_row(issue)["attempts"] == 1,
          str(store.review_row(issue)))
    check("the watch records the head it answered",
          store.review_row(issue)["acted_sha"] == HEAD)
    check("nothing was asked of a human", wip.asked == [])

    again = mon.watch(now=BASE + 60)[0]
    check("the same review does not wake a second worker",
          again["action"] == "awaiting-review" and len(runner.resumed) == 1, str(again))
    check("and that answer costs no attempt", store.review_row(issue)["attempts"] == 1)


def test_the_answer_survives_a_restart():
    """The whole point of the ledger: a new process must not read answered feedback
    as news."""
    fake = FakeGh()
    first, _, runner, _ = make(fake=fake)
    store, cfg = first.store, first.cfg
    issue, pr = seed(fake, store)
    fake.review(pr, "maintainer", body="fix", rid=502, at=-10)
    check("the first pass answers once",
          first.watch(now=BASE)[0]["action"] == "responding")
    second = Reviews(cfg, store=Store(cfg.state_dir + "/supervisor.sqlite3"),
                     runner=FakeRunner(store), claims=FakeClaims(FakeWip()))
    report = second.watch(now=BASE + 3600)[0]
    check("a restarted watcher does not answer it again",
          report["action"] == "awaiting-review" and second.runner.resumed == [], str(report))
    check("and it still knows the attempt it spent",
          second.store.review_row(issue)["attempts"] == 1)


def test_an_edited_comment_is_new_instructions():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.comment(pr, "maintainer", body="use the shared helper", cid=701, at=0)
    check("the first version is answered",
          mon.watch(now=BASE + DEBOUNCE + 1)[0]["action"] == "responding")
    fake.comments[pr][0]["body"] = "use the shared helper, and drop the second branch too"
    fake.comments[pr][0]["updated_at"] = iso(10)
    report = mon.watch(now=BASE + DEBOUNCE + 200)[0]
    check("an edit under the same id wakes the worker again",
          report["action"] == "responding" and len(runner.resumed) == 2, str(report))
    check("the new wording reaches the prompt", "drop the second branch" in
          runner.resumed[1][1])
    mon.watch(now=BASE + DEBOUNCE + 400)
    check("and the unchanged text is not work a third time", len(runner.resumed) == 2)


def test_an_account_that_becomes_trusted_is_not_ignored_forever():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.comment(pr, "newcomer", body="please rename this", cid=702, at=0)
    report = mon.watch(now=BASE + DEBOUNCE + 1)[0]
    check("a stranger's note is context, not work",
          report["action"] == "context" and runner.resumed == [], str(report))
    check("it is still recorded", mon.store.review_items(pr, statuses=("context",)))
    fake.role("newcomer", "write")
    report = mon.watch(now=BASE + DEBOUNCE + 2)[0]
    check("once the account holds a trusted role its note is work",
          report["action"] == "responding" and len(runner.resumed) == 1, str(report))


def test_the_supervisors_own_comments_are_not_feedback():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.comment(pr, "operator", body="<!-- agent-claim client=host:wt --> working on it",
                 cid=709, at=0)
    fake.comment(pr, "operator", body="<!-- agent-question client=host:wt id=q1 --> CI is red",
                 cid=710, at=0)
    fake.comment(pr, "operator", body="🤖 Agent Work Board\n\n- #7", cid=711, at=0)
    report = mon.watch(now=BASE + DEBOUNCE + 1)[0]
    check("a machine comment on the pull request is not feedback",
          report["items"] == 0 and runner.resumed == [], str(report))


# ---------------------------------------------------------------------------
# feedback that is not the worker's to carry out

def test_reserved_asks_go_to_a_human():
    mon, fake, runner, wip = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="nice - go ahead and merge it", rid=503, at=-10)
    fake.note(pr, "maintainer", body="and resolve the thread", cid=603, review_id=503,
              at=-10)
    fake.thread(pr, [603], tid="PRRT_thread_603")
    report = mon.watch(now=BASE)[0]
    check("a reserved ask never reaches a worker", runner.resumed == [], str(report))
    check("it is reported as escalated", report["action"] == "escalated", str(report))
    check("the question went to the issue, not to the pull request",
          wip.asked and wip.asked[0][0] == issue, str(wip.asked))
    check("the question names what was asked",
          "merge the pull request" in wip.asked[0][1], wip.asked[0][1][:200])
    check("the question says why not", "will not do on its own" in wip.asked[0][1])
    check("the ask is marked so it is not asked twice",
          mon.store.review_items(pr, statuses=("escalated",)), str(report))
    mon.watch(now=BASE + 60)
    check("and the next pass does not ask again", len(wip.asked) == 1)

    mon2, fake2, runner2, wip2 = make()
    issue, pr = seed(fake2, mon2.store)
    fake2.review(pr, "maintainer", body="", state="CHANGES_REQUESTED", rid=504, at=-10)
    report = mon2.watch(now=BASE)[0]
    check("changes requested without naming anything is not a guess",
          report["action"] == "escalated" and runner2.resumed == [], str(report))
    check("and it is asked as an unspecified request",
          "without naming any" in wip2.asked[0][1], wip2.asked[0][1][:200])

    mon3, fake3, runner3, _ = make()
    issue, pr = seed(fake3, mon3.store)
    fake3.review(pr, "maintainer", body="", state="COMMENTED", rid=521, at=-10)
    report = mon3.watch(now=BASE)[0]
    check("an empty COMMENTED review is the inline notes talking, not a question",
          report["action"] == "nothing" and runner3.resumed == [], str(report))


def test_code_and_a_reserved_ask_in_one_review():
    """The common shape: "fix the None case and merge when done". The code is the
    agent's business, the merge is not, and answering one must not swallow the
    other."""
    mon, fake, runner, wip = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="go ahead and merge this once it is green",
                rid=505, at=-10)
    fake.note(pr, "maintainer", body="guard the None case", cid=604, review_id=505,
              at=-10)
    fake.thread(pr, [604], tid="PRRT_thread_604")
    report = mon.watch(now=BASE)[0]
    check("the code feedback is answered",
          runner.resumed != [] and "guard the None case" in runner.resumed[0][1],
          str(report))
    check("the merge ask is escalated in the same pass", len(wip.asked) == 1, str(report))
    check("and the row still reports the response", report["action"] == "responding",
          str(report))
    escalated = mon.store.review_items(pr, statuses=("escalated",))
    check("the escalated item is the review, not the code note",
          [one["github_id"] for one in escalated] == ["505"], str(escalated))


def test_a_failed_question_is_asked_again():
    mon, fake, runner, _ = make(ask_raises=GhError("board unreachable", "network"))
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="merge it", rid=506, at=-10)
    report = mon.watch(now=BASE)[0]
    check("a failed escalation says so", report["action"] == "escalation-failed",
          str(report))
    check("and does not leave the item looking reported",
          not mon.store.review_items(pr, statuses=("escalated",)),
          str(mon.store.review_items(pr)))
    mon.claims.wip = FakeWip()
    mon.watch(now=BASE + 60)
    check("the next pass asks again", len(mon.claims.wip.asked) == 1)


# ---------------------------------------------------------------------------
# threads, deletions, debouncing

def test_a_resolved_thread_is_not_work():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="", state="COMMENTED", rid=507, at=-10)
    fake.note(pr, "maintainer", body="guard None", cid=605, review_id=507, at=-10)
    fake.thread(pr, [605], tid="PRRT_thread_605", resolved=True)
    report = mon.watch(now=BASE)[0]
    check("a thread the human resolved is settled, not work",
          report["action"] == "nothing" and runner.resumed == [], str(report))
    check("it is recorded as settled", mon.store.review_items(pr, statuses=("settled",)))
    fake.threads[pr][0]["isResolved"] = False
    report = mon.watch(now=BASE + 60)[0]
    check("un-resolving a thread is GitHub's own way of asking again",
          report["action"] == "responding" and len(runner.resumed) == 1, str(report))
    check("and the ledger row was reopened", report.get("reopened") == 1, str(report))


def test_an_unreadable_thread_state_is_not_read_as_resolved():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="two notes", rid=508, at=-10)
    fake.note(pr, "maintainer", body="guard None", cid=606, review_id=508, at=-10)
    fake.fail_graphql = True
    report = mon.watch(now=BASE)[0]
    check("a thread read that failed says so instead of pretending",
          report["threads"] == "unknown", str(report))
    check("and the feedback is treated as open", report["work"] == 2, str(report))
    check("so a human's finding is not dropped", len(runner.resumed) == 1)


def test_a_deleted_comment_stops_being_work():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="two notes", rid=509, at=-10)
    fake.note(pr, "maintainer", body="guard None", cid=607, review_id=509, at=-10)
    fake.thread(pr, [607], tid="PRRT_thread_607")
    check("the review is answered", mon.watch(now=BASE)[0]["action"] == "responding")
    fake.inline[pr] = []
    fake.threads[pr] = []
    report = mon.watch(now=BASE + 60)[0]
    check("a comment the reviewer deleted does not stay work",
          report["action"] == "awaiting-review", str(report))
    check("the ledger says it went stale", mon.store.review_items(pr, statuses=("stale",)))
    check("and no worker was woken for the deletion", len(runner.resumed) == 1)

    mon2, fake2, runner2, _ = make()
    issue, pr = seed(fake2, mon2.store)
    fake2.comment(pr, "maintainer", body="please rename", cid=703, at=0)
    mon2.watch(now=BASE + 1)[0]
    fake2.comments[pr] = []
    report = mon2.watch(now=BASE + DEBOUNCE + 1)[0]
    check("feedback deleted before it was answered simply drops",
          report["action"] == "nothing" and runner2.resumed == [], str(report))
    check("with a dropped row behind it",
          mon2.store.review_items(pr, statuses=("dropped",)),
          str(mon2.store.review_items(pr)))


def test_standalone_comments_are_debounced():
    """Five comments in two minutes are one conversation, not five cycles."""
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.comment(pr, "maintainer", body="one thing", cid=704, at=0)
    report = mon.watch(now=BASE + 30)[0]
    check("a fresh comment waits out the debounce",
          report["action"] == "debouncing" and runner.resumed == [], str(report))
    fake.comment(pr, "maintainer", body="another thing", cid=705, at=60)
    check("the quiet clock restarts on the newest comment",
          mon.watch(now=BASE + 120)[0]["action"] == "debouncing")
    report = mon.watch(now=BASE + 60 + DEBOUNCE + 1)[0]
    check("once it has been quiet the whole set is answered at once",
          report["action"] == "responding" and len(runner.resumed) == 1
          and report["work"] == 2, str(report))
    check("both comments are in the one prompt",
          "one thing" in runner.resumed[0][1] and "another thing" in runner.resumed[0][1])


def test_a_submitted_review_does_not_wait_for_the_debounce():
    """A review submission is a deliberate act: a human clicked "submit review"."""
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="rename the field", rid=510, at=0)
    report = mon.watch(now=BASE + 5)[0]
    check("a submitted review is acted on without waiting",
          report["action"] == "responding" and len(runner.resumed) == 1, str(report))


def test_the_thread_discussion_reaches_the_worker():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="notes", rid=511, at=-200)
    fake.note(pr, "maintainer", body="use the shared helper here", cid=608,
              review_id=511, at=-200)
    fake.thread(pr, [608], tid="PRRT_thread_608")
    mon.watch(now=BASE - 100)
    fake.note(pr, "maintainer", body="no, I mean the one in extras/", cid=609,
              review_id=511, at=-50)
    fake.thread(pr, [608, 609], tid="PRRT_thread_608")
    mon.watch(now=BASE)
    check("a thread is answered as an exchange, not as isolated remarks",
          len(runner.resumed) == 2 and "earlier in this thread" in runner.resumed[1][1],
          runner.resumed[-1][1][:300] if runner.resumed else "no resume at all")


# ---------------------------------------------------------------------------
# budgets, refusals, unreadable GitHub

def test_budgets_and_a_live_worker():
    mon, fake, runner, _ = make(review_response_attempts=1)
    issue, pr = seed(fake, mon.store)
    fake.comment(pr, "maintainer", body="first note", cid=706, at=0)
    check("the first cycle runs",
          mon.watch(now=BASE + DEBOUNCE + 1)[0]["action"] == "responding")
    fake.comment(pr, "maintainer", body="second note", cid=707, at=DEBOUNCE + 2)
    report = mon.watch(now=BASE + 2 * DEBOUNCE + 10)[0]
    check("the lifetime budget stops the second one", report["action"] == "held",
          str(report))
    check("and says what spent it", "budget spent (1/1" in report["detail"],
          report["detail"])
    check("so no worker started", len(runner.resumed) == 1)

    mon2, fake2, runner2, _ = make(review_response_attempts=0)
    seed(fake2, mon2.store)
    fake2.review(70, "maintainer", body="fix", rid=512, at=-10)
    report = mon2.watch(now=BASE)[0]
    check("a budget of zero means watch and report, never act",
          report["action"] == "held" and runner2.resumed == [], str(report))

    mon3, fake3, runner3, _ = make(alive=True)
    seed(fake3, mon3.store)
    fake3.review(70, "maintainer", body="fix", rid=513, at=-10)
    report = mon3.watch(now=BASE)[0]
    check("a worker that is still running is not resumed twice",
          report["action"] == "held" and "still running" in report["detail"], str(report))


def test_a_resume_that_cannot_happen_is_reported():
    mon, fake, runner, _ = make(resume_raises=StartError("no recorded session"))
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="fix", rid=514, at=-10)
    report = mon.watch(now=BASE)[0]
    check("a refused resume is reported, not swallowed",
          report["action"] == "respond-refused", str(report))
    check("and it costs no attempt", mon.store.review_row(issue)["attempts"] == 0,
          str(mon.store.review_row(issue)))
    check("and the feedback stays pending so it is tried again",
          len(mon.store.review_items(pr, statuses=("pending",))) == 1)


def test_unreadable_github_changes_nothing():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="fix", rid=515, at=-10)
    fake.fail_read.add("/reviews")
    report = mon.watch(now=BASE)[0]
    check("a GitHub that will not answer is not read as no feedback",
          report["action"] == "unreadable" and runner.resumed == [], str(report))
    check("and the watch says it could not read",
          mon.store.review_row(issue)["state"] == "unknown")
    fake.fail_read.clear()
    check("the next pass reads it after all",
          mon.watch(now=BASE + 60)[0]["action"] == "responding")

    mon2, fake2, runner2, _ = make()
    seed(fake2, mon2.store, issue=8, pr=71, branch="feature/issue-8-thing")
    fake2.prs[71]["state"] = "closed"
    report = mon2.watch(now=BASE)[0]
    check("a closed pull request leaves the watch",
          report["action"] == "closed" and runner2.resumed == [], str(report))
    check("and is recorded closed", mon2.store.review_row(8)["state"] == "closed")


def test_only_our_own_pull_requests():
    mon, fake, runner, _ = make()
    report = mon.watch(now=BASE)
    check("a supervisor with no leases follows nothing", report == [], str(report))
    check("so it cannot wake anybody", runner.resumed == [])


# ---------------------------------------------------------------------------
# the module cannot write to GitHub

FORBIDDEN_PATHS = ("/merge", "/merge-queue", "/resolve", "/approve", "/rerun",
                   "/cancel", "/dismiss")


def test_the_watcher_has_no_write_path():
    mon, fake, runner, _ = make()
    issue, pr = seed(fake, mon.store)
    fake.review(pr, "maintainer", body="go ahead and merge this", rid=516, at=-10)
    fake.note(pr, "maintainer", body="and resolve the threads", cid=610,
              review_id=516, at=-10)
    fake.comment(pr, "operator", body="translate this too", cid=708, at=-10)
    mon.watch(now=BASE)
    writes = [one for one in fake.reads if one[2] != "GET"]
    check("every REST call the watcher made was a GET", not writes, str(writes))
    hits = [path for path, _, _ in fake.reads
            if any(fragment in path for fragment in FORBIDDEN_PATHS)]
    check("and none of them touched a write-shaped path", not hits, str(hits))
    check("every GraphQL call the watcher made was a query",
          all("mutation" not in one.lower() for one, _ in fake.graphql_calls)
          and fake.graphql_calls, str(len(fake.graphql_calls)))

    source = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "agent_supervisor", "reviews.py")).read()
    for forbidden in ("gh pr merge", "gh pr review", "gh pr edit", "gh run rerun",
                      'method="POST"', "method='POST'", "-X POST", "/resolve",
                      "resolveReviewThread", "merge-queue", "--admin"):
        check(f"the module contains no {forbidden}", forbidden not in source)
    check("graphql() itself refuses a mutation", _refuses_mutation())
    check("the worker's deny list covers resolving a thread",
          any(one.get("resource") == "gh api *threads*" for one in _deny_list()),
          "config.WORKER_DENY_PERMISSIONS")


def _refuses_mutation():
    try:
        REAL_GRAPHQL("mutation { resolveReviewThread(input: {}) { id } }")
    except GhError as exc:
        return "mutation" in str(exc)
    except Exception:
        return False
    return False


def _deny_list():
    from agent_supervisor import config as config_module

    return config_module.WORKER_DENY_PERMISSIONS


# ---------------------------------------------------------------------------
# the state file's own rules

def test_store_rules():
    store = Store(os.path.join(TMP, "review-store-rules.sqlite3"))
    store.claim_lease(9, REPO, "stack", branch="feature/issue-9-x",
                      worktree="/srv/wt/issue-9", project="mrmap-agent-9-1")
    row = store.track_reviews(9, REPO, 72, HEAD)
    check("tracking a review watch starts at zero attempts", row["attempts"] == 0)
    check("recording feedback the first time says new",
          store.record_review_item(9, REPO, 72, "inline", "1", body="a",
                                   author="m", stamped_at=BASE) == "new")
    check("the same text is not news",
          store.record_review_item(9, REPO, 72, "inline", "1", body="a",
                                   author="m", stamped_at=BASE) == "same")
    check("edited text is news",
          store.record_review_item(9, REPO, 72, "inline", "1", body="a and b",
                                   author="m", stamped_at=BASE + 5) == "changed")
    store.mark_review_items(72, [("inline", "1")], "acted")
    check("answered text stays answered",
          store.record_review_item(9, REPO, 72, "inline", "1", body="a and b",
                                   author="m", stamped_at=BASE + 5) == "same")
    check("context feedback arrives as context",
          store.record_review_item(9, REPO, 72, "comment", "2", status="context",
                                   body="hi", author="x") == "new")
    check("and an author who became trusted promotes it",
          store.record_review_item(9, REPO, 72, "comment", "2", status="context",
                                   body="hi", author="x", trusted=True) == "promoted")
    check("promoted feedback is work now",
          store.review_items(72, statuses=("pending",)), str(store.review_items(72)))
    store.mark_review_items(72, [("comment", "2")], "acted")
    store.mark_review_items(72, [("inline", "1")], "settled")
    check("reopening touches a settled row and nothing else",
          store.reopen_review_items(72, [("inline", "1"), ("comment", "2")]) == 1)
    check("an answered row stays answered",
          len(store.review_items(72, statuses=("acted",))) == 1,
          str(store.review_items(72)))
    store.record_review_item(9, REPO, 72, "comment", "3", body="gone again", author="m")
    gone = store.review_items_gone(REPO, 72, {("inline", "1")})
    check("feedback that vanished goes stale when it was answered and dropped when it "
          "was not",
          sorted(gone) == sorted([("comment", "2", "stale"), ("comment", "3", "dropped")]),
          str(gone))
    check("an unknown item status is refused", _refuses(
        lambda: store.mark_review_items(72, [("inline", "1")], "approved"), ValueError))
    check("an unknown review state is refused",
          _refuses(lambda: store.update_review(9, state="merged"), ValueError))
    check("an unknown review column is refused",
          _refuses(lambda: store.update_review(9, nonsense=1), ValueError))
    check("an unknown item column is refused",
          _refuses(lambda: store.record_review_item(9, REPO, 72, "inline", "3", bogus=1),
                   ValueError))
    store.update_review(9, state="responded", attempts=2, acted_sha=HEAD)
    refreshed = store.track_reviews(9, REPO, 72, NEW_HEAD)
    check("re-tracking keeps the budget spent", refreshed["attempts"] == 2, str(refreshed))
    check("and keeps which head was answered", refreshed["acted_sha"] == HEAD)
    other = store.track_reviews(9, REPO, 73, NEW_HEAD)
    check("a new pull request number is a new subject", other["pr"] == 73, str(other))
    check("but the budget is still the budget", other["attempts"] == 2, str(other))
    check("the review watch shows up in status",
          len(store.status()["reviews"]) == 1, str(store.status()["reviews"]))


def _refuses(call, expected):
    try:
        call()
    except expected:
        return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# what an operator sees

def test_the_operator_commands_show_it():
    from agent_supervisor import cli

    mon, fake, runner, wip = make()
    store, cfg = mon.store, mon.cfg
    issue, pr = seed(fake, store)
    fake.review(pr, "maintainer", body="rename it", rid=517, at=-10)
    fake.note(pr, "maintainer", body="guard None", cid=611, review_id=517, at=-10)
    fake.thread(pr, [611], tid="PRRT_thread_611")

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "watch-reviews", "--dry-run", "--json"])
    try:
        rows = json.loads(out.getvalue())
        parsed = len(rows) == 1 and rows[0]["action"] == "would-respond"
    except ValueError:
        parsed = False
    check("watch-reviews --json is exactly one JSON document the daemon can read",
          parsed and code == 0, out.getvalue()[-200:])

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "watch-reviews", "--dry-run"])
    check("the preview says what it would do", "would-respond" in out.getvalue())
    check("a preview that waits for nobody exits 0", code == 0, str(code))
    check("the preview read only", {one[2] for one in fake.reads} == {"GET"},
          str(fake.reads[-3:]))
    check("and left nothing answered in the ledger",
          not store.review_items(pr, statuses=("acted",)), str(store.review_items(pr)))
    check("the preview asked nobody", wip.asked == [])

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "reviews", "--json"])
    rows = json.loads(out.getvalue())
    check("reviews --json is exactly one JSON document",
          code == 0 and len(rows) == 1 and rows[0]["pr"] == pr, out.getvalue()[:200])
    check("the dry run still recorded the watch",
          rows[0]["state"] == "watching", str(rows[0]))

    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["--config", cfg.path, "reviews"])
    printed = out.getvalue()
    check("reviews lists the watch", f"pr #{pr}" in printed, printed)
    check("and names the feedback still open",
          f"open: review {517} by maintainer" in printed, printed)

    store.update_review(issue, state="waiting-human", detail="1 ask(s) escalated")
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["--config", cfg.path, "status"])
    printed = out.getvalue()
    check("status shows the review watch", "review watch" in printed, printed[-500:])
    check("status names the pull request waiting for a human",
          "waiting for a human: #7" in printed, printed[-500:])


def test_the_exit_codes_are_the_timer_contract():
    """#1063's daemon reads the exit code, so the cases have to be distinguishable
    without parsing prose."""
    from agent_supervisor import cli

    empty, _, _, _ = make()
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", empty.cfg.path, "watch-reviews"])
    check("nothing waiting exits 0", code == 0, out.getvalue()[-200:])

    held, fake, runner, _ = make(review_response_attempts=0)
    seed(fake, held.store)
    fake.review(70, "maintainer", body="rename it", rid=520, at=-10)
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", held.cfg.path, "watch-reviews"])
    check("feedback held by a budget exits 1", code == 1, out.getvalue()[-200:])
    check("and still started no worker", runner.resumed == [])

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", held.cfg.path, "watch-reviews", "--json"])
    try:
        rows = json.loads(out.getvalue())
        parsed = len(rows) == 1 and rows[0]["action"] == "held"
    except ValueError:
        parsed = False
    check("a held row still answers with parseable JSON and exit 1",
          parsed and code == 1, out.getvalue()[-200:])


# ---------------------------------------------------------------------------

def main():
    test_who_may_direct()
    test_what_counts_as_a_reserved_ask()
    test_a_requested_change_wakes_one_worker()
    test_the_answer_survives_a_restart()
    test_an_edited_comment_is_new_instructions()
    test_an_account_that_becomes_trusted_is_not_ignored_forever()
    test_the_supervisors_own_comments_are_not_feedback()
    test_reserved_asks_go_to_a_human()
    test_code_and_a_reserved_ask_in_one_review()
    test_a_failed_question_is_asked_again()
    test_a_resolved_thread_is_not_work()
    test_an_unreadable_thread_state_is_not_read_as_resolved()
    test_a_deleted_comment_stops_being_work()
    test_standalone_comments_are_debounced()
    test_a_submitted_review_does_not_wait_for_the_debounce()
    test_the_thread_discussion_reaches_the_worker()
    test_budgets_and_a_live_worker()
    test_a_resume_that_cannot_happen_is_reported()
    test_unreadable_github_changes_nothing()
    test_only_our_own_pull_requests()
    test_the_watcher_has_no_write_path()
    test_store_rules()
    test_the_operator_commands_show_it()
    test_the_exit_codes_are_the_timer_contract()

    print(f"\n{PASS} passed, {FAIL} failed")
    for one in FAILURES:
        print(f"  FAIL  {one}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
