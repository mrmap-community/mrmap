"""Offline regression checks for scripts/next_eligible.py.

Run from the repository root: python3 scripts/test_next_eligible.py
Exit code 0 means every check passed.

The selector decides what may be started on, so the checks that matter are the
rejections: who applied the approval, whether a blocker was really
implemented, who already claims the issue, and whether the tool fails CLOSED
when GitHub cannot be read. Every gh and git call is answered by the fixture
below, so this needs no `gh`, no token and no network, and cannot touch a real
repository or a real branch.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    "next_eligible", importlib.machinery.SourceFileLoader(
        "next_eligible", os.path.join(HERE, "next_eligible.py")))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
wip = m.load_wip()
# A developer's own allowlist must not decide what this suite sees; the one
# check of the environment variable sets it explicitly and restores this.
os.environ.pop(m.APPROVERS_ENV, None)


class Fixture:
    """The whole GitHub and git state one run of the selector observes."""

    def __init__(self, order=()):
        self.repo = "o/r"
        self.epic = 1256
        self.base = "develop"
        self.order = list(order)              # sub-issue listing order
        self.state = {n: "OPEN" for n in order}
        self.labels = {n: [] for n in order}
        self.applied = {}                     # issue -> (login, __typename)
        self.unlabeled_after = set()          # issues whose last event removes it
        self.blockers = {}                    # issue -> [blocker numbers]
        self.bstate = {}                      # blocker -> (state, stateReason)
        self.bclosing = {}                    # blocker -> [PR numbers that closed it]
        self.pulls = {}                       # PR -> REST view dict
        self.open_prs = []                    # open PRs: number, head, body, closes
        self.branches = []                    # origin branch names
        self.claims = {}                      # issue -> claim state (wip/waiting/done)
        self.local_trees = []                 # branch names of local worktrees
        self.on_base = set()                  # merge commits that ARE ancestors
        self.fail = []                        # command substrings that must fail
        self.epic_state = "OPEN"
        self.null_subissues = False
        self.subissues_next = False
        self.no_label_event = set()           # issues whose events lack the apply event
        self.search_partial = False           # a search that reads fewer than it counts
        self.issue_search_partial = False     # the same for the approved-issue search
        self.created = {}                     # issue -> createdAt (scope all-approved)
        self.tl = {}                          # issue -> timeline cross-referencing PR numbers
        self.calls = []

    # ---- state building -----------------------------------------------------
    def issue(self, n, labels=(), state="OPEN", approved_by=None, approved_as="User"):
        self.labels[n] = list(labels)
        self.state[n] = state
        if approved_by:
            self.applied[n] = (approved_by, approved_as)
        return self

    def blocked(self, n, blockers):
        self.blockers[n] = list(blockers)
        return self

    def blocker(self, n, state="CLOSED", reason="COMPLETED", closed_by=()):
        self.bstate[n] = (state, reason)
        self.bclosing[n] = list(closed_by)
        return self

    def merged_pr(self, n, base="develop", sha="a" * 40, merged=True, on_base=True,
                  body="", head="feature/pr-%d"):
        self.pulls[n] = {"state": "closed", "merged_at": "2026-11-01T00:00:00Z" if merged else None,
                         "merge_commit_sha": sha, "base": {"ref": base},
                         "body": body, "head": {"ref": head % n if "%d" in head else head}}
        if on_base:
            self.on_base.add(sha)
        return self

    def open_pr(self, number, head="feature/x", body="", closes=()):
        self.open_prs.append({"number": number, "head": head, "body": body, "closes": list(closes)})
        return self

    # ---- the injected runner ------------------------------------------------
    def runner(self, argv):
        cmd = " ".join(argv)
        self.calls.append(cmd)
        for bad in self.fail:
            if bad in cmd:
                err = m.CommandError("simulated: %s" % cmd)
                err.exit_code = 4
                raise err
        if cmd.startswith("gh api user"):
            return '{"login": "tester"}\n'
        if cmd.startswith("gh repo view"):
            return json.dumps({"nameWithOwner": self.repo})
        if cmd.startswith("gh api graphql"):
            return self.graphql(cmd)
        if "/events?per_page=100" in cmd:
            return json.dumps(self.events(int(re.search(r"/issues/(\d+)/events", cmd).group(1))))
        if "/timeline?per_page=100" in cmd:
            return json.dumps([{"event": "cross-referenced",
                                "source": {"type": "PullRequest", "issue": {
                                    "number": p,
                                    "html_url": "https://github.com/o/r/pull/%d" % p,
                                    "pull_request": {}}}}
                               for p in self.tl.get(
                                   int(re.search(r"/issues/(\d+)/timeline", cmd).group(1)), [])])
        if cmd.startswith("gh api repos/%s/pulls/" % self.repo):
            n = int(cmd.rsplit("/", 1)[1])
            if n not in self.pulls:
                raise AssertionError("the selector read a PR the fixture does not have: %d" % n)
            return json.dumps(self.pulls[n])
        if cmd.startswith("gh issue list"):
            return json.dumps([{"number": n, "title": "wip %d" % n}
                               for n, s in self.claims.items() if s in ("wip", "waiting")])
        if "/comments" in cmd:
            return json.dumps(self.comments(int(re.search(r"/issues/(\d+)/comments", cmd).group(1))))
        if cmd.startswith("git worktree"):
            return "".join("worktree /wt/%s\nbranch refs/heads/%s\n\n" % (b, b)
                           for b in self.local_trees)
        if cmd.startswith("git fetch"):
            return ""
        if cmd.startswith("git ls-remote"):
            return "".join("%s\trefs/heads/%s\n" % ("b" * 40, b) for b in self.branches)
        if cmd.startswith("git merge-base"):
            if argv[3] in self.on_base:
                return ""
            err = m.CommandError("not an ancestor")
            err.exit_code = 1
            raise err
        raise AssertionError("the selector ran a command the fixture does not know: " + cmd)

    # ---- responses ----------------------------------------------------------
    def events(self, n):
        """The labeled events an issue would carry, as GitHub returns them."""
        if "agent: approved" not in self.labels.get(n, []) or n in self.no_label_event:
            return []
        login, typename = self.applied.get(n, ("nobody", "User"))
        ev = [{"event": "labeled", "actor": {"login": login, "__typename": typename},
               "label": {"name": "agent: approved"}}]
        if n in self.unlabeled_after:
            ev.append({"event": "unlabeled", "actor": {"login": login, "__typename": typename},
                       "label": {"name": "agent: approved"}})
        return ev

    def comments(self, n):
        state = self.claims.get(n)
        if not state:
            return []
        p = {"v": 1, "client": "other:wt", "issue": n, "branch": "feature/issue-%d-x" % n,
             "worktree": "/wt/x", "state": state, "since": "2026-11-01T00:00:00Z",
             "heartbeat": "2026-11-01T00:00:00Z", "released": None}
        return [{"id": 1, "body": wip.claim_body(p)}]

    def graphql(self, query):
        # The fixture answers queries by shape rather than parsing GraphQL, so a
        # query whose braces do not close would be answered happily here and
        # rejected by the live API - which is how a syntax bug survives a green
        # suite. Balance is the one thing about a query this fixture checks.
        if query.count("{") != query.count("}"):
            raise AssertionError("the selector sent an unbalanced GraphQL query: " + query)
        if "subIssues" in query:
            if self.null_subissues:
                return json.dumps({"data": {"repository":
                                  {"issue": {"title": "e", "state": self.epic_state,
                                             "subIssues": None}}}})
            nodes = [{"number": n, "title": "issue %d" % n, "state": self.state.get(n, "OPEN"),
                      "stateReason": None,
                      "labels": {"totalCount": len(self.labels.get(n, [])),
                                 "nodes": [{"name": lab} for lab in self.labels.get(n, [])]}}
                     for n in self.order]
            return json.dumps({"data": {"repository": {"issue": {
                "title": "the epic", "state": self.epic_state,
                "subIssues": {"totalCount": len(nodes), "pageInfo": {"hasNextPage": self.subissues_next},
                              "nodes": nodes}}}}})
        if "blockedBy" in query:
            n = int(re.search(r"issue\(number:(\d+)\)", query).group(1))
            nodes = []
            for b in self.blockers.get(n, []):
                state, reason = self.bstate.get(b, ("OPEN", None))
                closing = [{"number": p, "state": "MERGED", "baseRefName": self.pulls.get(p, {}).get("base", {}).get("ref"),
                            "mergedAt": self.pulls.get(p, {}).get("merged_at")}
                           for p in self.bclosing.get(b, [])]
                nodes.append({"number": b, "state": state, "stateReason": reason,
                              "closedByPullRequestsReferences":
                                  {"totalCount": len(closing), "pageInfo": {"hasNextPage": False},
                                   "nodes": closing}})
            return json.dumps({"data": {"repository": {"issue": {"blockedBy": {
                "totalCount": len(nodes), "pageInfo": {"hasNextPage": False}, "nodes": nodes}}}}})
        if "search(query:" in query and "is:issue" in query:
            # The scope all-approved candidate listing: open issues carrying
            # the approval label. Answered in the fixture's own listing order,
            # which is deliberately NOT the creation order - the selector has
            # to do its FIFO sort itself.
            nodes = [{"__typename": "Issue", "number": n, "title": "issue %d" % n,
                      "state": self.state.get(n, "OPEN"),
                      "createdAt": self.created.get(n, "2026-11-01T00:00:00Z"),
                      "labels": {"totalCount": len(self.labels.get(n, [])),
                                 "pageInfo": {"hasNextPage": False},
                                 "nodes": [{"name": lab} for lab in self.labels.get(n, [])]}}
                     for n in self.order
                     if self.state.get(n, "OPEN") == "OPEN"
                     and m.APPROVED_LABEL in self.labels.get(n, [])]
            counted = len(nodes) + (5 if self.issue_search_partial else 0)
            return json.dumps({"data": {"search": {"issueCount": counted,
                                                   "pageInfo": {"hasNextPage": False,
                                                                "endCursor": None}, "nodes": nodes}}})
        if "search(query:" in query:
            nodes = [{"__typename": "PullRequest", "number": pr["number"],
                      "headRefName": pr["head"], "body": pr["body"],
                      "closingIssuesReferences": {"nodes": [{"number": c} for c in pr["closes"]]}}
                     for pr in self.open_prs]
            # GitHub's search can count more results than it hands out; a screen
            # that missed one would call a taken issue free.
            counted = len(nodes) + (5 if self.search_partial else 0)
            return json.dumps({"data": {"search": {"issueCount": counted,
                                                   "pageInfo": {"hasNextPage": False,
                                                                "endCursor": None}, "nodes": nodes}}})
        raise AssertionError("the selector sent a GraphQL query the fixture does not know: " + query)


# ---------- running the tool ------------------------------------------------

def screen(fixture, *argv):
    """Run main() against the fixture -> (exit code, stdout)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = m.main(["--json"] + list(argv), runner=fixture.runner)
    return code, out.getvalue()


