#!/usr/bin/env python3
"""next_eligible: stateless eligibility screen for schedulable issues.

Maintenance tool carried by this repository; run it as
`python3 scripts/next_eligible.py` from the repository root. It answers one
question for an orchestrator or a person: which issues may a worker be
started on right now - the sub-issues of one epic (scope epic, the default)
or every open issue carrying a human `agent: approved` (scope all-approved)? It is STATELESS (it writes no claim, comment
or label - read-only toward GitHub and the repository, its only local side
effect being the `git fetch` of the base ref that Rule 4 requires) and it
RUNS ONCE: no daemon, no polling loop. The caller decides when to run it
again.

Usage:
  python3 scripts/next_eligible.py [--scope S] [--epic N] [--json] [--dry-run]
                                   [--humans a,b] [--ignore-stale-branches]
                                   [--ignore-approval-provenance-for-testing]

  --scope S         epic (default): screen the sub-issues of --epic.
                    all-approved: screen every open issue of the repository
                    that carries `agent: approved` - a human approval admits
                    an issue wherever it lives, epic membership is not
                    required. Rules 2 to 6 apply unchanged; the candidate
                    listing replaces Rule 1 (see below), and `Epic`-labelled
                    issues are rejected as containers.
  --epic N          epic issue to screen (default 1256; scope epic only)
  --json            print the machine-readable result as JSON on stdout
  --dry-run         the only mode this tool has: read-only evaluation with no
                    side effect beyond the base-ref fetch; the flag exists so
                    a caller can state its intent explicitly
  --humans a,b,c    replace the approver allowlist (also via the environment
                    variable AGENT_EPIC_APPROVERS, a comma list; the default
                    allowlist is `jokiefer` - only a person grants approvals,
                    this tool only verifies them)
  --ignore-stale-branches
                    do not reject candidates for an origin branch of the
                    issue-<N> pattern standing without an open PR (the tool
                    cannot see agent sessions, so this flag is the operator's
                    statement that no session owns that branch)
  --ignore-approval-provenance-for-testing
                    testing only, default OFF: skip Rule 2 (the `agent:
                    approved` label and its provenance) so the dependency
                    screen can be evaluated on its own. Loudly bannered in
                    every output and recorded in the JSON `flags`.

SELECTION RULES - a candidate is eligible only when ALL hold; every rejection
carries a machine-readable reason token (the part before ':' in a verdict's
reasons):

  1. open native sub-issue of the epic (GraphQL subIssues; the listing order
     of that connection is the priority order, ties by ascending number)
  2. label `agent: approved` present AND provenance verified: the labeled
     event that applied the current approval was carried by an authorized
     human - actors of __typename Bot or App are rejected, the login
     mrmap-agent-bot is rejected even if allowlisted, and every other actor
     must be on the approver allowlist; an empty allowlist fails closed
  3. label `agent: paused` absent
  4. every native blocked_by blocker (GraphQL blockedBy) is SATISFIED: state
     CLOSED, stateReason COMPLETED, and at least one PR that closed it
     (closedByPullRequestsReferences) is MERGED with baseRefName of the base
     branch and a merge commit that is an ancestor of origin/<base> (git
     merge-base --is-ancestor after git fetch origin <base>). A blocker
     closed without such a PR is NOT satisfied - closing an issue is not
     implementing it
  5. no active `scripts/wip` claim on it, local or remote - the discovery
     `wip ls` itself uses: `status: wip` labelled issues with their claim
     comments, plus the local worktrees whose branch names the issue
  6. no open PR represents it - a PR that closes it (the GraphQL search of
     open PRs: the native closing-issue relation and the `Closes #N` body
     convention) or whose head branch names it -> duplicate; an origin branch
     naming it without any open PR -> stale-branch-ownership, unless
     --ignore-stale-branches

  SCOPE all-approved replaces Rule 1's listing: candidates are every open
  issue of the repository carrying `agent: approved`, read through one
  fail-closed paginated GraphQL search; their priority order is oldest
  creation first, ties by number (an epic has a curated sub-issue order, the
  repository at large has none). Rules 2 to 6 apply unchanged, and an issue
  labelled `Epic` is rejected - a container is scheduled through its
  sub-issues, not spawned as a worker.

FAIL CLOSED: nothing is spawned on any doubt. An unauthenticated gh, a failing
or permission-denied GitHub call, null/ambiguous sub-issue, dependency or
event data, an empty allowlist, and a failing git fetch / merge-base all
produce status "error" with a non-zero exit and no eligible list - never a
guess. Exit 0 with results otherwise; `--json` also prints a result object in
the error case (keys: schema, status, error).

NOTE ON THE MERGE COMMIT: GitHub's public GraphQL schema carries no merge
commit on the PullRequest type (mergeCommitOid is not a public field), so the
merge-commit SHA is read from the REST view of the PR that the GraphQL
closedByPullRequestsReferences connection names - the same fact, the field
that exists.

The offline suite is scripts/test_next_eligible.py (fixture-driven, injected
command runner, no gh and no network), as every suite under scripts/.
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from subprocess import TimeoutExpired

SCHEMA = "next-eligible/v2"  # v1 had no scope field
SCOPE_EPIC = "epic"
SCOPE_ALL_APPROVED = "all-approved"
DEFAULT_EPIC = 1256
CMD_TIMEOUT = 120
DEFAULT_APPROVERS = "jokiefer"
APPROVERS_ENV = "AGENT_EPIC_APPROVERS"
BASE_BRANCH = "develop"
APPROVED_LABEL = "agent: approved"
PAUSED_LABEL = "agent: paused"
EPIC_LABEL = "Epic"
DENIED_LOGINS = {"mrmap-agent-bot"}
ACTIVE_CLAIM_STATES = ("wip", "waiting")

SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
# The branch convention of this repository: a path segment starting with
# issue-<N>; a bare digit run inside a slug names no issue (see scripts/wip).
BRANCH_ISSUE_RE = re.compile(r"(?:^|/)(?:issue[-_]?|#)(\d+)")
# The GitHub closing keywords, the shape `Closes #N` is one instance of.
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)", re.I)


class CommandError(Exception):
    """A gh or git call failed; the tool fails closed on it.

    exit_code carries the command's exit status when there was one, so a
    caller can read a defined non-zero status (git merge-base answers 1 for
    "not an ancestor") without parsing text.
    """

    exit_code = None


class EligibilityError(Exception):
    """Why the whole screen failed closed; nothing may be spawned on it."""


def subprocess_runner(argv):
    """Run argv, return stdout, raise CommandError on a non-zero exit or timeout.

    A command that hangs is a failure like any other: the caller fails closed
    with a status=error result instead of waiting on a stuck gh or network.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except (OSError, TimeoutExpired) as e:
        raise CommandError("%s could not be run: %s" % (" ".join(argv[:3]), e))
    if proc.returncode != 0:
        err = CommandError("%s exited %d: %s" % (" ".join(argv[:3]), proc.returncode,
                                                 (proc.stderr or proc.stdout or "").strip()))
        err.exit_code = proc.returncode
        raise err
    return proc.stdout or ""


