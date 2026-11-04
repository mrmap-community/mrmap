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


# 6. ask / answers: the question handoff markers, on top of the wait flow.
def qcomment(client, qid, question, created, answered=False, dbid=42):
    """One raw question comment from `client`, as the API would return it."""
    body = m.question_body(client, qid, question)
    if answered:
        body = m.answered_body(body, "2026-01-05T00:00:00Z")
    return {"id": dbid, "created_at": created, "body": body}


def rcomment(created, text, who="dev"):
    """A plain human reply, the only comment that is not machine-managed."""
    return {"id": 99, "created_at": created, "body": text, "user": {"login": who}}


def quoted_reply(created, client, qid, question, text="OK;", who="jokiefer", dbid=99):
    """A GitHub quote-reply, the #825 shape: the question quoted in '>' lines, answer below."""
    quoted = "\n".join("> " + l for l in m.question_body(client, qid, question).splitlines())
    return {"id": dbid, "created_at": created, "body": f"{quoted}\n{text}\n", "user": {"login": who}}


def claimcomment(created, client, dbid=61):
    """A raw claim comment from `client`, newer than a question would be."""
    p = {"v": 1, "client": client, "issue": 930, "branch": "b", "worktree": "/wt",
         "state": "wip", "since": created, "heartbeat": created, "released": None}
    return {"id": dbid, "created_at": created, "body": m.claim_body(p)}


CID = m.client_id("/wt")

# ask posts the full question as one comment and then runs the wait flow.
stub_network(monkey_find=lambda R: (None, None))
m.fetch_comments = lambda R, n: own_claim()  # claim stands, no question yet
code, out, err = run(m.cmd_ask, "should we prefer B over C, and why - be thorough about the tradeoffs and the migration cost")
qwrite = [c for c in calls if c[0].startswith("api repos/o/r/issues/930/comments") and "agent-question" in c[0]]
wpatch = [c for c in calls if c[0].startswith("api -X PATCH") and '"state":"waiting"' in c[0]]
results.append(check("ask posts one structured question comment and marks the claim waiting",
                     code == 0 and len(qwrite) == 1
                     and f"agent-question client={CID} id=" in qwrite[0][0]
                     and "should we prefer B" in qwrite[0][0]
                     and len(wpatch) == 1 and not [c for c in calls if "issue create" in c[0]],
                     f"code={code} writes={calls} err={err}"))

# ask is idempotent while the client's question is still open: it updates it.
stub_network(monkey_find=lambda R: (None, None))
m.fetch_comments = lambda R, n: [qcomment(CID, "abcd1234", "old question", "2026-01-01T00:00:00Z")] + own_claim()
code, out, err = run(m.cmd_ask, "a revised question with different wording on the same open thread")
qcreate = [c for c in calls if c[0].startswith("api repos/o/r/issues/930/comments") and "agent-question" in c[0]]
qpatch = [c for c in calls if c[0].startswith("api -X PATCH") and "agent-question" in c[0] and "id=abcd1234" in c[0]]
results.append(check("ask refreshes the open question instead of posting a second one",
                     code == 0 and not qcreate and len(qpatch) == 1,
                     f"code={code} writes={calls} err={err}"))

# answers surfaces a human reply once and stamps the question answered.
stub_network()
m.fetch_comments = lambda R, n: [qcomment(CID, "abcd1234", "should we prefer B over C?", "2026-01-01T00:00:00Z"),
                                 rcomment("2026-01-02T00:00:00Z", "use B, and keep the migration small")]
code, out, err = run(m.cmd_answers, "930")
marked = [c for c in calls if c[0].startswith("api -X PATCH") and m.ANSWERED_MARK in c[0]]
results.append(check("answers prints the human reply and marks the question answered",
                     code == 0 and "use B" in out and "abcd1234" in out and len(marked) == 1,
                     f"code={code} out={out} writes={calls} err={err}"))

# an answered question never surfaces again.
stub_network()
m.fetch_comments = lambda R, n: [qcomment(CID, "abcd1234", "should we prefer B over C?", "2026-01-01T00:00:00Z", answered=True),
                                 rcomment("2026-01-02T00:00:00Z", "use B, and keep the migration small")]