def tokens(result, n):
    return [r.split(":", 1)[0] for r in verdict(result, n)["reasons"]]


def verdict(result, n):
    for v in result["issues"]:
        if v["number"] == n:
            return v
    raise AssertionError("no verdict for #%s in %s" % (n, result))


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
    return ok


results = []

# 1. Approved, unclaimed, unblocked roots are eligible, in the epic's listing
#    order - which is not the number order, so the order has to be asserted.
f = Fixture(order=[1261, 1257, 1260])
f.issue(1261, ["agent: approved"], approved_by="jokiefer")
f.issue(1257, ["agent: approved", "type: bug"], approved_by="jokiefer")
f.issue(1260, ["agent: approved"], approved_by="jokiefer")
code, out = screen(f)
res = json.loads(out)
results.append(check("approved unblocked roots are eligible in listing order",
                     code == 0 and res["status"] == "ok" and res["eligible"] == [1261, 1257, 1260],
                     f"code={code} eligible={res['eligible']}"))

# 2. The screen is deterministic: the same state answers the same way twice.
code2, out2 = screen(f)
results.append(check("two runs over the same state give the same answer",
                     code2 == code and out2 == out))

# 3. No `agent: approved` label - not approved, nothing else considered.
f = Fixture(order=[1257]).issue(1257, ["type: bug"])
code, out = screen(f)
res = json.loads(out)
results.append(check("an unapproved issue is excluded with not-approved",
                     code == 0 and res["eligible"] == [] and tokens(res, 1257) == ["not-approved"],
                     f"eligible={res['eligible']} tokens={tokens(res, 1257)}"))