def gh_graphql(runner, query):
    """Run one GraphQL query through gh; errors and missing data fail closed."""
    try:
        out = runner(["gh", "api", "graphql", "-f", "query=" + query])
    except CommandError as e:
        raise EligibilityError("the GitHub GraphQL call failed (a missing permission reads "
                               "the same way): %s" % e)
    try:
        doc = json.loads(out or "")
    except ValueError:
        raise EligibilityError("GitHub GraphQL returned something that is not JSON")
    if not isinstance(doc, dict):
        raise EligibilityError("GitHub GraphQL returned no response object")
    if doc.get("errors"):
        raise EligibilityError("GitHub GraphQL error: "
                               + "; ".join(str(e.get("message", e)) for e in doc["errors"]))
    if not isinstance(doc.get("data"), dict):
        raise EligibilityError("GitHub GraphQL returned no data")
    return doc["data"]


def gh_rest_items(runner, path):
    """All items of a paginated REST listing; a truncated listing fails closed."""
    out = runner(["gh", "api", path, "--paginate"])
    items, dec, pos = [], json.JSONDecoder(), 0
    while pos < len(out):
        while pos < len(out) and out[pos] in " \n\r\t":
            pos += 1
            continue
        try:
            obj, pos = dec.raw_decode(out, pos)
        except ValueError:
            raise EligibilityError("GitHub REST %s returned something that is not JSON" % path)
        items.extend(obj if isinstance(obj, list) else [obj])
    return items


