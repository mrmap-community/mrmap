"""Offline regression checks for the board writes in scripts/wip.

Run from the repository root: python3 scripts/test_wip_board_sync.py
Exit code 0 means every check passed.

The board is a generated view of the claim comments, so the checks that matter are
"which writes does one claim change cause": claim, wait and done must move the
board without a separate `wip board`, must not create it, must not rewrite it when
nothing changed, and must not fail the claim when the board is unreachable. Every
GitHub-touching function is stubbed here, so this needs no `gh`, no token and no
network, and cannot touch a real repository.
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

calls = []


def stub_network(monkey_find=None):
    """Replace everything that would talk to GitHub with call-recording stubs."""
    calls.clear()
    m.repo = lambda: "o/r"
    m.git_root = lambda: "/wt"
    m.cur_branch = lambda: "housekeeping/issue-930-board-refresh"
    m.labeled_issues = lambda R: {}
    m.release_claims_on_closed = lambda R: 0
    m.claims_index = lambda R, numbers: {}
    m.ensure_label = lambda R: None

    def fake_sh(cmd, input=None, check=True):
        calls.append((" ".join(cmd[1:]), input))
        return "https://github.com/o/r/issues/1"

    def fake_try_sh(cmd, input=None):
        calls.append((" ".join(cmd[1:]), input))
        return True

    m.sh = fake_sh
    m.try_sh = fake_try_sh
    m.gh_json = lambda *a: []
    if monkey_find:
        m.find_board = monkey_find


def run(fn, *a):
    """Run fn, returning (exit_ok, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            fn(*a)
            code = 0
        except SystemExit as e:
            code = e.code or 0
    return code, out.getvalue(), err.getvalue()


def own_claim():
    """One raw claim comment from this client, as the API would return it."""
    p = {"v": 1, "client": m.client_id("/wt"), "issue": 930, "branch": "b", "worktree": "/wt",
         "state": "wip", "since": m.now_iso(), "heartbeat": m.now_iso(), "released": None}
    return [{"id": 7, "body": m.claim_body(p)}]


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
    return ok


results = []

# 1. board creation stays an explicit `wip board`, and it still works.
stub_network(monkey_find=lambda R: (None, None))
code, out, _ = run(m.cmd_board, None)
writes = [c for c in calls if c[0].startswith("issue create")]
results.append(check("wip board creates the board issue when none exists",
                     bool(writes) and m.BOARD_TITLE in writes[0][0] and m.BOARD_MARK in (writes[0][1] or ""),
                     f"writes={writes}"))

# 2. claim/wait/done never create a board; with no board they just leave it be.
for name, fn, arg in (("claim", m.cmd_claim, "930"), ("wait", m.cmd_wait, "need input"), ("done", m.cmd_done, "930")):
    stub_network(monkey_find=lambda R: (None, None))
    m.fetch_comments = lambda R, n: []
    if name == "done":
        m.fetch_comments = lambda R, n: own_claim()
    code, out, err = run(fn, arg)
    results.append(check(f"{name} writes no board issue when none exists",
                         code == 0 and not [c for c in calls if "issue create" in c[0]],
                         f"code={code} writes={calls} err={err}"))

# 3. a board write that dies mid-sync (die() -> SystemExit) warns and keeps exit 0.


def find_explodes(R):
    m.die("no route to github.com")


stub_network(monkey_find=find_explodes)
m.fetch_comments = lambda R, n: []
code, out, err = run(m.cmd_claim, "930")
results.append(check("a board refresh that dies leaves the claim succeeding",
                     code == 0 and "board" in err and "warning" in err,
                     f"code={code} err={err}"))

# 4. the change detector ignores only the refresh stamp.
body = m.board_body("o/r", [(930, "t", {"client": "c", "branch": "b", "worktree": "/wt",
                                        "state": "wip", "since": m.now_iso(), "heartbeat": m.now_iso()})], [])
moved_stamp = "\n".join(line.replace(m.now_iso(), "2000-01-01T00:00:00Z") if line.startswith("_Refreshed ") else line
                        for line in body.splitlines())
changed_row = body.replace("`c`", "`other`")
results.append(check("an identical board is detected across its refresh stamp",
                     m.board_table(body) == m.board_table(moved_stamp)))
results.append(check("a real row change is detected",
                     m.board_table(body) != m.board_table(changed_row)))

# 5. claim, wait and done each write the board exactly once when it did change.


def find_present(R):
    return 917, "<!-- agent-board v1 -->\n\n_Refreshed 2000-01-01T00:00:00Z x_\n"


for name, fn, arg in (("claim", m.cmd_claim, "930"), ("wait", m.cmd_wait, "need input")):
    stub_network(monkey_find=find_present)
    m.fetch_comments = lambda R, n: []
    code, out, err = run(fn, arg)
    writes = [c for c in calls if c[0].startswith("issue edit 917")]
    results.append(check(f"{name} refreshes the board once",
                         code == 0 and len(writes) == 1 and m.BOARD_MARK in (writes[0][1] or ""),
                         f"code={code} writes={writes} err={err}"))

stub_network(monkey_find=find_present)
m.fetch_comments = lambda R, n: own_claim()
code, out, err = run(m.cmd_done, "930")
writes = [c for c in calls if c[0].startswith("issue edit 917")]
results.append(check("done refreshes the board once",
                     code == 0 and len(writes) == 1, f"code={code} writes={writes} err={err}"))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