# 4. An approval applied by a bot does not count, even with a plausible login.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="dependabot[bot]",
                                approved_as="Bot")
res = json.loads(screen(f)[1])
results.append(check("a Bot actor that applied the label does not approve it",
                     res["eligible"] == [] and tokens(res, 1257) == ["approval-by-bot"],
                     f"tokens={tokens(res, 1257)}"))

# 4b. The agent's own login is denied even if someone puts it on the allowlist.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="mrmap-agent-bot",
                                approved_as="User")
res = json.loads(screen(f, "--humans", "mrmap-agent-bot,jokiefer")[1])
results.append(check("mrmap-agent-bot cannot approve even when allowlisted",
                     res["eligible"] == [] and tokens(res, 1257) == ["approval-by-bot"],
                     f"tokens={tokens(res, 1257)}"))

# 4c. A human who is not on the allowlist cannot approve either.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="someone-else")
res = json.loads(screen(f)[1])
results.append(check("an approval by a non-allowlisted human is excluded",
                     res["eligible"] == [] and tokens(res, 1257) == ["approval-by-unlisted-human"],
                     f"tokens={tokens(res, 1257)}"))

# 4d. --humans replaces the allowlist, and so does the environment variable.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="someone-else")
res = json.loads(screen(f, "--humans", "someone-else")[1])
results.append(check("--humans lets a listed human approve",
                     res["eligible"] == [1257], f"eligible={res['eligible']}"))
os.environ[m.APPROVERS_ENV] = "someone-else, jokiefer"
try:
    res = json.loads(screen(Fixture(order=[1257]).issue(1257, ["agent: approved"],
                                                        approved_by="someone-else"))[1])
    ok_env = res["eligible"] == [1257] and res["approvers"] == ["jokiefer", "someone-else"]