def connection(data, *path, what):
    """The nodes of a GraphQL connection, its totalCount and whether it is whole.

    A null connection or a node count beyond totalCount is ambiguous data -
    the tool refuses to screen on data it cannot trust.
    """
    cur = data
    for key in path:
        cur = (cur or {}).get(key)
    if not isinstance(cur, dict) or not isinstance(cur.get("nodes"), list) \
            or any(n is None for n in cur["nodes"]):
        raise EligibilityError("GraphQL %s connection is null or contains a null node" % what)
    nodes = cur["nodes"]
    total = cur.get("totalCount")
    if not isinstance(total, int) or len(nodes) > total:
        raise EligibilityError("GraphQL %s connection reports an inconsistent totalCount" % what)
    page = cur.get("pageInfo") or {}
    if page.get("hasNextPage") or len(nodes) < total:
        raise EligibilityError("GraphQL %s connection is not fully readable (%d of %s)"
                               % (what, len(nodes), total))
    return nodes


def resolve_repo(runner):
    out = runner(["gh", "repo", "view", "--json", "nameWithOwner"])
    try:
        return json.loads(out)["nameWithOwner"]
    except (ValueError, KeyError, TypeError):
        raise EligibilityError("could not read the repository of this checkout")


def fetch_base(runner, base):
    """Update origin/<base> (the one write this tool makes, demanded by Rule 4)."""
    try:
        runner(["git", "fetch", "origin", base])
    except CommandError as e:
        raise EligibilityError("git fetch origin %s failed, so merge ancestry cannot be "
                               "trusted: %s" % (base, e))


def origin_branches(runner):
    """Branch names on origin; ls-remote reads them without writing any ref."""
    try:
        out = runner(["git", "ls-remote", "--heads", "origin"])
    except CommandError as e:
        raise EligibilityError("git ls-remote origin failed: %s" % e)
    names = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            names.add(parts[1][len("refs/heads/"):])
    return names


def merge_commit_on_base(runner, sha, base):
    """True when the merge commit is an ancestor of origin/<base>.

    exit 0 -> ancestor, exit 1 -> not yet (a merged PR whose merge commit is
    not on the base branch does not satisfy a blocker), any other exit -> the
    question could not be asked and the tool fails closed.
    """
    if not SHA_RE.match(sha or ""):
        raise EligibilityError("merge commit %r is not a commit SHA - refusing to guess" % sha)
    try:
        runner(["git", "merge-base", "--is-ancestor", sha, "origin/" + base])
        return True
    except CommandError as e:
        if getattr(e, "exit_code", None) == 1:
            return False
        raise EligibilityError("git merge-base --is-ancestor %s origin/%s failed: %s"
                               % (sha, base, e))
    except TimeoutExpired as e:
        raise EligibilityError("git merge-base --is-ancestor %s origin/%s timed out: %s"
                               % (sha, base, e))


def open_pulls(runner, repo):
    """Open PRs of the repository: number, head branch, body, machine-readable closes.

    One GraphQL search connection, paginated, instead of one search per
    candidate: it carries the head branch name, the body (for the `Closes #N`
    convention this repository's PRs write) and the native closing-issue
    relation, so Rule 6 reads its whole input in one pass. type:ISSUE also
    returns plain issues that matched the query text - they are skipped, they
    are not ambiguous data.
    """
    prs, after, seen = [], None, 0
    total = None
    while True:
        q = ('{search(query:"repo:%s is:pr is:open",type:ISSUE,first:100%s)'
             '{issueCount pageInfo{hasNextPage endCursor} nodes{__typename ... on PullRequest'
             '{number headRefName body closingIssuesReferences(first:100)'
             '{nodes{number}}}}}}' % (repo, ',after:"%s"' % after if after else ""))
        search = gh_graphql(runner, q).get("search")
        if not isinstance(search, dict) or not isinstance(search.get("nodes"), list):
            raise EligibilityError("the open-PR search returned no result set")
        if total is None:
            total = search.get("issueCount")
        elif search.get("issueCount") != total:
            raise EligibilityError("the open-PR search result changed while it was read")
        for n in search["nodes"]:
            seen += 1
            if n.get("__typename") != "PullRequest":
                continue  # a plain issue matched the query text
            if not isinstance(n.get("number"), int) or not isinstance(n.get("headRefName"), str):
                raise EligibilityError("the open-PR search returned a PR without a number or branch")
            closing = n.get("closingIssuesReferences")
            if not isinstance(closing, dict) or not isinstance(closing.get("nodes"), list):
                raise EligibilityError("PR #%d reports no closing-issue relation to read"
                                       % n["number"])
            prs.append({"number": n["number"], "head": n["headRefName"],
                        "body": n.get("body") or "",
                        "closes": [c.get("number") for c in closing["nodes"]
                                   if isinstance(c.get("number"), int)]})
        page = search.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        if not page.get("endCursor"):
            raise EligibilityError("the open-PR search page ends without a cursor")
        after = page["endCursor"]
    # GitHub's search stops at 1000 results whatever the pages say; a screen
    # that missed an open PR would call an issue free when it is taken.
    if not isinstance(total, int) or seen < total:
        raise EligibilityError("the open-PR search could only read %d of %s results"
                               % (seen, total))
    return prs


