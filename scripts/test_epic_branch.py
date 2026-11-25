"""Offline regression checks for scripts/epic_branch.py (issue #1591).

Run from the repository root: python3 scripts/test_epic_branch.py
Exit code 0 means every check passed.

The resolver decides which branch an issue's work belongs on and which PR targets are
legal, so the checks that matter are the refusals: an unlinked parent, a refused slug,
two epics sharing a slug, a branch nobody owns, a closed epic whose work never reached
develop, a child PR pointed at develop, an epic branch pointed anywhere but develop, and
every case where GitHub or git cannot be read. Every `gh` and `git` call is answered by
the fixture below, so this needs no `gh`, no token, no network and no real repository -
and it cannot create a branch or retarget a pull request anywhere.

The two write subcommands are tested against the same injected runner, which records the
pushes and PATCHes it is asked for instead of performing them: that is how the checks can
assert both that `--write` writes exactly one thing and that a dry run writes nothing.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    "epic_branch", importlib.machinery.SourceFileLoader(
        "epic_branch", os.path.join(HERE, "epic_branch.py")))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

DEVELOP_SHA = "d" * 40
EPIC_SHA = "e" * 40
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%-72s %s%s" % (name, "ok" if ok else "FAIL", (" " + detail) if not ok else ""))
    return ok


def codes_of(res):
    return sorted(f["code"] for f in res.get("findings") or [])


# A past deployment override must not reactivate the superseded epic policy.
for day in ("2026-12-15", "2026-12-21", "2030-01-01"):
    with patch.dict(
            os.environ, {m.STRICT_FROM_ENV: "2020-01-01"}):
        check("superseded epic policy stays advisory on %s" % day,
              m.mode_for(day) == "advisory")
check("explicit legacy strict remains available", m.mode_for("2030-01-01", "strict") == "strict")


class Fixture:
    """The whole GitHub and git state one run of the resolver observes."""

    def __init__(self):
        self.repo = "o/r"
        self.issues = {}            # number -> issue dict
        self.branches = {"develop": DEVELOP_SHA, "master": "m" * 40}
        self.ancestors = set()      # SHAs that ARE ancestors of origin/develop
        self.pulls = {}             # PR number -> REST view dict
        self.timelines = {}         # issue -> [PR numbers cross-referencing it]
        self.fail = []              # command substrings that must fail
        self.pushes = []            # git pushes the runner was asked to make
        self.patches = []           # PR base patches the runner was asked to make
        self.agent_bot = False      # answer `gh api user` as the agent identity
        self.calls = []

    # ---- state building -----------------------------------------------------
    def issue(self, number, body="", state="OPEN", parent=None, labels=()):
        self.issues[number] = {"number": number, "body": body, "state": state,
                               "parent": parent, "labels": list(labels)}
        return self

    def epic(self, number, slug=None, state="OPEN", parent=None, extra=""):
        body = ("slug: %s\n" % slug if slug else "") + extra
        return self.issue(number, body=body, state=state, parent=parent, labels=["Epic"])

    def children(self, epic_number, numbers):
        """The native sub-issue listing of an epic (its curated order)."""
        self.issues[epic_number]["children"] = list(numbers)
        for n in numbers:
            self.issues.setdefault(n, {"number": n, "body": "", "state": "OPEN",
                                       "parent": epic_number, "labels": []})
            self.issues[n]["parent"] = epic_number
        return self

    def branch(self, name, sha=EPIC_SHA):
        self.branches[name] = sha
        return self

    def merged_pr(self, pr, number, base="epic/epic-integration", sha="a" * 40,
                  on_base=True):
        """The merged PR that implemented `number` (cross-referenced from its timeline)."""
        self.pulls[pr] = {"number": pr, "state": "closed", "merged_at": "2026-11-01T00:00:00Z",
                          "merge_commit_sha": sha,
                          "base": {"ref": base, "repo": {"full_name": self.repo}},
                          "head": {"ref": "feature/pr-%d" % pr, "sha": sha,
                                   "repo": {"full_name": self.repo}}}
        self.timelines.setdefault(number, []).append(pr)
        if on_base:
            self.ancestors.add(sha)
        return self

    def open_pr(self, pr, head, base, head_repo=None, head_sha=None, state="open"):
        self.pulls[pr] = {"number": pr, "state": state, "merged_at": None,
                          "merge_commit_sha": None, "title": "x", "body": "", "draft": False,
                          "base": {"ref": base, "repo": {"full_name": self.repo}},
                          "head": {"ref": head, "sha": head_sha or "b" * 40,
                                   "repo": {"full_name": head_repo or self.repo}}}
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
            login = "mrmap-agent-bot" if self.agent_bot else "jokiefer"
            return json.dumps({"login": login})
        if cmd.startswith("gh repo view"):
            return json.dumps({"nameWithOwner": self.repo})
        if cmd.startswith("gh api graphql"):
            return self.graphql(cmd)
        if "labels=Epic" in cmd:
            return self.epic_listing(cmd)
        if "timeline?per_page" in cmd:
            return self.timeline(cmd)
        if cmd.startswith("gh api -X PATCH"):
            self.patches.append(cmd)
            return "{}"
        if "pulls?state=open" in cmd:
            return self.open_pr_listing()
        if cmd.startswith("gh api repos/o/r/pulls/"):
            num = int(cmd.rsplit("/", 1)[1].split(" ")[0])
            if num not in self.pulls:
                raise m.CommandError("no such PR: %d" % num)
            return json.dumps(self.pulls[num])
        if cmd.startswith("git ls-remote"):
            return "".join("%s\trefs/heads/%s\n" % (sha, name)
                           for name, sha in sorted(self.branches.items()))
        if cmd.startswith("git merge-base --is-ancestor"):
            sha, rev = argv[-2], argv[-1]
            if rev == "origin/develop":
                return "" if sha in self.ancestors else self._not_ancestor(sha, rev)
            name = rev.split("origin/", 1)[-1]
            if name not in self.branches:
                raise m.CommandError("unknown rev %s" % rev)
            # a child head descends from the epic head when the fixture says so: the
            # head's own SHA is registered as an ancestor of that branch.
            return "" if sha in self.ancestors_of(name) else self._not_ancestor(sha, rev)
        if cmd.startswith("git fetch"):
            return ""
        if cmd.startswith("git rev-parse"):
            name = argv[-1].split("origin/", 1)[-1]
            if name not in self.branches:
                raise m.CommandError("unknown rev %s" % argv[-1])
            return self.branches[name] + "\n"
        if cmd.startswith("git push"):
            self.pushes.append(cmd)
            return ""
        raise AssertionError("the fixture was asked about an unknown command: %s" % cmd)

    @staticmethod
    def _not_ancestor(sha, rev):
        err = m.CommandError("not an ancestor: %s %s" % (sha, rev))
        err.exit_code = 1
        raise err

    def ancestors_of(self, branch):
        return set(self.__dict__.get("_anc", {}).get(branch, set()))

    def ancestor(self, branch, sha):
        self.__dict__.setdefault("_anc", {}).setdefault(branch, set()).add(sha)
        return self

    def graphql(self, cmd):
        import re
        num = int(re.search(r"issue\(number:(\d+)\)", cmd).group(1))
        issue = self.issues.get(num)
        if issue is None:
            return json.dumps({"data": {"repository": {"issue": None}}})
        if "bodyText" in cmd:
            node = {"number": num, "title": "issue %d" % num, "state": issue["state"],
                    "stateReason": "COMPLETED" if issue["state"] == "CLOSED" else None,
                    "bodyText": issue["body"],
                    "labels": {"nodes": [{"name": lab} for lab in issue["labels"]]}}
        elif "parent{number}" in cmd:
            node = {"parent": {"number": issue["parent"]} if issue["parent"] else None}
        elif "subIssues" in cmd:
            kids = issue.get("children", [])
            node = {"subIssues": {"totalCount": len(kids),
                                  "pageInfo": {"hasNextPage": False},
                                  "nodes": [{"number": k, "state": self.issues[k]["state"]}
                                            for k in kids]}}
        else:
            node = {"number": num, "state": issue["state"]}
        return json.dumps({"data": {"repository": {"issue": node}}})

    def epic_listing(self, cmd=""):
        want_closed = "state=all" in cmd
        out = []
        for num, issue in sorted(self.issues.items()):
            if "Epic" not in issue["labels"]:
                continue
            if issue["state"] != "OPEN" and not want_closed:
                continue
            out.append({"number": num, "state": issue["state"], "body": issue["body"],
                        "labels": [{"name": lab} for lab in issue["labels"]]})
        return json.dumps(out)

    def open_pr_listing(self):
        return json.dumps([{"number": n, "state": p["state"],
                            "head": {"ref": p["head"]["ref"]},
                            "base": {"ref": p["base"]["ref"]}}
                           for n, p in sorted(self.pulls.items())
                           if p["state"] == "open"])

    def timeline(self, cmd):
        num = int(cmd.split("/issues/")[1].split("/")[0])
        events = [{"event": "cross-referenced",
                   "source": {"type": "PullRequest",
                              "issue": {"number": pr,
                                        "pull_request": {"url": "https://x"},
                                        "html_url": "https://github.com/%s/pull/%d"
                                                    % (self.repo, pr)}}}
                  for pr in self.timelines.get(num, [])]
        return json.dumps(events)


# 0. The tool's own self-test, invoked from here so check_repo_tooling.sh sees the pure
#    rules (slug grammar, branch-name parsing, rollout halves) as part of this suite too.
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    _selftest_rc = m.self_test()
if _selftest_rc != 0:
    print(_buf.getvalue())
check("scripts/epic_branch.py check", _selftest_rc == 0, _buf.getvalue()[-200:])

# --------------------------------------------------------------------------- fixtures


def fixture_with_epic(slug="epic-integration", branch=True, state="OPEN", parent=None):
    """Epic #100 (optionally nested under #99) with child #101 on its branch."""
    f = Fixture()
    if parent is not None:
        f.epic(99, slug="outer-epic", state="OPEN")
    f.epic(100, slug=slug, state=state, parent=parent,
           extra="## Objective\nkeep incomplete features off develop\n")
    f.issue(101, body="**Parent:** #100 | **Blocked by:** #100\n", parent=100)
    f.children(100, [101])
    if branch and slug:
        f.branch("epic/" + slug)
    return f