finally:
    os.environ.pop(m.APPROVERS_ENV, None)
results.append(check("AGENT_EPIC_APPROVERS sets the allowlist", ok_env, f"eligible={res['eligible']}"))

# 4e. An empty allowlist fails closed: nothing can be honoured, nothing is eligible.
f = Fixture(order=[1257, 1258])
f.issue(1257, ["agent: approved"], approved_by="jokiefer")
f.issue(1258, ["agent: approved"], approved_by="jokiefer")
code, out = screen(f, "--humans", "")
res = json.loads(out)
results.append(check("an empty allowlist fails closed with no eligible issue",
                     code != 0 and res["status"] == "error" and "allowlist" in res["error"]
                     and "eligible" not in res,
                     f"code={code} res={res}"))

# 4f. A label whose last event removed it cannot be attributed to anyone.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
f.unlabeled_after.add(1257)
res = json.loads(screen(f)[1])
results.append(check("an approval whose last event is unlabeled is excluded",
                     tokens(res, 1257) == ["approval-unlabeled"], f"tokens={tokens(res, 1257)}"))

# 5. `agent: paused` excludes, whatever else is true of the issue.
f = Fixture(order=[1257]).issue(1257, ["agent: approved", "agent: paused"], approved_by="jokiefer")
res = json.loads(screen(f)[1])
results.append(check("a paused issue is excluded with paused",
                     res["eligible"] == [] and "paused" in tokens(res, 1257),
                     f"tokens={tokens(res, 1257)}"))

# 6. An open blocker blocks.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, state="OPEN")
res = json.loads(screen(f)[1])
results.append(check("an open blocker blocks with blocked-by-open-<n>",
                     res["eligible"] == [] and tokens(res, 1259) == ["blocked-by-open-1257"],
                     f"tokens={tokens(res, 1259)}"))

# 7. A blocker closed as NOT_COMPLETED did not finish, so it does not unblock.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, state="CLOSED", reason="NOT_COMPLETED")
res = json.loads(screen(f)[1])
results.append(check("a blocker closed as NOT_COMPLETED does not unblock",
                     res["eligible"] == [] and tokens(res, 1259) == ["blocker-not-completed-1257"],
                     f"tokens={tokens(res, 1259)}"))

# 8. A blocker closed with no merged PR is closed without implementation.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, closed_by=[])
res = json.loads(screen(f)[1])
results.append(check("a blocker closed without a merged PR is closed-without-implementation",
                     res["eligible"] == []
                     and tokens(res, 1259) == ["blocker-closed-without-implementation-1257"],
                     f"tokens={tokens(res, 1259)}"))

# 8b. A PR that closed it but was never merged is the same case.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, closed_by=[901]).merged_pr(901, merged=False, on_base=False)
res = json.loads(screen(f)[1])
results.append(check("a blocker whose closing PR was closed unmerged stays blocked",
                     tokens(res, 1259) == ["blocker-closed-without-implementation-1257"],
                     f"tokens={tokens(res, 1259)}"))

# 9. A blocker merged into develop unblocks the issue behind it.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, closed_by=[901]).merged_pr(901, sha="c" * 40)
res = json.loads(screen(f)[1])
results.append(check("a blocker merged into develop unblocks",
                     res["eligible"] == [1259] and verdict(res, 1259)["reasons"] == [],
                     f"eligible={res['eligible']} reasons={verdict(res, 1259)['reasons']}"))

# 9b. Merged into another branch (master) is not the base branch: still blocked.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, closed_by=[901]).merged_pr(901, base="master", sha="d" * 40)
res = json.loads(screen(f)[1])
results.append(check("a blocker merged only into master does not unblock",
                     res["eligible"] == []
                     and tokens(res, 1259) == ["blocker-closed-without-implementation-1257"]
                     and "master" in verdict(res, 1259)["reasons"][0],
                     f"reasons={verdict(res, 1259)['reasons']}"))

# 9c. Merged into develop but not yet reachable from origin/develop: still blocked.
f = Fixture(order=[1259]).issue(1259, ["agent: approved"], approved_by="jokiefer")
f.blocked(1259, [1257]).blocker(1257, closed_by=[901]).merged_pr(901, sha="e" * 40, on_base=False)
res = json.loads(screen(f)[1])
results.append(check("a merge commit that is not an ancestor of origin/develop does not unblock",
                     res["eligible"] == []
                     and tokens(res, 1259) == ["blocker-closed-without-implementation-1257"],
                     f"tokens={tokens(res, 1259)}"))

