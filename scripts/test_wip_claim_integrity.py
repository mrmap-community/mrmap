"""Offline regression checks for the claim integrity guards in scripts/wip.

Run from the repository root: python3 scripts/test_wip_claim_integrity.py
Exit code 0 means every check passed.

The #1196 shape: AO named a worktree `ao/implement-github-issue-6/root` from
the spawn prompt, `infer_issue` found the 6 in that slug, and claims plus a
board row landed on issue #6 - closed in 2021, unrelated to the epic actually
staffed. Each check pins one guard from that fix: what a branch may name, how
an explicit number and a branch guess resolve against each other, and that a
CLOSED issue is refused while it is being claimed, not after the next board
sweep. Everything that would talk to git or GitHub is stubbed, so this needs
no `gh`, no token and no network, and cannot touch a real repository.
"""
import importlib.machinery
import importlib.util
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout

spec = importlib.util.spec_from_loader(
    "wip", importlib.machinery.SourceFileLoader(
        "wip", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wip")))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

calls = []   # ("gh ... args", input) of every sh/try_sh write
reads = []   # gh_json calls, kept apart so write checks stay write checks


def stub(branch="master", state=None):
    """Replace git and GitHub with call-recording stubs.

    `state` is what `gh issue view` reports for any issue ('OPEN', 'CLOSED');
    None means the state cannot be told, which must not block legitimate work.
    """
    calls.clear()
    reads.clear()
    m.repo = lambda: "o/r"
    m.git_root = lambda: "/wt"
    m.cur_branch = lambda: branch
    m.ensure_label = lambda R: None
    m.labeled_issues = lambda R: {}
    m.release_claims_on_closed = lambda R: 0
    m.claims_index = lambda R, numbers: {}
    m.find_board = lambda R: (None, None)
    m.fetch_comments = lambda R, n: []

    def fake_sh(cmd, input=None, check=True):
        calls.append((" ".join(cmd[1:]), input))
        return "https://github.com/o/r/issues/1"

    def fake_try_sh(cmd, input=None):
        calls.append((" ".join(cmd[1:]), input))
        return True

    def fake_gh_json(*a):
        reads.append(a)
        if a[:2] == ("issue", "view"):
            return {"state": state}
        return []

    m.sh = fake_sh
    m.try_sh = fake_try_sh
    m.gh_json = fake_gh_json


def run(fn, *a):
    """Run fn, returning (exit_ok, result, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    result = None
    with redirect_stdout(out), redirect_stderr(err):
        try:
            result = fn(*a)
            code = 0
        except SystemExit as e:
            code = e.code or 0
    return code, result, out.getvalue(), err.getvalue()


def own_claim(issue=948):
    """One raw claim comment from this client, as the API would return it."""
    p = {"v": 1, "client": m.client_id("/wt"), "issue": issue, "branch": "b", "worktree": "/wt",
         "state": "wip", "since": m.now_iso(), "heartbeat": m.now_iso(), "released": None}
    return [{"id": 7, "body": m.claim_body(p)}]


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
    return ok


results = []

# 1. What a branch may name: only a convention-shaped segment, never a digit
#    run inside a slug (the #1196 prompt echo).
PARSE_CASES = [
    ("housekeeping/issue-930-board-refresh", 930),
    ("feature/issue6", 6),
    ("feature/issue_42-x", 42),
    ("fix/#42-thing", 42),
    ("issue-7", 7),
    ("ao/issue-1177-child-of-an-epic", 1177),
    ("ao/implement-github-issue-6/root", None),
    ("ao/implement-github-issue-6", None),
    ("ao/repo-task-harden/wip-claim-integrity", None),
    ("bugfix/notissue-9-x", None),
    ("ao/mrmap-83", None),
    ("master", None),
    (None, None),
]
for branch, want in PARSE_CASES:
    results.append(check(f"branch {branch!r} names {'#' + str(want) if want else 'no issue'}",
                         m.branch_issue(branch) == want,
                         f"got={m.branch_issue(branch)}"))

# 2. The #1196 branch infers nothing and says so, instead of claiming #6.
stub(branch="ao/implement-github-issue-6/root")
code, _, out, err = run(m.infer_issue, None, "claim")
results.append(check("a prompt-echo branch infers no issue and names the branch",
                     code == 1 and "cannot infer" in err and "implement-github-issue-6" in err,
                     f"code={code} err={err}"))

# 3. An explicit number is trusted over a prompt-echo branch: the controller
#    passes the real issue while the worktree slug still carries a stray digit.
stub(branch="ao/implement-github-issue-6/root")
code, n, _, err = run(m.infer_issue, "948", "claim")
results.append(check("an explicit number is trusted over a prompt-echo branch",
                     code == 0 and n == 948 and not err,
                     f"code={code} n={n} err={err}"))

# 4. An explicit number conflicting with a convention-shaped branch is refused
#    outright - wrong argument or wrong worktree, and the error names both.
stub(branch="housekeeping/issue-6-wrong-room")
code, n, _, err = run(m.infer_issue, "948", "claim")
results.append(check("explicit-vs-parsed conflict returns no number and names both sources",
                     code == 0 and n is None
                     and "#948" in err and "#6" in err and "issue-6-wrong-room" in err,
                     f"code={code} n={n} err={err}"))
code, _, _, err = run(m.resolve_issue, "948", "claim")
results.append(check("a command run dies on the conflict instead of claiming one of them",
                     code == 1 and "ambiguous" in err,
                     f"code={code} err={err}"))

# 5. Agreement still stands.
stub(branch="housekeeping/issue-948-harden-claims")
code, n, _, err = run(m.infer_issue, "948", "claim")
results.append(check("explicit and branch naming the same issue is no conflict",
                     code == 0 and n == 948 and not err, f"code={code} n={n} err={err}"))

# 6. A CLOSED issue is refused at claim time - no comment, no label, no board
#    row, whatever the branch or --force would otherwise have allowed.
stub(branch="ao/implement-github-issue-6/root", state="CLOSED")
code, _, _, err = run(m.cmd_claim, "6")
results.append(check("claiming a closed issue is refused before anything is written",
                     code == 1 and "closed" in err
                     and not [c for c in calls if c[0].startswith("api repos/o/r/issues/6/comments")]
                     and not [c for c in calls if c[0].startswith("issue edit 6")],
                     f"code={code} calls={calls} err={err}"))

# 7. The refusal also stands for a heartbeat on a claim that survived the issue
#    being closed; the error points at `wip done`.
stub(branch="housekeeping/issue-948-harden-claims", state="CLOSED")
m.fetch_comments = lambda R, n: own_claim(948)
code, _, _, err = run(m.cmd_claim, "948")
results.append(check("re-claiming a closed issue is refused and points at wip done",
                     code == 1 and "closed" in err and "wip done 948" in err
                     and not [c for c in calls if c[0].startswith("api -X PATCH")],
                     f"code={code} calls={calls} err={err}"))

# 8. `wait` only refuses where it would create a claim.
stub(branch="housekeeping/issue-948-harden-claims", state="CLOSED")
code, _, _, err = run(m.cmd_wait, "need input", False, "948")
results.append(check("a wait that would claim a closed issue is refused",
                     code == 1 and "closed" in err
                     and not [c for c in calls if c[0].startswith("api repos/o/r/issues/948/comments")],
                     f"code={code} calls={calls} err={err}"))
stub(branch="housekeeping/issue-948-harden-claims", state="CLOSED")
m.fetch_comments = lambda R, n: own_claim(948)
code, _, _, err = run(m.cmd_wait, "need input", False, "948")
results.append(check("marking an existing claim waiting is not blocked by the guard",
                     code == 0 and bool([c for c in calls if c[0].startswith("api -X PATCH")]),
                     f"code={code} calls={calls} err={err}"))

# 9. `done` on a closed issue keeps working: releasing is never finished work's enemy.
stub(branch="housekeeping/issue-948-harden-claims", state="CLOSED")
m.fetch_comments = lambda R, n: own_claim(948)
code, _, out, err = run(m.cmd_done, "948")
results.append(check("releasing a claim on a closed issue still works",
                     code == 0 and "released #948" in out
                     and bool([c for c in calls if c[0].startswith("api -X PATCH")]),
                     f"code={code} out={out} calls={calls} err={err}"))

# 10. An OPEN issue claims through as before, and a state that cannot be told
#     (a stubbed or partial gh answer) must not block legitimate work.
for state in ("OPEN", None):
    stub(branch="ao/implement-github-issue-6/root", state=state)
    code, _, _, err = run(m.cmd_claim, "948")
    posts = [c for c in calls if c[0].startswith("api repos/o/r/issues/948/comments")]
    labels = [c for c in calls if c[0].startswith("issue edit 948") and m.LABEL in c[0]]
    results.append(check(f"claim on an issue with state {state or 'unknown'} still writes claim and label",
                         code == 0 and len(posts) == 1 and len(labels) == 1,
                         f"code={code} calls={calls} err={err}"))

# 11. `ls` uses the same parse: a prompt-echo worktree is "(no issue in branch)",
#     not a phantom association with a closed #6.
stub()
m.worktrees = lambda: [{"path": "/wt", "branch": "ao/implement-github-issue-6/root"}]
scanned = []
m.claims_index = lambda R, numbers: scanned.extend(numbers) or {}
code, _, out, err = run(m.cmd_ls, None)
results.append(check("ls does not associate a prompt-echo branch with a phantom issue",
                     code == 0 and 6 not in scanned and "(no issue in branch)" in out,
                     f"code={code} out={out} scanned={scanned} err={err}"))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