def resolve(f, issue=101, **kw):
    res = m.resolve_issue(f.runner, issue, repo=f.repo, **kw)
    return res, m.exit_code(res)


# --------------------------------------------------------------- resolve: happy paths

# 1. An issue with no parent is independent: develop, row R1, nothing to fix.
f = Fixture().issue(200, body="## What\nplain fix\n")
res, code = resolve(f, 200)
check("independent issue resolves to develop (R1)",
      res["status"] == "ok" and res["row"] == "R1" and res["target"] == "develop"
      and not res["findings"] and code == 0, res["reason"])

# 2. A child of an open epic with a slug and a branch: the epic branch, row R2.
f = fixture_with_epic()
res, code = resolve(f)
check("child of a slugged epic resolves to its epic branch (R2)",
      res["row"] == "R2" and res["target"] == "epic/epic-integration"
      and res["branchSha"] == EPIC_SHA and code == 0, str(res))

# 3. The branch not existing yet is a finding with a named actor, not a re-route.
f = fixture_with_epic(branch=False)
res, code = resolve(f)
check("missing epic branch keeps the target and names the protected path",
      res["status"] == "ok" and res["target"] == "epic/epic-integration"
      and res["branchSha"] is None and codes_of(res) == ["epic-branch-missing"]
      and "create-branch" in res["findings"][0]["message"] and code == 0, str(res))