# 9d. Several blockers: one unsatisfied blocker is enough to block, and each
#     blocker is answered under its own number.
f = Fixture(order=[1264]).issue(1264, ["agent: approved"], approved_by="jokiefer")
f.blocked(1264, [1267, 1265]).blocker(1267, closed_by=[901]).merged_pr(901, sha="f" * 40)
f.blocker(1265, state="OPEN")
res = json.loads(screen(f)[1])
results.append(check("one unsatisfied of several blockers keeps the issue blocked",
                     res["eligible"] == [] and "blocked-by-open-1265" in tokens(res, 1264)
                     and "blocker-closed-without-implementation-1265" not in tokens(res, 1264),
                     f"tokens={tokens(res, 1264)}"))

# 10. An issue with an active wip claim is excluded, and a released claim is not.
f = Fixture(order=[1257, 1258])
f.issue(1257, ["agent: approved"], approved_by="jokiefer")
f.issue(1258, ["agent: approved"], approved_by="jokiefer")
f.claims = {1257: "wip", 1258: "done"}
res = json.loads(screen(f)[1])
results.append(check("an issue with an active wip claim is excluded, a released one is not",
                     res["eligible"] == [1258] and tokens(res, 1257) == ["wip-claimed"],
                     f"eligible={res['eligible']} tokens={tokens(res, 1257)}"))

# 10b. A waiting claim is as active as a working one, and a local worktree that
#      already names the issue counts too - `wip ls` shows both.
f = Fixture(order=[1257, 1258])
f.issue(1257, ["agent: approved"], approved_by="jokiefer")
f.issue(1258, ["agent: approved"], approved_by="jokiefer")
f.claims = {1257: "waiting"}
f.local_trees = ["feature/issue-1258-collect"]
res = json.loads(screen(f)[1])
results.append(check("a waiting claim and a local worktree both hold their issue",
                     res["eligible"] == [] and tokens(res, 1257) == ["wip-claimed"]
                     and tokens(res, 1258) == ["wip-claimed"],
                     f"tokens={tokens(res, 1257)} {tokens(res, 1258)}"))

# 11. An open PR that closes the issue, or whose branch names it, is a duplicate.
f = Fixture(order=[1257, 1258, 1259])
f.issue(1257, ["agent: approved"], approved_by="jokiefer")
f.issue(1258, ["agent: approved"], approved_by="jokiefer")
f.issue(1259, ["agent: approved"], approved_by="jokiefer")
f.open_pr(801, head="feature/other", body="Fixes #1257 then some text")
f.open_pr(802, head="feature/issue-1258-topic", body="nothing in the body")
f.open_pr(803, head="feature/other-2", closes=[1259])
res = json.loads(screen(f)[1])
results.append(check("an open PR that closes or names the issue excludes it",
                     res["eligible"] == [] and tokens(res, 1257) == ["duplicate-pr-801"]
                     and tokens(res, 1258) == ["duplicate-pr-802"]
                     and tokens(res, 1259) == ["duplicate-pr-803"],
                     f"tokens={[tokens(res, n) for n in (1257, 1258, 1259)]}"))

# 12. An origin branch naming the issue with no open PR is a stale ownership.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
f.branches = ["feature/issue-1257-old-attempt"]
res = json.loads(screen(f)[1])
results.append(check("an orphan origin branch naming the issue excludes it",
                     res["eligible"] == [] and tokens(res, 1257) == ["stale-branch-ownership"],
                     f"tokens={tokens(res, 1257)}"))

# 12b. The flag says no session owns it: then the branch costs nothing.
code, out = screen(f, "--ignore-stale-branches")
res = json.loads(out)
results.append(check("--ignore-stale-branches lets the issue through and records the flag",
                     code == 0 and res["eligible"] == [1257]
                     and "ignore-stale-branches" in res["flags"],
                     f"eligible={res['eligible']} flags={res['flags']}"))

# 12c. A branch with an open PR is not stale - it is the duplicate case.
f.branches = ["feature/issue-1257-live"]
f.open_pr(804, head="feature/issue-1257-live")
res = json.loads(screen(f)[1])
results.append(check("a branch with an open PR reads as a duplicate, not as stale",
                     tokens(res, 1257) == ["duplicate-pr-804"], f"tokens={tokens(res, 1257)}"))

# 13. Fail closed: every one of these answers status=error with a non-zero exit.


def fails(name, mutate, want):
    fx = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
    mutate(fx)
    code, out = screen(fx)
    res = json.loads(out)
    return check(name, code != 0 and res["status"] == "error" and want in res["error"]
                 and "eligible" not in res, f"code={code} res={res}")


results.append(fails("a gh that is not authenticated fails closed",
                     lambda fx: fx.fail.append("gh api user"), "gh is not usable"))
results.append(fails("a failing GraphQL call fails closed",
                     lambda fx: fx.fail.append("blockedBy"), "GraphQL"))
results.append(fails("a denied GitHub answer fails closed",
                     lambda fx: (fx.blocked(1257, [1256]), fx.blocker(1256, closed_by=[901]),
                                 fx.merged_pr(901, sha="a" * 40),
                                 fx.fail.append("repos/o/r/pulls")), "reading PR"))