code, out, err = run(m.cmd_answers, "930")
results.append(check("an answered question is not surfaced a second time",
                     code == 0 and "no open questions" in out and "use B" not in out
                     and not [c for c in calls if "PATCH" in c[0]],
                     f"code={code} out={out} writes={calls} err={err}"))

# a follow-up question does not resurface the previous answer.
stub_network()
m.fetch_comments = lambda R, n: [
    qcomment(CID, "aaa11111", "first question", "2026-01-01T00:00:00Z", answered=True),
    rcomment("2026-01-02T00:00:00Z", "the human answer"),
    qcomment(CID, "bbb22222", "a follow-up question", "2026-01-03T00:00:00Z", dbid=44)]
code, out, err = run(m.cmd_answers, "930")
results.append(check("a follow-up question does not resurface the earlier answer",
                     code == 0 and "the human answer" not in out and "bbb22222" in out and "still waiting" in out,
                     f"code={code} out={out} writes={calls} err={err}"))

# the real #825 case: the human answers with "Reply in conversation", so the reply
# body carries the question's marker text inside '>' lines.
Q825 = "Confirm the #826 application-mapping scope? Reply here with corrections or an OK."
qr = quoted_reply("2026-11-03T18:56:57Z", CID, "d70b4cdf", Q825, dbid=6612781098)
results.append(check("a quote-reply repeating the marker is not machine-managed",
                     not m.is_machine_comment(qr)
                     and not m.is_machine_comment({"body": "> <!-- agent-claim {} -->\n+1"})
                     and not m.is_machine_comment({"body": "> agent-board v1\ndone"})
                     and m.is_machine_comment(qcomment(CID, "d70b4cdf", Q825, "2026-11-03T17:57:31Z"))))

stub_network()
q825 = qcomment(CID, "d70b4cdf", Q825, "2026-11-03T17:57:31Z", dbid=6611525807)
m.fetch_comments = lambda R, n: [q825, qr]
code, out, err = run(m.cmd_answers, "930")
marked = [c for c in calls if c[0].startswith("api -X PATCH") and m.ANSWERED_MARK in c[0]]
results.append(check("answers surfaces the quote-reply and stamps the original question once",
                     code == 0 and "OK;" in out and out.count("- question d70b4cdf") == 1
                     and "1 answer" in out
                     and len(marked) == 1 and "comments/6611525807" in marked[0][0]
                     and "comments/6612781098" not in marked[0][0],
                     f"code={code} out={out} writes={calls} err={err}"))

# a duplicated open question comment still surfaces exactly once, oldest first.
stub_network()
m.fetch_comments = lambda R, n: [
    qcomment(CID, "eee55555", "one question posted twice", "2026-01-01T00:00:00Z", dbid=51),
    qcomment(CID, "eee55555", "one question posted twice", "2026-01-01T00:05:00Z", dbid=52)]
code, out, err = run(m.cmd_answers, "930")
results.append(check("an open question is printed at most once",
                     code == 0 and out.count("- question eee55555") == 1 and "still waiting" in out,
                     f"code={code} out={out} writes={calls} err={err}"))

# machine comments newer than the question are still no answer.
stub_network()
m.fetch_comments = lambda R, n: [
    qcomment(CID, "fff66666", "a question nobody answered", "2026-01-01T00:00:00Z"),
    claimcomment("2026-01-02T00:00:00Z", "other:wt"),
    qcomment("other:wt", "ggg77777", "another client's question", "2026-01-03T00:00:00Z", dbid=63),
    {"id": 64, "created_at": "2026-01-04T00:00:00Z", "body": "<!-- agent-board v1 -->\nrows"}]
code, out, err = run(m.cmd_answers, "930")
results.append(check("a newer claim, question or board comment is still not an answer",
                     code == 0 and "still waiting" in out and "another client" not in out
                     and not [c for c in calls if "PATCH" in c[0]],
                     f"code={code} out={out} writes={calls} err={err}"))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