# 4. An epic that declares no slug is the bootstrap row: develop, and the declaration owed.
f = fixture_with_epic(slug=None)
res, code = resolve(f)
check("epic without a slug is the bootstrap row (R3)",
      res["row"] == "R3" and res["target"] == "develop" and not res["findings"], str(res))

# 5. Nested epic: the child works on the PARENT's branch (R9).
f = fixture_with_epic(slug="inner-epic", parent=99)
f.branch("epic/outer-epic")
res, code = resolve(f)
check("child of a nested epic works on the parent epic's branch (R9)",
      res["row"] == "R9" and res["target"] == "epic/outer-epic"
      and res["parentEpic"] == {"number": 99, "slug": "outer-epic"}, str(res))

# 6. ... and a nested epic whose parent declares no slug falls back to develop.
f = fixture_with_epic(slug="inner-epic", parent=99)
f.issues[99]["body"] = "no declaration here\n"
res, code = resolve(f)
check("nested epic under an unslugged parent is the bootstrap row (R3, R9)",
      res["row"] == "R3" and res["target"] == "develop", str(res))

# 7. A closed epic whose merged children are on develop: follow-up is a new issue (R10).
f = fixture_with_epic(state="CLOSED")
f.issue(101, body="done", parent=100, state="CLOSED")
f.merged_pr(500, 101, base="epic/epic-integration", sha="a" * 40, on_base=True)
res, code = resolve(f)
check("closed epic with its children on develop is R10",
      res["row"] == "R10" and res["target"] == "develop" and not res["findings"], str(res))

# 8. A closed epic whose work never reached develop is refused outright (R11).
f = fixture_with_epic(state="CLOSED")
f.issue(101, body="done", parent=100, state="CLOSED")
f.merged_pr(500, 101, base="epic/epic-integration", sha="a" * 40, on_base=False)
res, code = resolve(f)
check("closed epic never integrated is refused (R11)",
      res["status"] == "error" and res["row"] == "R11"
      and codes_of(res) == ["epic-abandoned"] and code == 2, str(res))

# 9. --no-ancestry never asks git and never claims R11 on the strength of nothing.
f = fixture_with_epic(state="CLOSED")
f.issue(101, body="done", parent=100, state="CLOSED")
res, code = resolve(f, ancestry=False)
check("--no-ancestry reports R10 without consulting git",
      res["row"] == "R10" and not [c for c in f.calls if "merge-base" in c], str(res))

# 10. An epic with no children at all reads as integrated (nothing owed develop).
f = Fixture().epic(100, slug="empty-epic", state="CLOSED")
f.issues[100]["children"] = []
f.issue(101, body="**Parent:** #100", parent=100)
res, code = resolve(f)
check("closed epic with no native children is R10", res["row"] == "R10", str(res))

# ------------------------------------------------------------- resolve: fail closed

# 11. The body names a parent the API does not report: refuse, never guess (open question
#     of the contract: the native relation is the fact).
f = Fixture().issue(300, body="**Parent:** #100 | **Target:** develop\n")
res, code = resolve(f, 300)
check("a body-named parent with no native link is refused",
      res["status"] == "error" and codes_of(res) == ["parent-missing"] and code == 2,
      str(res))

# 12. ... but prose naming the issue itself is not a parent claim.
f = Fixture().issue(301, body="Part of #301 is impossible; this is about `parse_slug`.")
res, code = resolve(f, 301)
check("self-referencing prose does not create a parent claim",
      res["row"] == "R1", str(res))

# 13. A declared-but-refused slug is an error, not "no slug" (which would re-route to
#     develop and lose the epic's isolation).
for body, code_want in (("slug: Epic_Integration", "epic-slug-invalid"),
                        ("slug: " + "a" * 21, "epic-slug-too-long"),
                        ("slug: -nope", "epic-slug-invalid")):
    f = Fixture().epic(100, state="OPEN", extra="")
    f.issues[100]["body"] = body + "\nbody"
    f.issue(101, body="**Parent:** #100", parent=100)
    f.children(100, [101])
    res, code = resolve(f)
    check("refused slug `%s` fails closed" % body,
          res["status"] == "error" and codes_of(res) == [code_want] and code == 2, str(res))

# 14. Two open epics sharing a slug: neither may be resolved, because the tool cannot
#     know which one owns the branch.
f = fixture_with_epic(slug="shared")
f.epic(120, slug="shared", extra="")
f.issue(121, body="**Parent:** #120", parent=120)
f.children(120, [121])
res, code = resolve(f)
check("two open epics sharing a slug are refused (rule 2)",
      res["status"] == "error" and codes_of(res) == ["epic-slug-conflict"]
      and "#120" in res["error"] and "one slug is one" in res["error"], str(res))