results.append(fails("a null sub-issue connection fails closed",
                     lambda fx: setattr(fx, "null_subissues", True), "null"))
results.append(fails("a non-OPEN epic fails closed",
                     lambda fx: setattr(fx, "epic_state", "CLOSED"), "not OPEN"))
results.append(fails("a failing git fetch fails closed",
                     lambda fx: fx.fail.append("git fetch"), "git fetch origin develop failed"))
results.append(fails("a git merge-base that cannot answer fails closed",
                     lambda fx: (fx.blocked(1257, [1256]), fx.blocker(1256, closed_by=[901]),
                                 fx.merged_pr(901, sha="a" * 40, on_base=False),
                                 fx.fail.append("merge-base")), "merge-base"))
results.append(fails("a wip claim scan that fails fails closed",
                     lambda fx: (fx.claims.update({1257: "wip"}),
                                 fx.fail.append("issues/1257/comments")), "claim scan"))

# 14. The JSON schema is what a caller parses: stable keys in both outcomes.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
code, out = screen(f)
res = json.loads(out)
results.append(check("the ok result has a stable shape",
                     code == 0 and set(res) == {"schema", "status", "error", "repo", "baseRef",
                                                "scope", "epicNumber", "epicTitle", "approvers",
                                                "flags", "issues", "eligible"}
                     and set(res["issues"][0]) == {"number", "title", "order", "eligible", "reasons"}
                     and res["schema"] == m.SCHEMA and isinstance(res["eligible"], list),
                     f"keys={sorted(res)}"))
broken = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
broken.fail.append("gh api user")
code, out = screen(broken)
results.append(check("the error result has a stable shape",
                     code != 0 and set(json.loads(out)) == {"schema", "status", "error"},
                     f"keys={sorted(json.loads(out))}"))

# 15. The testing flag shows the dependency screen on its own: approvals are
#     skipped, everything else still applies, and the run says so out loud.
f = Fixture(order=[1257, 1258, 1259])
for n in (1257, 1258, 1259):
    f.issue(n, ["type: bug"])
f.blocked(1259, [1257])
f.branches = ["feature/issue-1258-stale"]
code, out = screen(f, "--ignore-approval-provenance-for-testing")
res = json.loads(out)
results.append(check("the testing flag yields the dependency screen only and banners itself",
                     code == 0 and res["eligible"] == [1257]
                     and res["flags"] == ["ignore-approval-provenance-for-testing"]
                     and tokens(res, 1259) == ["blocked-by-open-1257"]
                     and tokens(res, 1258) == ["stale-branch-ownership"]
                     and "ignore-approval-provenance-for-testing" in res["flags"],
                     f"eligible={res['eligible']} flags={res['flags']}"))
plain = io.StringIO()
with redirect_stdout(plain):
    code_plain = m.main([], runner=f.runner)
bannered = io.StringIO()
with redirect_stdout(bannered):
    m.main(["--ignore-approval-provenance-for-testing"], runner=f.runner)
results.append(check("without the flag nothing is approved, with it the run banners itself",
                     code_plain == 0 and "TESTING MODE" not in plain.getvalue()
                     and "TESTING MODE" in bannered.getvalue(),
                     repr(plain.getvalue()[:80])))

# 16. The human table reads: eligible row, reasons for the rest, spawn order.
table = io.StringIO()
f2 = Fixture(order=[1261, 1257])
f2.issue(1261, ["agent: approved"], approved_by="jokiefer")
f2.issue(1257, ["type: bug"])
with redirect_stdout(table):
    code = m.main(["--dry-run"], runner=f2.runner)
text = table.getvalue()
results.append(check("--dry-run is accepted and prints the table with the spawn order",
                     code == 0 and "#1261" in text and "YES" in text
                     and "eligible (spawn order): #1261" in text and "not-approved" in text,
                     repr(text[-200:])))

# 17. Read-only: the run never writes to GitHub or to the repository beyond the
#     base-ref fetch the rules demand.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
screen(f)
writes = [c for c in f.calls if " -X PATCH" in c or "issue edit" in c or "issue create" in c
          or "issue comment" in c or "issue close" in c or "git push" in c
          or "git branch -" in c or "git checkout" in c or "git switch" in c]
git_writes = [c for c in f.calls if c.startswith("git ")
              and not c.startswith(("git fetch origin develop", "git ls-remote",
                                    "git merge-base", "git worktree"))]
results.append(check("a screen writes nothing to GitHub or the repository",
                     not writes and not git_writes, f"writes={writes} git={git_writes}"))