def approved_candidates(runner, repo):
    """Every open issue carrying the approval label, oldest creation first.

    The candidate listing of scope all-approved. Same discipline as
    open_pulls: one paginated search connection and a result set that cannot
    be read whole fails closed - screening a partial queue would starve an
    approved issue that sits on an unread page. The search pre-filters the
    label; Rule 2 still verifies the label and its provenance per candidate,
    because a search index is eventual-consistent and an approval is never
    inferred from a query match.
    """
    found, after, seen, total = [], None, 0, None
    while True:
        q = ('{search(query:"repo:%s is:issue is:open label:\\"%s\\"",type:ISSUE'
             ',first:100%s){issueCount pageInfo{hasNextPage endCursor}'
             'nodes{__typename ... on Issue{number title state createdAt'
             ' labels(first:100){totalCount pageInfo{hasNextPage} nodes{name}}}}}}'
             % (repo, APPROVED_LABEL, ',after:"%s"' % after if after else ""))
        search = gh_graphql(runner, q).get("search")
        if not isinstance(search, dict) or not isinstance(search.get("nodes"), list):
            raise EligibilityError("the approved-issue search returned no result set")
        if total is None:
            total = search.get("issueCount")
        elif search.get("issueCount") != total:
            raise EligibilityError("the approved-issue search result changed while it was read")
        for n in search["nodes"]:
            seen += 1
            if n.get("__typename") != "Issue":
                continue  # the query asks for issues; anything else is noise, not data
            if not isinstance(n.get("number"), int) or not isinstance(n.get("createdAt"), str):
                raise EligibilityError("the approved-issue search returned an issue without "
                                       "a number or a creation time")
            if n.get("state") != "OPEN":
                raise EligibilityError("#%d matched the open-issue search but reports state %s"
                                       % (n["number"], n.get("state")))
            labels = [lab.get("name") for lab in
                      connection(n, "labels", what="labels of #%d" % n["number"])
                      if isinstance(lab.get("name"), str)]
            if APPROVED_LABEL not in labels:
                raise EligibilityError("#%d came back from the `%s` search without carrying "
                                       "the label the search filtered on" % (n["number"],
                                                                              APPROVED_LABEL))
            found.append({"number": n["number"], "title": n.get("title") or "",
                          "labels": labels, "createdAt": n["createdAt"]})
        page = search.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        if not page.get("endCursor"):
            raise EligibilityError("the approved-issue search page ends without a cursor")
        after = page["endCursor"]
    if not isinstance(total, int) or seen < total:
        raise EligibilityError("the approved-issue search could only read %d of %s results"
                               % (seen, total))
    # No curated order exists outside an epic; FIFO by creation is the one
    # deterministic order that never reorders itself while issues are added.
    found.sort(key=lambda c: (c["createdAt"], c["number"]))
    return found