# 15. An epic/* branch that no open epic declares is not an integration target.
f = fixture_with_epic(slug="claimed")
f.branch("epic/claimed")            # stands, but claimed by this epic - fine
res, _ = resolve(f)
check("a branch its epic declares is accepted", res["row"] == "R2", str(res))
f2 = Fixture().epic(100, slug="orphan")
f2.branch("epic/orphan")
f2.issue(101, body="**Parent:** #100", parent=100)
f2.children(100, [101])
f2.issues[100]["labels"] = []       # not Epic-labelled any more: nobody owns the branch
res, code = resolve(f2)
check("an epic branch no open epic claims is refused",
      res["status"] == "error" and codes_of(res) == ["epic-branch-unclaimed"], str(res))

# 16. A nested epic whose parentage is only in prose cannot decide which branch to use.
f = fixture_with_epic(slug="inner-epic")
f.issues[100]["body"] = "slug: inner-epic\nParent: #99\n"
f.issue(99, body="outer\n", labels=["Epic"])
res, code = resolve(f)
check("an epic whose own parent is prose-only is refused",
      res["status"] == "error" and codes_of(res) == ["parent-missing"], str(res))

# 17. A nested epic under a CLOSED parent is refused: R9 needs an open parent.
f = fixture_with_epic(slug="inner-epic", parent=99)
f.issues[99]["state"] = "CLOSED"
res, code = resolve(f)
check("a nested epic under a closed parent is refused",
      res["status"] == "error" and codes_of(res) == ["epic-parent-closed"], str(res))

# 18. Unreadable metadata fails closed rather than answering "develop".
f = fixture_with_epic()
f.fail.append("issue(number:101)")
res, code = resolve(f)
check("an unreadable issue fails closed", res["status"] == "error" and code == 2, str(res))

f = fixture_with_epic()
f.fail.append("ls-remote")
res, code = resolve(f)
check("an unreadable branch listing fails closed",
      res["status"] == "error" and "ls-remote" in res["error"] and code == 2, str(res))

f = fixture_with_epic(state="CLOSED")
f.issue(101, state="CLOSED", body="done", parent=100)
f.fail.append("subIssues")
res, code = resolve(f)
check("unreadable children of a closed epic fail closed",
      res["status"] == "error" and "children" in res["error"], str(res))

f = fixture_with_epic()
f.fail.append("labels=Epic")
res, code = resolve(f)
check("an unreadable epic listing fails closed", res["status"] == "error", str(res))

f = fixture_with_epic()
f.issues[100]["state"] = "PENDING"
res, code = resolve(f)
check("an epic in a state that is neither OPEN nor CLOSED fails closed",
      res["status"] == "error" and code == 2, str(res))

# ------------------------------------------------------------------- check-pr: targets


def check_pr(f, pr=900, mode="strict", **kw):
    res = m.check_pr(f.runner, pr, repo=f.repo, mode=mode, **kw)
    return res, m.exit_code(res)


# 19. The defect the epic exists to remove: an epic child PR pointed straight at develop.
f = fixture_with_epic()
f.open_pr(900, head="ao/topic/issue-101-thing", base="develop")
res, code = check_pr(f)
check("a child PR into develop is refused (R4)",
      codes_of(res) == ["child-targets-develop"] and res["target"] == "epic/epic-integration"
      and res["row"] == "R5" and code == 1, str(res))

# 20. Same finding in advisory mode, but the exit stays 0: the rollout shape of #1580.
res, code = check_pr(f, mode="advisory")
check("advisory mode reports the violation without failing it",
      codes_of(res) == ["child-targets-develop"] and code == 0, str(res))

# 21. ... and at develop/master both name the permanent branch.
f.open_pr(901, head="ao/topic/issue-101-thing", base="master")
res, code = check_pr(f, pr=901)
check("a child PR into master is refused too", codes_of(res) == ["master-target-violation"],
      str(res))

# 22. The correct base is clean and carries the row and the epic.
f.open_pr(902, head="ao/topic/issue-101-thing", base="epic/epic-integration")
f.ancestor("epic/epic-integration", "b" * 40)
res, code = check_pr(f, pr=902)
check("a child PR into its own epic branch is clean (R2)",
      res["row"] == "R2" and not res["findings"] and res["epic"] == 100 and code == 0,
      str(res))

# 23. A child PR into another epic's branch, or a sibling's branch, is refused (R5).
f.branch("epic/other-epic")
f.open_pr(903, head="ao/topic/issue-101-thing", base="epic/other-epic")
res, code = check_pr(f, pr=903)
check("a child PR into a foreign epic branch is refused (R5)",
      codes_of(res) == ["child-wrong-base"] and res["target"] == "epic/epic-integration",
      str(res))

f.open_pr(904, head="ao/topic/issue-101-thing", base="ao/topic/issue-102-sibling")
res, code = check_pr(f, pr=904)
check("a child PR based on a sibling branch is refused (R5)",
      codes_of(res) == ["child-wrong-base"], str(res))

# 24. R12: the epic moved on, so the child head no longer descends from its head.
f = fixture_with_epic()
f.open_pr(905, head="ao/topic/issue-101-thing", base="epic/epic-integration",
          head_sha="c" * 40)
res, code = check_pr(f, pr=905)
check("a child head that does not descend from the epic head is refused (R12)",
      codes_of(res) == ["child-not-descendant"] and res["row"] == "R12", str(res))

# 24b. --no-ancestry skips exactly R12 - for a shallow checkout where the head object may
#      be absent - and says it did, so a skipped rule cannot be read as a passed one.
f = fixture_with_epic()
f.open_pr(905, head="ao/topic/issue-101-thing", base="epic/epic-integration",
          head_sha="c" * 40)