# 18. A CLOSED sub-issue is not a candidate, however well it is labelled.
f = Fixture(order=[1257, 1258])
f.issue(1257, ["agent: approved"], approved_by="jokiefer")
f.issue(1258, ["agent: approved"], approved_by="jokiefer", state="CLOSED")
res = json.loads(screen(f)[1])
results.append(check("a closed sub-issue is not eligible",
                     res["eligible"] == [1257] and tokens(res, 1258) == ["not-open"],
                     f"eligible={res['eligible']} tokens={tokens(res, 1258)}"))

# 19. A connection that reports another page is not fully readable: the screen
#     refuses to rank candidates it could not see.
results.append(fails("a sub-issue listing with a next page fails closed",
                     lambda fx: setattr(fx, "subissues_next", True), "not fully readable"))
results.append(fails("a search that reads fewer PRs than it counts fails closed",
                     lambda fx: setattr(fx, "search_partial", True), "could only read"))
results.append(fails("an approval no event can be found for fails closed",
                     lambda fx: fx.no_label_event.add(1257), "unverifiable"))

# ---------- scope all-approved --------------------------------------------

# 20. Scope all-approved screens every open approved issue of the repository
#     - unlabelled issues are not candidates at all - and orders the eligible
#     list FIFO by creation, because outside an epic no curated order exists.
f = Fixture(order=[9, 8, 7])
f.issue(7, ["agent: approved"], approved_by="jokiefer")
f.issue(8, ["agent: approved"], approved_by="jokiefer")
f.issue(9, ["type: bug"])
f.created = {7: "2026-01-03T00:00:00Z", 8: "2026-01-01T00:00:00Z"}
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("all-approved screens every approved open issue, FIFO by creation",
                     res["scope"] == "all-approved" and res["epicNumber"] is None
                     and res["epicTitle"] is None and res["eligible"] == [8, 7]
                     and not [c for c in f.calls if " -X PATCH" in c or "issue edit" in c
                              or "issue comment" in c or "issue create" in c],
                     f"eligible={res['eligible']} scope={res['scope']}"))

# 21. An Epic carrying the approval itself is a container, not a worker task.
f = Fixture(order=[5]).issue(5, ["agent: approved", "Epic"], approved_by="jokiefer")
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("an approved Epic is rejected as a container",
                     res["eligible"] == [] and tokens(res, 5) == ["epic-container"],
                     f"tokens={tokens(res, 5)}"))

# 22. Rules 2 to 6 hold identically in repo scope: paused, bot approval, an
#     open blocker, an active claim and a duplicate PR each veto on their own.
f = Fixture(order=[10, 11, 12, 13, 14])
f.issue(10, ["agent: approved", "agent: paused"], approved_by="jokiefer")
f.issue(11, ["agent: approved"], approved_by="mrmap-agent-bot")
f.issue(12, ["agent: approved"], approved_by="jokiefer")
f.issue(13, ["agent: approved"], approved_by="jokiefer")
f.issue(14, ["agent: approved"], approved_by="jokiefer")
f.blocked(12, [99])
f.blocker(99, state="OPEN", reason=None)
f.claims[13] = "wip"
f.open_pr(777, head="feature/x", body="Closes #14")
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("paused, bot approval, open blocker, claim and duplicate PR reject in repo scope",
                     res["eligible"] == [] and tokens(res, 10) == ["paused"]
                     and tokens(res, 11) == ["approval-by-bot"]
                     and tokens(res, 12) == ["blocked-by-open-99"]
                     and tokens(res, 13) == ["wip-claimed"]
                     and tokens(res, 14) == ["duplicate-pr-777"],
                     f"10={tokens(res, 10)} 11={tokens(res, 11)} 12={tokens(res, 12)}"
                     f" 13={tokens(res, 13)} 14={tokens(res, 14)}"))

# 23. The blocker rule is the same rule: closed-completed alone does not
#     satisfy; only a PR merged into the base branch does - then the issue
#     becomes eligible with nothing else standing in the way.
f = Fixture(order=[20])
f.issue(20, ["agent: approved"], approved_by="jokiefer")
f.blocked(20, [21])
f.blocker(21, closed_by=[500])
f.merged_pr(500, base="master", sha="c" * 40, on_base=False)
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("a blocker merged elsewhere does not satisfy in repo scope",
                     res["eligible"] == []
                     and tokens(res, 20) == ["blocker-closed-without-implementation-21"],
                     f"tokens={tokens(res, 20)}"))
f2 = Fixture(order=[20])
f2.issue(20, ["agent: approved"], approved_by="jokiefer")
f2.blocked(20, [21])
f2.blocker(21, closed_by=[501])
f2.merged_pr(501, sha="d" * 40, on_base=True)
res = json.loads(screen(f2, "--scope", "all-approved")[1])
results.append(check("a blocker merged into develop satisfies in repo scope",
                     res["eligible"] == [20], f"eligible={res['eligible']}"))