def load_wip():
    """Import scripts/wip (no extension) the way its own suite does."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wip")
    if not os.path.exists(path):
        raise EligibilityError("scripts/wip not found next to this tool - the claim state "
                               "of issues cannot be read")
    spec = importlib.util.spec_from_loader("wip", importlib.machinery.SourceFileLoader("wip", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def claim_scan(runner, repo):
    """{issue: why} for issues `scripts/wip ls` would show as claimed - or local.

    Reuses scripts/wip's own discovery and parsing rather than reimplementing
    it: the `status: wip` labelled issues with their claim comments (remote
    claims included), plus the local worktrees whose branch names an issue.
    `wip ls` prints both, and both mean somebody is already on it. The claim
    comments are the truth; the label only widens the scan, as it does there.
    """
    try:
        wip = load_wip()
        wip.sh = lambda cmd, input=None, check=True: runner(cmd)
        claimed = {}
        labeled = wip.labeled_issues(repo)
        for n, payloads in wip.claims_index(repo, sorted(labeled)).items():
            if any(p.get("state") in ACTIVE_CLAIM_STATES for _, p in payloads):
                claimed[n] = "an active claim is held on #%d (`scripts/wip ls`)" % n
        for t in wip.worktrees():
            n = wip.branch_issue(t.get("branch", ""))
            if n and n not in claimed:
                claimed[n] = "local worktree `%s` already works on #%d" % (t.get("branch"), n)
        return claimed
    except CommandError as e:
        raise EligibilityError("the wip claim scan failed: %s" % e)


def approval_verdict(runner, repo, num, labels, approvers, ignore_provenance):
    """Rule 2: the approval label with verified human provenance."""
    if ignore_provenance:
        return []
    if APPROVED_LABEL not in labels:
        return ["not-approved: the issue does not carry `%s`" % APPROVED_LABEL]
    if not approvers:
        return ["allowlist-empty: no approver allowlist is in effect, so no approval can "
                "be honoured - pass --humans or set %s" % APPROVERS_ENV]
    try:
        # --paginate follows every Link page, so this listing is complete: the
        # labeled event of an approval applied long ago is still in it.
        events = gh_rest_items(runner, "repos/%s/issues/%d/events?per_page=100" % (repo, num))
    except CommandError as e:
        raise EligibilityError("reading the labeled events of #%d failed: %s" % (num, e))
    decisive = None
    for ev in events:
        if not isinstance(ev, dict) or ev.get("event") not in ("labeled", "unlabeled"):
            continue
        if ((ev.get("label") or {}).get("name")) == APPROVED_LABEL:
            decisive = ev
    if decisive is None:
        raise EligibilityError("#%d carries `%s` but its events show no labeled event for it "
                               "- provenance is unverifiable" % (num, APPROVED_LABEL))
    if decisive["event"] == "unlabeled":
        return ["approval-unlabeled: the last `%s` event on #%d removed the label; its "
                "presence again cannot be attributed" % (APPROVED_LABEL, num)]
    actor = decisive.get("actor") or {}
    login = actor.get("login") or ""
    typename = actor.get("__typename") or ""
    if typename in ("Bot", "App") or login.lower() in DENIED_LOGINS:
        return ["approval-by-bot: `%s` (%s) applied `%s` to #%d - a bot cannot approve"
                % (login or typename, typename or "unknown type", APPROVED_LABEL, num)]
    if login.lower() not in {a.lower() for a in approvers}:
        return ["approval-by-unlisted-human: `%s` applied `%s` to #%d and is not on the "
                "approver allowlist" % (login, APPROVED_LABEL, num)]
    return []


def blocker_state(data):
    if data == "OPEN":
        return "open"
    if data == "CLOSED":
        return "closed"
    raise EligibilityError("a blocker reported issue state %r, which is not open or closed" % data)


def blocker_verdicts(runner, repo, num, base, cache):
    """Rule 4: every blocked_by blocker of #num, satisfied or named.

    A PR satisfies a blocker only as a whole: MERGED, merged into the base
    branch, and its merge commit reachable from origin/<base>. The reason
    names how far it got, so a caller can tell "nothing was implemented"
    from "implemented, but not where this epic is integrated".
    """
    owner, name = repo.split("/")
    q = ('{repository(owner:"%s",name:"%s"){issue(number:%d){blockedBy(first:100)'
         '{totalCount pageInfo{hasNextPage} nodes{number state stateReason '
         'closedByPullRequestsReferences(first:100){totalCount pageInfo{hasNextPage} '
         'nodes{number state baseRefName mergedAt}}}}}}}' % (owner, name, num))
    blockers = connection(gh_graphql(runner, q), "repository", "issue", "blockedBy",
                          what="blockedBy of #%d" % num)
    reasons = []
    for b in blockers:
        bnum = b.get("number")
        if not isinstance(bnum, int):
            raise EligibilityError("a blocker of #%d has no issue number" % num)
        if blocker_state(b.get("state")) == "open":
            reasons.append("blocked-by-open-%d: #%d is still open" % (bnum, bnum))
            continue
        if b.get("stateReason") != "COMPLETED":
            reasons.append("blocker-not-completed-%d: #%d was closed as %s - not finished work"
                           % (bnum, bnum, b.get("stateReason")))
            continue
        closing = connection(b, "closedByPullRequestsReferences",
                             what="closing PRs of blocker #%d" % bnum)
        merged_elsewhere, merged_no_sha, not_on_base = [], None, None
        satisfied = False
        for pr in closing:
            pnum = pr.get("number")
            if not isinstance(pnum, int):
                raise EligibilityError("a closing PR of blocker #%d has no number" % bnum)
            if pnum not in cache:
                try:
                    view = json.loads(runner(["gh", "api", "repos/%s/pulls/%d" % (repo, pnum)]))
                except (CommandError, ValueError):
                    raise EligibilityError("reading PR #%d (a closing PR of blocker #%d) "
                                           "failed" % (pnum, bnum))
                cache[pnum] = {"state": view.get("state"),
                               "merged_at": view.get("merged_at"),
                               "merge_sha": view.get("merge_commit_sha"),
                               "base": (view.get("base") or {}).get("ref")}
            v = cache[pnum]
            if v["state"] != "closed" or not v["merged_at"]:
                continue  # this PR did not merge anything; the next one may
            if v["base"] != base:
                merged_elsewhere.append((pnum, v["base"]))
                continue
            if not v["merge_sha"]:
                merged_no_sha = pnum
                continue
            if merge_commit_on_base(runner, v["merge_sha"], base):
                satisfied = True
                break
            not_on_base = pnum
        if satisfied:
            continue
        if not_on_base:
            why = "PR #%d merged it into `%s`, but its merge commit is not on origin/%s" \
                  % (not_on_base, base, base)
        elif merged_elsewhere:
            why = "PR #%d merged it into `%s` instead of `%s`" \
                  % (merged_elsewhere[0][0], merged_elsewhere[0][1], base)
        elif merged_no_sha:
            why = "PR #%d merged it but carries no merge commit" % merged_no_sha
        else:
            why = "no merged PR of it was found"
        reasons.append("blocker-closed-without-implementation-%d: #%d is closed but %s"
                       % (bnum, bnum, why))
    return reasons


def pr_verdicts(num, prs, branches, ignore_stale):
    """Rule 6: no open PR and no unexplained origin branch may represent it."""
    reasons = []
    for pr in prs:
        if num in pr["closes"]:
            reasons.append("duplicate-pr-%d: open PR #%d closes #%d" % (pr["number"], pr["number"], num))
        elif num in {int(n) for n in CLOSES_RE.findall(pr["body"] or "")}:
            reasons.append("duplicate-pr-%d: open PR #%d closes #%d in its body text"
                           % (pr["number"], pr["number"], num))
        elif BRANCH_ISSUE_RE.search(pr["head"] or "") and \
                BRANCH_ISSUE_RE.search(pr["head"]).group(1) == str(num):
            reasons.append("duplicate-pr-%d: open PR #%d has head branch `%s` naming #%d"
                           % (pr["number"], pr["number"], pr["head"], num))
    if reasons:
        return reasons
    for br in branches:
        m = BRANCH_ISSUE_RE.search(br)
        if m and m.group(1) == str(num) and not any(p["head"] == br for p in prs):
            if ignore_stale:
                break
            reasons.append("stale-branch-ownership: origin branch `%s` names #%d without an "
                           "open PR; no session is known to own it (--ignore-stale-branches "
                           "declares otherwise)" % (br, num))
            break
    return reasons


def evaluate(runner, epic=DEFAULT_EPIC, approvers=(DEFAULT_APPROVERS,), repo=None,
             ignore_provenance=False, ignore_stale=False, scope=SCOPE_EPIC):
    """Screen one scope and return the result dict; raise EligibilityError to fail closed."""

    # Fail closed before reading anything: an unauthenticated gh must not be
    # mistaken for "no candidates".
    try:
        runner(["gh", "api", "user"])
    except CommandError as e:
        raise EligibilityError("gh is not usable (gh api user failed): %s" % e)

    if repo is None:
        repo = resolve_repo(runner)
    approvers = [a.strip() for a in approvers if a and a.strip()]
    if not approvers and not ignore_provenance:
        raise EligibilityError("the approver allowlist is empty - no approval can be "
                               "honoured, so nothing is eligible (fail closed)")

    owner, name = repo.split("/")
    fetch_base(runner, BASE_BRANCH)
    branches = origin_branches(runner)
    prs = open_pulls(runner, repo)
    claimed = claim_scan(runner, repo)

    cache = {}
    verdicts = []

    def screen(order, num, title, labels, not_open=None):
        """Rules 2 to 6 on one candidate; not_open names why it is not open."""
        if not_open:
            return {"number": num, "title": title, "order": order, "eligible": False,
                    "reasons": [not_open]}
        reasons = []
        reasons += approval_verdict(runner, repo, num, labels, approvers, ignore_provenance)
        if PAUSED_LABEL in labels:
            reasons.append("paused: the issue carries `%s`" % PAUSED_LABEL)
        reasons += blocker_verdicts(runner, repo, num, BASE_BRANCH, cache)
        if num in claimed:
            reasons.append("wip-claimed: %s" % claimed[num])
        reasons += pr_verdicts(num, prs, branches, ignore_stale)
        return {"number": num, "title": title, "order": order,
                "eligible": not reasons, "reasons": reasons}

    if scope == SCOPE_ALL_APPROVED:
        epic_num, epic_title = None, None
        for order, c in enumerate(approved_candidates(runner, repo)):
            if EPIC_LABEL in c["labels"]:
                verdicts.append({"number": c["number"], "title": c["title"], "order": order,
                                 "eligible": False,
                                 "reasons": ["epic-container: an Epic is scheduled through its "
                                            "sub-issues, never spawned as a worker"]})
                continue
            verdicts.append(screen(order, c["number"], c["title"], c["labels"]))
    else:
        q = ('{repository(owner:"%s",name:"%s"){issue(number:%d){title state '
             'subIssues(first:100){totalCount pageInfo{hasNextPage} nodes{number title state '
             'stateReason labels(first:100){totalCount nodes{name}}}}}}}'
             % (owner, name, epic))
        epic_data = gh_graphql(runner, q)
        epic_issue = (epic_data.get("repository") or {}).get("issue")
        if not isinstance(epic_issue, dict):
            raise EligibilityError("epic #%s was not found in %s" % (epic, repo))
        if epic_issue.get("state") != "OPEN":
            raise EligibilityError("epic #%s is %s, not OPEN - its sub-issues are not screened"
                                   % (epic, epic_issue.get("state")))
        sub_nodes = connection(epic_data, "repository", "issue", "subIssues",
                               what="subIssues of epic #%s" % epic)
        epic_num, epic_title = int(epic), epic_issue.get("title") or ""
        for order, s in enumerate(sub_nodes):
            num = s.get("number")
            if not isinstance(num, int):
                raise EligibilityError("the epic's sub-issue listing contains a node without a number")
            labels = [lab.get("name") for lab in connection(s, "labels", what="labels of #%s" % num)
                      if isinstance(lab.get("name"), str)]
            not_open = (None if s.get("state") == "OPEN"
                        else "not-open: the sub-issue is %s" % s.get("state"))
            verdicts.append(screen(order, num, s.get("title") or "", labels, not_open))

    eligible = [v["number"] for v in
                sorted((v for v in verdicts if v["eligible"]), key=lambda v: (v["order"], v["number"]))]
    flags = ["ignore-approval-provenance-for-testing"] if ignore_provenance else []
    if ignore_stale:
        flags.append("ignore-stale-branches")
    return {"schema": SCHEMA, "status": "ok", "error": None, "repo": repo, "baseRef": BASE_BRANCH,
            "scope": scope, "epicNumber": epic_num, "epicTitle": epic_title,
            "approvers": sorted(a.lower() for a in approvers), "flags": flags,
            "issues": verdicts, "eligible": eligible}


# ---------- rendering ----------

def render_json(res):
    return json.dumps(res, indent=2, sort_keys=True)


def render_human(res):
    lines = []
    if "ignore-approval-provenance-for-testing" in res["flags"]:
        lines += ["*** TESTING MODE: approval label and provenance (Rule 2) are NOT enforced "
                  "- this verdict is evidence about dependencies only ***", ""]
    if res.get("epicNumber") is not None:
        lines.append("repo %s   epic #%s %s   base %s   approvers %s"
                     % (res["repo"], res["epicNumber"], res["epicTitle"], res["baseRef"],
                        ",".join(res["approvers"]) or "-none-"))
    else:
        lines.append("repo %s   scope %s   base %s   approvers %s"
                     % (res["repo"], res.get("scope"), res["baseRef"],
                        ",".join(res["approvers"]) or "-none-"))
    if "ignore-stale-branches" in res["flags"]:
        lines.append("note: stale origin branches are ignored for this run (--ignore-stale-branches)")
    lines += ["", "   #  eligible  verdict", "  ---  --------  " + "-" * 56]
    for v in sorted(res["issues"], key=lambda v: (v["order"], v["number"])):
        mark = "  YES" if v["eligible"] else "   no"
        lines.append("%3d  %-8s  %s" % (v["number"], mark, "; ".join(v["reasons"]) or "eligible"))
    lines.append("")
    if res["eligible"]:
        lines.append("eligible (spawn order): " + " ".join("#%d" % n for n in res["eligible"]))
    else:
        lines.append("eligible: none")
    return "\n".join(lines)


def render_human_error(err):
    return "ERROR - fail closed, spawn nothing\n%s" % err


def resolve_approvers(cli_humans):
    """--humans wins; else AGENT_EPIC_APPROVERS; else the default. Never guessed."""
    if cli_humans is not None:
        return [a.strip() for a in cli_humans.split(",") if a.strip()]
    env = os.environ.get(APPROVERS_ENV)
    if env is not None:
        return [a.strip() for a in env.split(",") if a.strip()]
    return [a.strip() for a in DEFAULT_APPROVERS.split(",") if a.strip()]


def main(argv=None, runner=None):
    ap = argparse.ArgumentParser(
        prog="next_eligible.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__.split("Usage:")[0].strip(),
        epilog="Usage:\n  python3 scripts/next_eligible.py [--scope S] [--epic N] [--json]"
               " [--dry-run] [--humans a,b] [--ignore-stale-branches]"
               " [--ignore-approval-provenance-for-testing]\n"
               "Rules and reason codes: see the text above. --dry-run is the only mode this"
               " tool has; it is accepted to state the read-only intent explicitly.")
    ap.add_argument("--scope", choices=(SCOPE_EPIC, SCOPE_ALL_APPROVED), default=SCOPE_EPIC,
                    help="epic: screen the sub-issues of --epic (default); all-approved: screen"
                         " every open issue of the repository carrying `agent: approved`")
    ap.add_argument("--epic", type=int, default=DEFAULT_EPIC,
                    help="epic issue to screen (default: %(default)s; scope epic only)")
    ap.add_argument("--json", action="store_true", help="print the machine-readable result")
    ap.add_argument("--dry-run", action="store_true",
                    help="the only mode: read-only evaluation (no writes beyond the base-ref fetch)")
    ap.add_argument("--humans", default=None,
                    help="comma list replacing the approver allowlist (env %s, default %s)"
                         % (APPROVERS_ENV, DEFAULT_APPROVERS))
    ap.add_argument("--ignore-stale-branches", action="store_true",
                    help="do not reject candidates over an origin branch naming them without an open PR")
    ap.add_argument("--ignore-approval-provenance-for-testing", action="store_true",
                    help="TESTING ONLY (default OFF): skip Rule 2, the approval label and its "
                         "provenance, so the dependency screen can be evaluated alone")
    args = ap.parse_args(argv)

    if runner is None:
        runner = subprocess_runner
    try:
        res = evaluate(runner, epic=args.epic, approvers=resolve_approvers(args.humans),
                       ignore_provenance=args.ignore_approval_provenance_for_testing,
                       ignore_stale=args.ignore_stale_branches, scope=args.scope)
    except (EligibilityError, CommandError) as e:
        if args.json:
            print(render_json({"schema": SCHEMA, "status": "error", "error": str(e)}))
        else:
            print(render_human_error(str(e)))
        return 2
    print(render_json(res) if args.json else render_human(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