res, code = check_pr(f, pr=905, ancestry=False)
check("--no-ancestry skips R12 and records the skip",
      res["ancestry"] is False and not res["findings"] and code == 0
      and not [c for c in f.calls if "merge-base" in c], str(res))

# 25. Fork identity: a fork head can never descend from this repository's epic branch.
f = fixture_with_epic()
f.open_pr(906, head="ao/topic/issue-101-thing", base="epic/epic-integration",
          head_repo="someone/r")
res, code = check_pr(f, pr=906)
check("a fork head targeting an epic branch is refused",
      codes_of(res) == ["fork-head-target"] and code == 1, str(res))

# 26. An independent child PR to develop stays clean: epic branches must not become a
#     reason to route unrelated work (rule 6).
f = Fixture().issue(400, body="## Independent\n")
f.open_pr(907, head="fix/issue-400-crash", base="develop")
res, code = check_pr(f, pr=907)
check("an independent PR to develop is clean (R1)",
      res["row"] == "R1" and not res["findings"] and code == 0, str(res))

# 27. A head branch that names no issue cannot be derived: reported, not guessed.
f = fixture_with_epic()
f.open_pr(908, head="my-casual-branch", base="develop")
res, code = check_pr(f, pr=908)
check("a head branch naming no issue is reported", codes_of(res) == ["head-branch-no-issue"],
      str(res))

# 28. An unreadable PR is a fail-closed error, not a pass - and the rollout asymmetry:
#     strict gates on it, advisory reports it without turning a pre-existing pull request
#     red over a gh hiccup, and NEITHER reading can be mistaken for an answer.
f = fixture_with_epic()
res, code = check_pr(f, pr=12345)
check("an unreadable PR fails closed in strict mode",
      res["status"] == "error" and code == 1, str(res))
f = fixture_with_epic()
res, code = check_pr(f, pr=12345, mode="advisory")
check("an unreadable PR stays an error but does not gate while advisory",
      res["status"] == "error" and res["error"] and code == 0
      and codes_of(res) == ["metadata-unreadable"], str(res))
f = fixture_with_epic()
res = m.check_branch(f.runner, 100, repo=f.repo, mode="advisory")
f.fail.append("graphql")
res = m.check_branch(f.runner, 100, repo=f.repo, mode="advisory")
check("check-branch stays an error result while advisory",
      res["status"] == "error" and m.exit_code(res) == 0, str(res))
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("check-branch gates on it once strict",
      res["status"] == "error" and m.exit_code(res) == 1, str(res))
# a mode-less resolve has nothing to gate on and always answers 2.
f = fixture_with_epic()
f.fail.append("graphql")
res, code = resolve(f)
check("resolve has no advisory half: an unreadable parent fails closed",
      res["status"] == "error" and code == 2, str(res))

# 29. An ambiguous issue behind an otherwise-fine PR blocks the verdict.
f = fixture_with_epic()
f.issues[101]["parent"] = None
f.open_pr(909, head="ao/topic/issue-101-thing", base="develop")
res, code = check_pr(f, pr=909)
check("a PR whose issue cannot resolve is metadata-ambiguous",
      codes_of(res) == ["metadata-ambiguous"] and code == 1, str(res))

# ------------------------------------------------------- check-pr: epic-branch heads

# 30. The integration PR: epic/<slug> -> develop is the one legal epic-branch base (R6).
f = fixture_with_epic()
f.open_pr(910, head="epic/epic-integration", base="develop")
res, code = check_pr(f, pr=910)
check("epic branch into develop is the integration PR (R6)",
      res["row"] == "R6" and not res["findings"] and code == 0, str(res))

# 31. ... and anywhere else is refused.
for base in ("release/1.2", "ao/topic/issue-101-thing", "epic/other-epic"):
    f = fixture_with_epic()
    f.branch("epic/other-epic")
    f.open_pr(911, head="epic/epic-integration", base=base)
    res, code = check_pr(f, pr=911)
    check("epic branch into `%s` is refused (R6)" % base,
          codes_of(res) == ["epic-pr-base"] and res["row"] == "R6", str(res))
# A base of master is answered by the permanent-pair rule, which is the stronger one.
f = fixture_with_epic()
f.open_pr(911, head="epic/epic-integration", base="master")
res, code = check_pr(f, pr=911)
check("epic branch into master is refused (R13)",
      codes_of(res) == ["master-target-violation"] and res["row"] == "R13", str(res))

# 32. A nested epic integrates upward, not outward (R9).
f = fixture_with_epic(slug="inner-epic", parent=99)
f.branch("epic/outer-epic")
f.open_pr(912, head="epic/inner-epic", base="develop")
res, code = check_pr(f, pr=912)
check("nested epic straight into develop is refused (R9)",
      codes_of(res) == ["nested-epic-base"] and res["target"] == "epic/outer-epic", str(res))
f.open_pr(913, head="epic/inner-epic", base="epic/outer-epic")
res, code = check_pr(f, pr=913)
check("nested epic into its parent's branch is clean (R9)",
      res["row"] == "R9" and not res["findings"] and code == 0, str(res))

# 33. R13 keeps working for the pair it was written for - and the fork case.
f = Fixture()
f.open_pr(914, head="develop", base="master")
res, code = check_pr(f, pr=914)
check("develop -> master stays allowed (R13)", not res["findings"] and code == 0, str(res))
f.open_pr(915, head="feature/x", base="master")
res, code = check_pr(f, pr=915)
check("a feature branch may not target master (R13)",
      codes_of(res) == ["master-target-violation"] and code == 1, str(res))