# 24. The candidate search is fail-closed like every other read: a result set
#     that counts more than it hands out ends the screen, not a partial queue.
f = Fixture(order=[1]).issue(1, ["agent: approved"], approved_by="jokiefer")
f.issue_search_partial = True
code, out = screen(f, "--scope", "all-approved")
res = json.loads(out)
results.append(check("an approved-issue search that reads fewer than it counts fails closed",
                     code != 0 and res["status"] == "error"
                     and "could only read" in res["error"] and "eligible" not in res,
                     f"code={code} res={res}"))

# 25. An issue approved by an unlisted human stays rejected in repo scope.
f = Fixture(order=[6]).issue(6, ["agent: approved"], approved_by="someone-else")
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("repo scope rejects approvals from humans outside the allowlist",
                     res["eligible"] == []
                     and tokens(res, 6) == ["approval-by-unlisted-human"],
                     f"tokens={tokens(res, 6)}"))

# 26. The default scope is untouched: same call as before, epic keys intact.
f = Fixture(order=[1257]).issue(1257, ["agent: approved"], approved_by="jokiefer")
res = json.loads(screen(f)[1])
results.append(check("the default scope is epic with its keys unchanged",
                     res["scope"] == "epic" and res["epicNumber"] == 1256
                     and res["eligible"] == [1257], f"scope={res['scope']}"))

# 27. Rule 4 timeline fallback: an issue closed by hand after a develop-merged
#     PR carries no native closed-by relation - the PR that NAMES the blocker
#     (body keyword or branch convention) still satisfies it.
f = Fixture(order=[20])
f.issue(20, ["agent: approved"], approved_by="jokiefer")
f.blocked(20, [21])
f.blocker(21, closed_by=[])
f.tl[21] = [502]
f.merged_pr(502, sha="e" * 40, on_base=True, body="Closes #21\n\nfixes it")
res = json.loads(screen(f)[1])
results.append(check("a hand-closed blocker satisfied by a develop-merged naming PR",
                     res["eligible"] == [20]
                     and any("timeline" in c for c in f.calls),
                     f"eligible={res['eligible']}"))

# 28. Branch naming satisfies as evidence of naming just like the body keyword.
f = Fixture(order=[20])
f.issue(20, ["agent: approved"], approved_by="jokiefer")
f.blocked(20, [21])
f.blocker(21, closed_by=[])
f.tl[21] = [503]
f.merged_pr(503, sha="f" * 40, on_base=True, body="no keyword here",
            head="feature/issue-21-repair")
res = json.loads(screen(f)[1])
results.append(check("an issue-<N> head branch names the blocker just as well",
                     res["eligible"] == [20], f"eligible={res['eligible']}"))

# 29. A timeline PR that only mentions the number, or merged elsewhere, or
#     never merged, satisfies nothing - the fallback must not go soft.
f = Fixture(order=[20])
f.issue(20, ["agent: approved"], approved_by="jokiefer")
f.blocked(20, [21])
f.blocker(21, closed_by=[])
f.tl[21] = [601, 602, 603]
f.merged_pr(601, sha="1" * 40, on_base=True, body="saw this in #21 once")
f.merged_pr(602, base="master", sha="2" * 40, on_base=False, body="Closes #21")
f.merged_pr(603, sha="3" * 40, merged=False, body="Closes #21")
res = json.loads(screen(f)[1])
results.append(check("mention-only, wrong-base and unmerged timeline PRs satisfy nothing",
                     res["eligible"] == []
                     and tokens(res, 20) == ["blocker-closed-without-implementation-21"],
                     f"tokens={tokens(res, 20)}"))

# 30. A timeline that cannot be read fails closed (it is Rule 4 evidence now).
results.append(fails("an unreadable blocker timeline fails closed",
                     lambda fx: (fx.blocked(1257, [1256]), fx.blocker(1256, closed_by=[]),
                                 fx.fail.append("issues/1256/timeline")), "timeline"))

# 31. Two candidates behind the SAME hand-closed blocker: the first one reads
#     the timeline PRs into the shared PR cache, and the second must still be
#     judged on them. Skipping by "already in the cache" once made every
#     sibling behind an already-cleared blocker a false negative.
f = Fixture(order=[20, 22])
f.issue(20, ["agent: approved"], approved_by="jokiefer")
f.issue(22, ["agent: approved"], approved_by="jokiefer")
f.blocked(20, [21])
f.blocked(22, [21])
f.blocker(21, closed_by=[])
f.tl[21] = [700, 701]
f.merged_pr(700, sha="7" * 40, on_base=True, body="mentioned #21 in passing")
f.merged_pr(701, sha="8" * 40, on_base=True, body="Closes #21")
res = json.loads(screen(f, "--scope", "all-approved")[1])
results.append(check("two candidates sharing one satisfied blocker are both eligible",
                     res["eligible"] == [20, 22], f"eligible={res['eligible']}"))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