f.open_pr(916, head="develop", base="master", head_repo="fork/r")
res, code = check_pr(f, pr=916)
check("a fork's develop may not target master (R13)",
      codes_of(res) == ["master-target-violation"], str(res))

# 34. An epic-branch PR is checked without ever reading an issue.
f = fixture_with_epic()
f.open_pr(917, head="epic/epic-integration", base="develop")
res, code = check_pr(f, pr=917)
check("an epic-branch PR needs no issue resolution",
      not [c for c in f.calls if "issue(number:101)" in c], str(f.calls))

# 34b. An `epic/*` head no open epic declares is the rule-2 refusal, not a gh hiccup.
#      Before this the branch fell through to `_epic_for_branch`, answered None, and the
#      PR was reported clean against `develop`: rule 2 was silent exactly where CI asks it.
f = Fixture()
f.epic(100, slug="epic-integration")
f.branch("epic/stray")
f.open_pr(918, head="epic/stray", base="develop")
res, code = check_pr(f, pr=918)
check("an epic branch no epic declares is refused (rule 2)",
      res["status"] == "error" and codes_of(res) == ["epic-branch-unclaimed"]
      and code == 1, str(res))

# 34c. ... and it keeps that code when the branch is missing too: `gh` answered perfectly
#      well, so collapsing the refusal into `metadata-unreadable` would tell the author to
#      fix their network instead of their slug declaration.
f = Fixture()
f.epic(100, slug="epic-integration")
f.open_pr(919, head="epic/stray", base="develop")
res, code = check_pr(f, pr=919)
check("an unowned epic head missing on origin still reports rule 2, not unreadable",
      res["status"] == "error" and codes_of(res) == ["epic-branch-unclaimed"]
      and "gh" not in res["error"], str(res))

# 34d. The branch of a CLOSED epic is rule 11's stale branch, not rule 2's unowned one:
#      ownership is measured over open and closed epics, exactly as `_slug_conflict` does.
f = fixture_with_epic(state="CLOSED")
f.open_pr(920, head="epic/epic-integration", base="develop")
res, code = check_pr(f, pr=920)
check("an epic branch whose epic closed is stale, not unowned (R6, R11)",
      codes_of(res) == ["epic-branch-stale"] and res["row"] == "R6" and code == 1,
      str(res))

# 34e. A fork may not present an epic integration: the branch is a branch of THIS repo.
f = fixture_with_epic()
f.open_pr(921, head="epic/epic-integration", base="develop", head_repo="someone/r")
res, code = check_pr(f, pr=921)
check("a fork head named like the epic branch is refused (R12)",
      codes_of(res) == ["fork-head-target"] and res["row"] == "R12" and code == 1,
      str(res))

# 34f. An owned epic branch deleted from origin under a still-open PR is rule 3's missing
#      branch, and the message names the protected path that puts it back.
f = fixture_with_epic(branch=False)
f.open_pr(922, head="epic/epic-integration", base="develop")
res, code = check_pr(f, pr=922)
check("an epic head that no longer stands on origin is refused (rule 3)",
      codes_of(res) == ["epic-branch-missing"] and res["row"] == "R6"
      and "create-branch" in res["findings"][0]["message"], str(res))

# 34g. The develop side of the same rule: a child PR of a SLUGLESS epic stays clean while
#      the epic bootstraps (R3), and a child of a slugless epic is never reported as an
#      independent issue - the rows are what #1594 counts.
f = fixture_with_epic(slug=None)
f.open_pr(923, head="agent/issue-101", base="develop")
res, code = check_pr(f, pr=923)
check("a child PR to develop while its epic has no slug is the bootstrap row (R3)",
      res["row"] == "R3" and res["target"] == "develop" and not res["findings"]
      and code == 0, str(res))
f = fixture_with_epic()
f.open_pr(924, head="agent/issue-101", base="develop")
res, code = check_pr(f, pr=924)
check("a child PR to develop once its epic has a slug is still the violation (R4/R5)",
      res["row"] == "R5" and codes_of(res) == ["child-targets-develop"], str(res))
f = Fixture()
f.issue(404, body="## Independent\n")
f.open_pr(925, head="agent/issue-404", base="develop")
res, code = check_pr(f, pr=925)
check("a genuinely independent PR to develop reports R1, not R3",
      res["row"] == "R1" and res["target"] == "develop" and not res["findings"], str(res))
f = fixture_with_epic(state="CLOSED")
f.issue(101, body="done", parent=100, state="CLOSED")
f.merged_pr(500, 101, base="epic/epic-integration", sha="a" * 40, on_base=True)
f.open_pr(926, head="agent/issue-101", base="develop")
res, code = check_pr(f, pr=926)
check("a follow-up PR after a merged epic reports R10, not R1",
      res["row"] == "R10" and not res["findings"], str(res))

# -------------------------------------------------------------- check-branch and audit

# 35. A missing branch, a missing slug and a stale branch are each their own finding.
f = fixture_with_epic(branch=False)
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("an open epic without its branch is reported",
      codes_of(res) == ["epic-branch-missing"] and m.exit_code(res) == 1, str(res))
f = fixture_with_epic(slug=None)
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("an open epic without a slug is reported", codes_of(res) == ["epic-slug-missing"],
      str(res))
f = fixture_with_epic(state="CLOSED")
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("a branch standing over a closed epic is reported",
      codes_of(res) == ["epic-branch-stale"], str(res))
f = fixture_with_epic()
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("a healthy epic branch is clean", not res["findings"] and m.exit_code(res) == 0,
      str(res))
f = fixture_with_epic(slug="UPPER")
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("a refused slug is reported by check-branch", codes_of(res) == ["epic-slug-invalid"],
      str(res))
f = fixture_with_epic()
f.fail.append("graphql")
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
check("check-branch fails closed", res["status"] == "error" and m.exit_code(res) == 1,
      str(res))

# 36. The audit is the rollout view: one entry per open epic, findings collected.
f = fixture_with_epic(branch=False)
f.epic(130, slug=None)
res = m.audit(f.runner, repo=f.repo, mode="advisory")
codes = sorted({x["code"] for x in res["findings"]})
check("audit covers every open epic and collects findings",
      [e["epic"] for e in res["epics"]] == [100, 130]
      and codes == ["epic-branch-missing", "epic-slug-missing"], str(codes))
f.branch("epic/epic-integration")
res = m.audit(f.runner, repo=f.repo, mode="advisory")
check("audit reports nothing extra for a healthy epic",
      sorted({x["code"] for x in res["findings"]}) == ["epic-slug-missing"], str(res))

# 37. ... and with the wider scope, the open PRs whose head names an issue.
f = fixture_with_epic()
f.open_pr(920, head="ao/topic/issue-101-thing", base="develop")
f.open_pr(921, head="chore/unrelated", base="develop")
res = m.audit(f.runner, repo=f.repo, mode="strict", scope="all-approved")
check("audit all-approved screens only PRs whose head names an issue",
      [p["pr"] for p in res["pulls"]] == [920]
      and codes_of(res["pulls"][0]) == ["child-targets-develop"], str(res["pulls"]))

# ------------------------------------------------------------------- the write paths

# 38. A dry run reads everything and pushes nothing.
f = fixture_with_epic(branch=False)
res = m.create_branch(f.runner, 100, write=False, repo=f.repo)
check("create-branch dry run pushes nothing",
      res["created"] is False and not f.pushes and res["branchSha"] == DEVELOP_SHA
      and m.exit_code(res) == 0, str(res))

# 39. --write pushes exactly one new branch, at origin/develop's tip.
f = fixture_with_epic(branch=False)
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("create-branch pushes the new branch at origin/develop",
      f.pushes == ["git push origin %s:refs/heads/epic/epic-integration" % DEVELOP_SHA]
      and res["created"] is True, str(f.pushes))

# 40. Idempotent: an existing epic branch is reused, never pushed to.
f = fixture_with_epic()
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("an existing epic branch is reused, never pushed to",
      not f.pushes and res["created"] is False and res["branchSha"] == EPIC_SHA, str(res))

# 41. Nothing is created from an identity the contract refuses.
f = fixture_with_epic(slug=None, branch=False)
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("no branch is created for an unslugged epic",
      codes_of(res) == ["epic-slug-missing"] and not f.pushes, str(res))
f = fixture_with_epic(slug="Bad_Slug", branch=False)
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("no branch is created from a refused slug",
      codes_of(res) == ["epic-slug-invalid"] and not f.pushes, str(res))
f = fixture_with_epic(state="CLOSED", branch=False)
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("no branch is created for a closed epic",
      codes_of(res) == ["epic-not-open"] and not f.pushes, str(res))
f = fixture_with_epic(slug="shared", branch=False)
f.epic(120, slug="shared")
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("no branch is created when a slug collides",
      codes_of(res) == ["epic-slug-conflict"] and not f.pushes, str(res))

# 42. The agent identity may not create a branch (rule 15).
f = fixture_with_epic(branch=False)
f.agent_bot = True
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("the agent identity cannot create a branch",
      res["status"] == "error" and "person's acts" in res["error"] and not f.pushes,
      str(res))
# ... but a dry run needs no identity at all.
f = fixture_with_epic(branch=False)
f.agent_bot = True
res = m.create_branch(f.runner, 100, write=False, repo=f.repo)
check("the agent identity may still ask what would happen",
      res["created"] is False and not f.pushes, str(res))

# 43. A failing push is an error, not a half-created branch.
f = fixture_with_epic(branch=False)
f.fail.append("git push")
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
check("a failing push fails closed", res["status"] == "error" and "push" in res["error"],
      str(res))

# 44. Retarget: only onto the resolved target, only for an open PR, only with --write.
f = fixture_with_epic()
f.open_pr(930, head="ao/topic/issue-101-thing", base="develop")
res = m.retarget(f.runner, 930, "epic/epic-integration", write=False, repo=f.repo)
check("retarget dry run writes nothing",
      res["retargeted"] is False and not f.patches and res["base"] == "develop", str(res))
res = m.retarget(f.runner, 930, "epic/epic-integration", write=True, repo=f.repo)
check("retarget patches the base once",
      len(f.patches) == 1 and "-f base=epic/epic-integration" in f.patches[0], str(f.patches))
f = fixture_with_epic()
f.open_pr(931, head="ao/topic/issue-101-thing", base="develop")
res = m.retarget(f.runner, 931, "develop", write=True, repo=f.repo)
check("retarget refuses a base the contract does not name",
      codes_of(res) == ["wrong-target"] and not f.patches, str(res))
f = fixture_with_epic()
f.open_pr(932, head="ao/topic/issue-101-thing", base="develop", state="closed")
res = m.retarget(f.runner, 932, "epic/epic-integration", write=True, repo=f.repo)
check("retarget refuses a closed PR", codes_of(res) == ["pr-not-open"], str(res))
f = fixture_with_epic()
f.open_pr(933, head="casual", base="develop")
res = m.retarget(f.runner, 933, "epic/epic-integration", write=True, repo=f.repo)
check("retarget refuses a head naming no issue", codes_of(res) == ["head-branch-no-issue"],
      str(res))
f = fixture_with_epic()
f.open_pr(934, head="ao/topic/issue-101-thing", base="develop")
f.agent_bot = True
res = m.retarget(f.runner, 934, "epic/epic-integration", write=True, repo=f.repo)
check("the agent identity cannot retarget", res["status"] == "error" and not f.patches,
      str(res))

# ------------------------------------------------------------------------ the renderer

# 44. Human output is keyed by the subcommand, never by which optional keys are filled.
#     A `resolve` of an independent issue carries `branch: develop` and no epic, and a
#     `retarget` carries an `epic` and no findings, so a renderer that sniffed the keys
#     printed the first as an epic branch of epic #None and dropped the base transition
#     the second exists to report. Each verb's line is asserted on its own content.
r = m.render_human(m.resolve_issue(Fixture().issue(410, body="x").runner, 410,
                                   repo="o/r"))
check("resolve names the issue, target and row, and invents no epic",
      r.startswith("#410  target develop  row R1") and "epic #" not in r, r)
f = fixture_with_epic()
f.open_pr(940, head="agent/issue-101", base="develop")
res, _ = check_pr(f, pr=940)
r = m.render_human(res)
check("check-pr names the PR, the head, the base and the target",
      r.startswith("PR #940  agent/issue-101 -> develop  target epic/epic-integration")
      and "row R5" in r and "child-targets-develop" in r, r)
f = fixture_with_epic()
res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
r = m.render_human(res)
check("check-branch names the epic and its branch",
      r.startswith("epic #100  branch epic/epic-integration"), r)
f = fixture_with_epic()
f.open_pr(941, head="ao/topic/issue-101-thing", base="develop")
res = m.retarget(f.runner, 941, "epic/epic-integration", write=False, repo=f.repo)
r = m.render_human(res)
check("retarget reports the base transition it was asked about",
      "PR #941  base develop -> epic/epic-integration" in r
      and "dry run: nothing written" in r, r)
f = fixture_with_epic()
res = m.audit(f.runner, repo=f.repo, mode="advisory")
r = m.render_human(res)
check("audit reports its own scope and counts",
      r.startswith("audit of o/r  scope epic  mode advisory"), r)
check("every public builder stamps its envelope with its own verb",
      all(getattr(builder, "_verb", None) == verb
          for builder, verb in ((m.resolve_issue, "resolve"), (m.check_pr, "check-pr"),
                                (m.check_branch, "check-branch"), (m.audit, "audit"),
                                (m.create_branch, "create-branch"),
                                (m.retarget, "retarget"))),
      ", ".join("%s=%s" % (b.__name__, getattr(b, "_verb", None)) for b in
                (m.resolve_issue, m.check_pr, m.check_branch, m.audit,
                 m.create_branch, m.retarget)))
f = fixture_with_epic(branch=False)
f.agent_bot = True
res = m.create_branch(f.runner, 100, write=True, repo=f.repo)
r = m.render_human(res)
check("a refused write verb still renders its own shape",
      r.startswith("ERROR") and "person's acts" in res["error"], r)
res = m._result()
res["status"] = "ok"
check("an unstamped envelope is named unknown, not guessed at",
      m.render_human(res).startswith("unrecognised result"), m.render_human(res))

# ------------------------------------------------------------------ vocabulary drift

# 45. Every code this suite ever saw is a code the tool declares, and the docs page
#     promises exactly the declared list.
seen = set()
for f in [fixture_with_epic(), fixture_with_epic(branch=False), fixture_with_epic(slug=None)]:
    res, _ = resolve(f)
    seen |= set(codes_of(res))
    res = m.check_branch(f.runner, 100, repo=f.repo, mode="strict")
    seen |= set(codes_of(res))
declared = m.EMITTED_CODES
check("every reported code is in the tool's declared vocabulary",
      seen <= declared and "child-targets-develop" in declared and len(declared) >= 15,
      "missing=%s" % sorted(seen - declared))

# 46. The documentation page promises its list of codes IS the tool's list, exactly as
#     the classification page does for pr_classify. Parsing the page's ``code`` spans
#     rather than trusting a hand-copied table is what keeps the two honest as the tool
#     grows: a new Finding appears in `codes` without anybody editing the page, and a
#     code invented in the page names nothing the tool can report.
DOCS = os.path.join(os.path.dirname(HERE), "docs", "source", "development",
                    "epic-branch-resolution.rst")
try:
    with open(DOCS, encoding="utf-8") as handle:
        page = handle.read()
except OSError as exc:
    page = None
    check("the documentation page exists", False, str(exc))
if page is not None:
    import re as _re
    # Only the first column of the finding table, and only below its own heading: double
    # backticks elsewhere carry command names and the agent identity, which are not part
    # of the vocabulary and must not be able to enter the comparison.
    section = page.split("Finding codes", 1)[-1].split("\nTests\n", 1)[0]
    listed = set()
    for row in _re.findall(r"(?m)^\s+\* - (.+)$", section):
        listed.update(_re.findall(r"``([a-z][a-z-]+)``", row))
    check("every documented code is one the tool emits", listed <= declared,
          "invented: %s" % ", ".join(sorted(listed - declared)))
    check("every emitted code is documented", declared <= listed,
          "undocumented: %s" % ", ".join(sorted(declared - listed)))
    check("the page names the contract it implements",
          "epic-integration-contract" in page and "next_eligible" in page,
          "the page must link the contract and the eligibility screen it does not replace")

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
