"""Offline regression checks for the decision protocol in scripts/decisions.

Run from the repository root: python3 scripts/test_decisions.py
Exit code 0 means every check passed.

The protocol exists so that a design decision cannot be taken by an agent, by
silence, or by the wrong person, so these checks are written as attacks first
and features second. Every GitHub-touching function is stubbed here: no `gh`, no
token, no network, and no real issue can be touched. The fixtures are the real
shapes found on RFC #992 - an unmarked questionnaire with a copy/paste answer
template, and a maintainer answering `Q7: C` under it.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

spec = importlib.util.spec_from_loader(
    "decisions", importlib.machinery.SourceFileLoader(
        "decisions", os.path.join(os.path.dirname(os.path.abspath(__file__)), "decisions")))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

WRITES = []
ISSUE = {"body": "", "updated": "2026-11-01T00:00:00Z"}
REACTIONS = {}
COMMENTS = []
ONE_COMMENT = {}


def stub(comments=(), body="", reactions=None, comment_store=None):
    """Replace everything that would talk to GitHub with call-recording stubs."""
    WRITES.clear()
    ISSUE["body"] = body
    ISSUE["updated"] = "2026-11-01T00:00:00Z"
    d.repo = lambda: "o/r"
    d.git_root = lambda: "/wt"
    d.cur_branch = lambda: "housekeeping/issue-1069-decision-protocol"
    d.fetch_comments = lambda R, n: list(comments)
    d.reactions_for = lambda R, cid: list((reactions or {}).get(cid, []))
    d.issue_view = lambda R, n: (ISSUE["body"], ISSUE["updated"])

    def write_issue_body(R, n, new):
        WRITES.append(("body", new))
        ISSUE["body"] = new
        return "ok"

    def post_comment(R, n, body):
        WRITES.append(("comment", body))
        return "https://github.com/o/r/issues/%s#issuecomment-777" % n

    def fetch_comment(R, cid):
        return (comment_store or {}).get(str(cid))

    def fake_sh(cmd, input=None, check=True):
        WRITES.append(("sh", " ".join(cmd[1:])))
        return "https://github.com/o/r/issues/42#issuecomment-777"

    d.write_issue_body = write_issue_body
    d.post_comment = post_comment
    d.fetch_comment = fetch_comment
    d.sh = fake_sh
    d.gh_json = lambda *a: {"html_url": "https://github.com/o/r/issues/42#issuecomment-777"}


def run(fn, *a, **kw):
    """Run fn, returning (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            fn(*a, **kw)
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue(), err.getvalue()


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))
    return bool(ok)


results = []

ASKS = [
    {"q": "Q7", "d": ["D04"], "title": "Persistence", "blocking": True,     "options": {"A": "references only", "B": "snapshots only", "C": "hybrid references and "
                 "snapshots"}, "recommend": "C", "why": "portable and reconcilable",
     "owner": "", "gate": ""},
    {"q": "Q8", "d": ["D05"], "title": "Schema", "blocking": False,
     "options": {"A": "extend the model", "B": "audit then generalize", "C": "json only"},
     "recommend": "B", "why": "the migration is the risk", "owner": "", "gate": ""},
]

# the same identity the tool itself derives, so fixtures and code agree
CLIENT = d.client_id("/wt")


def ask_payload(asks=None, rx=False):
    asks = asks if asks is not None else [dict(a) for a in ASKS]
    return {"v": 1, "id": "dr-aaaa1111", "client": CLIENT, "issue": 42, "asks": asks,
            "rx": rx, "hash": d.body_hash(json.dumps(asks, sort_keys=True)), "version": 1,
            "status": "pending", "created": "2026-11-01T00:00:00Z", "register": "", "rfc": ""}


def request_comment(asks=None, ts="2026-11-01T00:00:00Z", dbid=10, rx=False, marked=True,
                    who="agentbot"):
    """An agent's request comment: marked machine text, or the unmarked #992 shape."""
    payload = ask_payload(asks, rx)
    body = d.render_request(payload)
    if not marked:
        # the #992 shape: the same questions and the same copy/paste template, but
        # written by a hand, with no marker to say who authored it
        body = body.split("-->", 1)[1].strip()
    return {"id": dbid, "created_at": ts, "updated_at": ts,
            "user": {"login": who, "type": "User"}, "author_association": "MEMBER",
            "html_url": f"https://github.com/o/r/issues/42#issuecomment-{dbid}", "body": body}


def human(ts, body, who="maintainer", assoc="MEMBER", dbid=20, utype="User", updated=None):
    return {"id": dbid, "created_at": ts, "updated_at": updated or ts,
            "user": {"login": who, "type": utype}, "author_association": assoc,
            "html_url": f"https://github.com/o/r/issues/42#issuecomment-{dbid}", "body": body}


def audit_comment(events, dbid=90, ts="2026-11-02T00:00:00Z"):
    payload = {"v": 1, "id": "au-seed", "client": "host:wt", "issue": 42, "events": events}
    return {"id": dbid, "created_at": ts, "updated_at": ts,
            "user": {"login": "agentbot", "type": "Bot"}, "author_association": "NONE",
            "html_url": f"https://github.com/o/r/issues/42#issuecomment-{dbid}",
            "body": d.audit_body(payload, events, [])}


REGISTER_BODY = """# RFC

## 8. Decision register (must be maintained in this issue)

| ID | Topic | Status | Decision / evidence | Reviewer |
|---|---|---|---|---|
| D01 | Dataset identity | **Accepted (#669)** | fileIdentifier | design |
| D04 | Persistence | **Open / blocking** | Hybrid proposed | Maintainers |
| D05 | Schema | **Open / blocking** | Await Q8 | Maintainers |

A decision is accepted only when a maintainer records it.

## 9. Next steps

Unrelated section that must survive untouched.
"""


def recorded_event(qid="Q7", state="Accepted", option="C", did=("D04",), ts="2026-11-01T06:00:00Z",
                   src_ref=None, actor="maintainer", kind="answer"):
    src_ref = src_ref or "c20:beefbeef00"
    return {"kind": kind, "src_kind": "comment", "q": qid, "d": list(did), "state": state,
            "ts": ts, "option": option, "text": "hybrid references and snapshots", "note": "",
            "actor": actor, "assoc": "MEMBER", "src": "https://github.com/o/r/issues/42"
            f"#issuecomment-{src_ref.split(':')[0].lstrip('c')}", "src_ts": ts,
            "src_ref": src_ref,
            "key": d.event_key(qid, src_ref, state, option)}


# ---------- 1. the request itself ----------

# a request states its questions, its recommendation and that it is not approval
body = d.render_request(ask_payload())
results.append(check("a request names its questions, its recommendation and its pending state",
                     "### Q7 — Persistence [BLOCKING] → D04" in body
                     and "- **C (recommended): hybrid references and snapshots**" in body
                     and "- A: references only" in body
                     and "Agent recommendation: C** — portable and reconcilable" in body
                     and "status: pending" in body, body))
results.append(check("a request says three times that answering is not approval",
                     body.count("not the `agent: approved` label") == 1
                     and "proposal, not approval" in body
                     and "not a pull request approval" in body))
results.append(check("a request carries the machine marker with its question ids",
                     d.REQUEST_RE.search(body.replace("\n", " ", 1)) is not None
                     and '"q":"Q7"' in body))

# a request over the question budget is refused: a wall of questions is the RFC problem
big = [dict(ASKS[0], q=f"Q{9 + i}", d=[]) for i in range(d.MAX_ASKS + 1)]
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump({"asks": big}, handle)
    big_path = handle.name
code, out, err = run(d.load_spec, big_path)
results.append(check(f"a request with more than {d.MAX_ASKS} questions is refused",
                     code == 1 and "at most" in err, f"code={code} err={err}"))

# a question with no recommendation cannot be asked: the agent must state its own view
no_rec = [dict(ASKS[0], recommend=None)]
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump({"asks": no_rec}, handle)
    no_rec_path = handle.name
code, out, err = run(d.load_spec, no_rec_path)
results.append(check("a question without an agent recommendation is refused",
                     code == 1 and "recommend" in err, f"code={code} err={err}"))

# reactions may only be offered for one question, or the spec is refused
stub([request_comment(asks=[dict(ASKS[0])], rx=True)])
code, out, err = run(d.cmd_request, "42", no_rec_path, False)   # also has no recommend
results.append(check("request reuses the spec validator", code == 1, f"code={code} err={err}"))
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump({"rx": True, "asks": [dict(a) for a in ASKS]}, handle)
    rx_multi_path = handle.name
code, out, err = run(d.cmd_request, "42", rx_multi_path, False)
results.append(check("reaction opt-in for several questions at once is refused",
                     code == 1 and "exactly one question" in err, f"code={code} err={err}"))

# posting a request is a dry run unless --write, and repeatable without stacking
stub([request_comment()])
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump({"asks": [dict(a) for a in ASKS]}, handle)
    spec_path = handle.name
code, out, err = run(d.cmd_request, "42", spec_path, False)
results.append(check("request writes nothing without --write",
                     code == 0 and not WRITES and "already open" in out,
                     f"code={code} writes={WRITES} out={out[:200]}"))
code, out, err = run(d.cmd_request, "42", spec_path, True)
results.append(check("the same request is refreshed, never stacked a second time",
                     code == 0 and len([w for w in WRITES if w[0] == "comment"]) == 0
                     and "refreshed" in out, f"code={code} writes={WRITES} out={out[:200]}"))
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
    json.dump({"asks": [dict(ASKS[0])]}, handle)
    one_path = handle.name
stub([request_comment()])          # the open request asks two questions, this one asks one
code, out, err = run(d.cmd_request, "42", one_path, True)
results.append(check("a different set of questions is posted as a new request",
                     code == 0 and len([w for w in WRITES if w[0] == "comment"]) == 1
                     and "asked Q7" in out, f"code={code} writes={WRITES} out={out[:150]}"))

# ---------- 2. reading answers ----------

def scan(comments, approvers=None, gates=(), maps=(), rx=True):
    stub(comments)
    return d.reconcile("o/r", 42, gates, approvers, rx, maps)


state = scan([request_comment(),
              human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B")])
got = {q: (s["state"], (s.get("accepted") or {}).get("option")) for q, s in state["ask_states"].items()}
results.append(check("a multi-line answer decides both questions",
                     got == {"Q7": ("Accepted", "C"), "Q8": ("Accepted", "B")}, f"got={got}"))
results.append(check("the decision of a question reaches its decision id",
                     state["decisions"]["D04"]["state"] == "Accepted"
                     and state["decisions"]["D05"]["state"] == "Accepted"))

state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C; Q8: B")])
results.append(check("two answers on one line separated by ';' are both read",
                     [state["ask_states"][q]["state"] for q in ("Q7", "Q8")]
                     == ["Accepted", "Accepted"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "**Q7:** C")])
results.append(check("bold around the question id still parses",
                     state["ask_states"]["Q7"]["state"] == "Accepted"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C and Q8: B")])
results.append(check("two answers run together in prose are clarified, not guessed apart",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"
                     and not state["new_events"],
                     f"state={state['ask_states']['Q7']}"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C; Q8: B\n")])
results.append(check("';' between two answers on one line is the documented form",
                     [state["ask_states"][q]["state"] for q in ("Q7", "Q8")]
                     == ["Accepted", "Accepted"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7 — C\nQ8 - B")])
results.append(check("'Q7 — C' and 'Q8 - B' are answers too",
                     state["ask_states"]["Q7"]["state"] == "Accepted"
                     and state["ask_states"]["Q8"]["state"] == "Accepted"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7/Q8: A")])
results.append(check("a grouped answer decides both questions",
                     [state["ask_states"][q]["accepted"]["option"] for q in ("Q7", "Q8")]
                     == ["A", "A"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: defer")])
results.append(check("'defer' defers instead of deciding",
                     state["ask_states"]["Q7"]["state"] == "Deferred"
                     and state["decisions"]["D04"]["state"] == "Deferred"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q8: discuss — needs the migration cost")])
results.append(check("'discuss' with a reason is a discussion, not a decision",
                     state["ask_states"]["Q8"]["state"] == "Discussed"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: yes")])
results.append(check("'yes' means the recommendation, and says so",
                     state["ask_states"]["Q7"]["state"] == "Accepted"
                     and state["ask_states"]["Q7"]["accepted"]["option"] == "C"
                     and "recommendation" in state["ask_states"]["Q7"]["accepted"]["note"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z",
                                       "Q7: Omit the links entirely in v1, we can add them later")])
results.append(check("an answer in prose is kept in the author's own words",
                     state["ask_states"]["Q7"]["state"] == "Accepted"
                     and state["ask_states"]["Q7"]["accepted"]["verbatim"]
                     and "Omit the links entirely" in state["ask_states"]["Q7"]["accepted"]["text"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C is right, though B is safer")])
results.append(check("an answer naming two options is clarified, never decided",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"
                     and not state["new_events"]
                     and any("not unambiguous" in r for r in state["refused"]),
                     f"state={state['ask_states']['Q7']} refused={state['refused']}"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: E")])
results.append(check("a letter that is not on offer decides nothing",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"
                     and not state["new_events"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7:")])
results.append(check("an empty answer asks for clarification instead of guessing",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q99: C")])
results.append(check("an answer to a question nobody asked decides nothing",
                     not state["new_events"] and any("no open request" in r for r in state["refused"]),
                     f"refused={state['refused']}"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "I think we should just ship it")])
results.append(check("free text without a question id is surfaced, never interpreted",
                     not state["new_events"] and len(state["unstructured"]) == 1))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "> Q7: C\n\nI agree with you")])
results.append(check("a quoted answer is not the maintainer's own answer",
                     state["ask_states"]["Q7"]["state"] == "Pending" and not state["new_events"]))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "    Q7: C\n\nnot this one")])
results.append(check("an indented quote of the template is not an answer either",
                     state["ask_states"]["Q7"]["state"] == "Pending" and not state["new_events"]))
state = scan([request_comment(), human("2026-11-05T06:00:00Z", "Q7: B\nQ7: C")])
results.append(check("two different answers to one question in one comment are clarified",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"
                     and not state["new_events"], f"state={state['ask_states']['Q7']}"))

# ---------- 3. who may decide ----------

for who, assoc, utype, label in (
        ("stranger", "NONE", "User", "a stranger"),
        ("newcomer", "FIRST_TIME_CONTRIBUTOR", "User", "a first-time contributor"),
        ("passing", "CONTRIBUTOR", "User", "a contributor without write access"),
        ("ci-bot", "MEMBER", "Bot", "a bot account")):
    state = scan([request_comment(),
                  human("2026-11-01T06:00:00Z", "Q7: C", who=who, assoc=assoc, utype=utype)])
    results.append(check(f"{label} cannot decide a question",
                         state["ask_states"]["Q7"]["state"] == "Pending"
                         and not state["new_events"]
                         and any("not counted" in r for r in state["refused"]),
                         f"state={state['ask_states']['Q7']} refused={state['refused']}"))

state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", who="write-buddy",
                                       assoc="COLLABORATOR")])
results.append(check("someone with write access to the repository may decide",
                     state["ask_states"]["Q7"]["state"] == "Accepted"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", who="member-outside")],
             approvers={"other"})
results.append(check("an allowlist narrows who decides, even a MEMBER",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and not state["new_events"], f"state={state['ask_states']['Q7']}"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", who="listed")],
             approvers={"listed"})
results.append(check("someone on the allowlist decides",
                     state["ask_states"]["Q7"]["state"] == "Accepted"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "As Q7 I would take C, ok?")])
results.append(check("a suggestion written by the agent's own hand is never an answer",
                     state["ask_states"]["Q7"]["state"] == "Pending"))

# a machine comment - claim, question, board, request, audit - never answers, whatever it says
machine_shapes = [
    {"id": 31, "created_at": "2026-11-01T07:00:00Z",
     "user": {"login": "agentbot", "type": "Bot"}, "author_association": "NONE",
     "html_url": "https://github.com/o/r/issues/42#issuecomment-31",
     "body": "<!-- agent-claim {\"v\":1} -->\n\nQ7: C"},
    {"id": 32, "created_at": "2026-11-01T07:00:00Z",
     "user": {"login": "agentbot", "type": "Bot"}, "author_association": "NONE",
     "html_url": "https://github.com/o/r/issues/42#issuecomment-32",
     "body": "<!-- decision-request {} -->\n\nQ8: B"},
    {"id": 33, "created_at": "2026-11-01T07:00:00Z",
     "user": {"login": "agentbot", "type": "Bot"}, "author_association": "NONE",
     "html_url": "https://github.com/o/r/issues/42#issuecomment-33",
     "body": "<!-- agent-board v1 -->\n\nQ7: C\nQ8: B"},
]
state = scan([request_comment()] + machine_shapes)
results.append(check("an agent comment never answers, whatever marker it carries",
                     [state["ask_states"][q]["state"] for q in ("Q7", "Q8")]
                     == ["Pending", "Pending"] and not state["new_events"]))

# the #992 case: an unmarked questionnaire whose own fenced template answers itself
legacy = request_comment(marked=False)
legacy["body"] += "\n### How to answer\n\n```text\nQ7: C\nQ8: B\n```\n"
state = scan([legacy])
results.append(check("the answer template inside a request is not an answer to it",
                     [state["ask_states"][q]["state"] for q in ("Q7", "Q8")]
                     == ["Pending", "Pending"] and not state["new_events"]
                     and any("without a" in w for w in state["warnings"]),
                     f"states={ {q: s['state'] for q, s in state['ask_states'].items()} }"))
state = scan([legacy, human("2026-11-02T06:00:00Z", "Q7: C\nQ8: B", who="maintainer")])
results.append(check("an unmarked request is still answered by a maintainer's own comment",
                     [state["ask_states"][q]["state"] for q in ("Q7", "Q8")]
                     == ["Accepted", "Accepted"] and len(state["new_events"]) == 2))
state = scan([request_comment(), human("2025-10-01T06:00:00Z", "Q7: C")])
results.append(check("an answer older than the question is not an answer to it",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and any("before the request" in r for r in state["refused"]),
                     f"refused={state['refused']}"))

# ---------- 4. reactions ----------

SINGLE = [dict(ASKS[0])]


def rx_scan(reactions, approvers=None, asks=None, rx=True):
    comment = request_comment(asks=asks if asks is not None else [dict(a) for a in SINGLE], rx=rx)
    stub([comment], reactions={comment["id"]: reactions})
    return d.reconcile("o/r", 42, (), approvers, True, ())


state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"})
results.append(check("an allowlisted 👍 on a single binary request approves the recommendation",
                     state["ask_states"]["Q7"]["state"] == "Accepted"
                     and len(state["new_events"]) == 1
                     and state["new_events"][0]["kind"] == "reaction"
                     and state["new_events"][0]["option"] == "C",
                     f"state={ {q: s['state'] for q, s in state['ask_states'].items()} }"))
state = rx_scan([{"content": "-1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"})
results.append(check("an allowlisted 👎 rejects it",
                     state["ask_states"]["Q7"]["state"] == "Rejected"))
state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}},
                 {"content": "-1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"})
results.append(check("👍 and 👎 on the same request decide nothing",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and not state["new_events"]
                     and any("conflicts" in (s.get("reaction") or "")
                             for s in state["ask_states"].values())))
state = rx_scan([{"content": "+1", "user": {"login": "ci-bot", "type": "Bot"}}],
                approvers={"ci-bot"})
results.append(check("a bot's 👍 never decides, even on the allowlist",
                     state["ask_states"]["Q7"]["state"] == "Pending" and not state["new_events"]))
state = rx_scan([{"content": "+1", "user": {"login": "unlisted", "type": "User"}}],
                approvers={"listed"})
results.append(check("a reaction from someone off the allowlist does not count",
                     state["ask_states"]["Q7"]["state"] == "Pending" and not state["new_events"]))
state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}}])
results.append(check("without an allowlist a reaction is read but decides nothing",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and not state["new_events"]
                     and any("no approver allowlist" in r for r in state["refused"]),
                     f"refused={state['refused']}"))
state = rx_scan([{"content": "laugh", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"})
results.append(check("any other reaction emoji is not a decision",
                     state["ask_states"]["Q7"]["state"] == "Pending"))
state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"}, asks=[dict(a) for a in ASKS], rx=False)
results.append(check("a request that did not opt in has its reactions left alone",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and "reaction" not in state["ask_states"]["Q7"]))
state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"}, rx=False)
comment = request_comment(asks=[dict(a) for a in ASKS], rx=True)
stub([comment], reactions={comment["id"]: [{"content": "+1", "user": {"login": "listed",
                                                                      "type": "User"}}]})
state = d.reconcile("o/r", 42, (), {"listed"}, True, ())
results.append(check("reactions on a request holding several questions are never interpreted",
                     state["ask_states"]["Q7"]["state"] == "Pending"
                     and any("opted into reactions but holds" in w for w in state["warnings"])))
state = rx_scan([{"content": "+1", "user": {"login": "listed", "type": "User"}}],
                approvers={"listed"})
results.append(check("an answer in words beats the reaction on the same question",
                     "reaction" in state["ask_states"]["Q7"]))

# ---------- 5. recording ----------

stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B")])
code, out, err = run(d.cmd_record, "42", [], None, False)
results.append(check("record shows the audit entry and writes nothing without --write",
                     code == 0 and not WRITES and "would append" in out and "Q7" in out,
                     f"code={code} writes={WRITES} out={out[:200]}"))
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B")])
code, out, err = run(d.cmd_record, "42", [], None, True)
posted = [w for w in WRITES if w[0] == "comment"]
results.append(check("record appends one audit comment naming actor, source and outcome",
                     code == 0 and len(posted) == 1 and "decision-audit" in posted[0][1]
                     and "issuecomment-20" in posted[0][1] and "maintainer" in posted[0][1]
                     and "option C" in posted[0][1], f"code={code} posted={len(posted)}"))
results.append(check("the audit comment repeats that a decision is not implementation approval",
                     "not implementation approval" in posted[0][1]
                     and "agent: approved" in posted[0][1]))

# a second run must find nothing new to say
seed_events = json.loads(d.AUDIT_RE.search(posted[0][1]).group(1))["events"]
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B"),
      audit_comment(seed_events)])
code, out, err = run(d.cmd_record, "42", [], None, True)
results.append(check("recording the same answers twice writes nothing the second time",
                     code == 0 and not [w for w in WRITES if w[0] == "comment"]
                     and "nothing to record" in out, f"code={code} out={out[:200]}"))

# the same answer posted twice is one event; posted twice differently is a conflict
state = scan([request_comment(),
              human("2026-11-01T06:00:00Z", "Q7: C", dbid=20),
              human("2026-11-01T06:05:00Z", "Q7: C", dbid=21)])
results.append(check("a duplicated identical answer is one decision",
                     len([e for e in state["new_events"] if e["q"] == "Q7"]) == 1))
state = scan([request_comment(),
              human("2026-11-01T06:00:00Z", "Q7: C", who="first", dbid=20),
              human("2026-11-01T07:00:00Z", "Q7: A", who="second", dbid=21)])
results.append(check("two maintainers deciding differently are clarified, not timed",
                     state["ask_states"]["Q7"]["state"] == "Needs clarification"
                     and not state["new_events"], f"state={state['ask_states']['Q7']}"))

# an answer that was recorded and is then edited keeps the recorded outcome
edited = human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B", dbid=20,
                updated="2026-11-03T06:00:00Z")
seed = audit_comment(seed_events)
state = scan([request_comment(), dict(edited, body="Q7: A\nQ8: B"), seed])
q7 = state["ask_states"]["Q7"]
results.append(check("a recorded answer that was edited later is clarified, never rewritten",
                     q7["state"] == "Needs clarification"
                     and "edited" in (q7.get("why") or "")
                     and not [e for e in state["new_events"] if e["q"] == "Q7"],
                     f"q7={q7}"))
state = scan([request_comment(), dict(edited, body="Q7: C\nQ8: B "), seed])
results.append(check("an edit that changes nothing in the outcome writes nothing new",
                     state["ask_states"]["Q7"]["state"] == "Accepted"
                     and not [e for e in state["new_events"] if e["q"] == "Q7"],
                     f"new={[e['q'] for e in state['new_events']]}"))

# a question with no answer at all is never recorded, and nothing can be invented
stub([request_comment()])
code, out, err = run(d.cmd_record, "42", [], None, True)
results.append(check("silence records nothing",
                     code == 0 and not WRITES and "nothing to record" in out))
stub([request_comment()])
code, out, err = run(d.cmd_record, "42", [], None, True)
results.append(check("an unanswered question stays Pending, not Deferred by omission",
                     "Pending" in out))

# no source, no decision: assert_source is the last gate before an event is appended
results.append(check("an event with no source is refused",
                     run(d.assert_source, {"q": "Q7", "kind": "answer"})[0] == 1))
results.append(check("an event built from a recommendation is refused",
                     run(d.assert_source, {"q": "Q7", "kind": "recommendation",
                                           "src": "https://x/1"})[0] == 1))
results.append(check("a reaction from a bot account is refused even with a source",
                     run(d.assert_source, {"q": "Q7", "kind": "reaction", "actor": "bot",
                                           "src": "https://x/1", "src_kind": "reaction",
                                           "reactor_type": "Bot"})[0] == 1))

# a claim, a question or a board comment is not an answer either: no label is ever written
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C")])
run(d.cmd_record, "42", [], None, True)
results.append(check("the protocol never writes a label or a pull request",
                     not [w for w in WRITES if w[0] not in ("comment", "body")]))

# ---------- 6. the register ----------

stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B")], body=REGISTER_BODY)
code, out, err = run(d.cmd_register, "42", [], None, False, False)
results.append(check("register writes nothing before --write and shows the rows it would touch",
                     code == 0 and not WRITES and "D04" in out and "D05" in out,
                     f"code={code} out={out[:200]}"))

stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B")], body=REGISTER_BODY)
audit_seed = audit_comment(seed_events)
WRITES.clear()
d.fetch_comments = lambda R, n: [request_comment(),
                                 human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B"), audit_seed]
ISSUE["body"] = REGISTER_BODY
code, out, err = run(d.cmd_register, "42", [], None, True, False)
new_body = ISSUE["body"]
untouched = (new_body.startswith("# RFC") and "| D01 |" in new_body
             and "Unrelated section that must survive untouched." in new_body
             and "A decision is accepted only when a maintainer records it." in new_body)
results.append(check("register updates the decided rows and leaves the rest of the body alone",
                     code == 0 and "Accepted 2026-11-01" in new_body and untouched,
                     f"code={code} body={new_body[:200]}"))
results.append(check("a synchronized row keeps the reviewer cell and the question's own answer",
                     "| Maintainers |" in new_body.split("D04")[1].split("\n")[0]
                     and "issuecomment-20" in new_body))
results.append(check("the note under the register says what a recorded decision is not",
                     "decision-note" in new_body and "not permission to implement" in new_body))
WRITES.clear()
second = run(d.cmd_register, "42", [], None, True, False)
results.append(check("synchronizing an already synchronized register writes nothing again",
                     second[0] == 0 and "nothing changed" in second[1]
                     and not [w for w in WRITES if w[0] == "body"],
                     f"code={second[0]} out={second[1][:200]}"))

# a row that names an unanswered question may not read Accepted
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C")], body=REGISTER_BODY)
d.fetch_comments = lambda R, n: [request_comment(),
                                 human("2026-11-01T06:00:00Z", "Q7: C"),
                                 audit_comment(seed_events[:1])]
code, out, err = run(d.cmd_register, "42", [], None, True, False)
results.append(check("a row that still waits on a question is refused, not marked Accepted",
                     code == 0 and "D05" in out and "waits on Q8" in out
                     and "| D05 | Schema | **Open / blocking** |" in ISSUE["body"],
                     f"out={out[:300]}"))

# a body without a register table is refused instead of being rewritten
stub([request_comment()], body="# RFC\n\nno table here\n")
code, out, err = run(d.cmd_register, "42", [], None, True, False)
results.append(check("an issue body with no register table is refused, not edited",
                     code == 1 and "no parseable" in err and not WRITES,
                     f"code={code} err={err}"))

# a body that moved while the write was prepared is not overwritten
WRITES.clear()
d.fetch_comments = lambda R, n: [request_comment(),
                                 human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B"), audit_seed]
ISSUE["body"] = REGISTER_BODY
original_view = d.issue_view
READS = []


def racing_view(R, n):
    """The second read sees somebody else's edit, which is exactly the race."""
    READS.append(1)
    body, ts = original_view(R, n)
    if len(READS) >= 2:
        return body + "\nA human added this while we were preparing.\n", "2026-11-01T00:05:00Z"
    return body, ts


d.issue_view = racing_view
code, out, err = run(d.cmd_register, "42", [], None, True, False)
results.append(check("a body edited by someone else in the meantime stops the write",
                     code == 1 and "changed since it was read" in err and not WRITES,
                     f"code={code} err={err}"))

# a reopened decision keeps its history and the row says it was reopened
reopen_event = dict(recorded_event(qid="Q7", state="Pending", option=None, kind="reopen",
                                   ts="2026-11-05T00:00:00Z", src_ref="c21:cafe000000"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", dbid=20),
              audit_comment([seed_events[0], reopen_event], dbid=95)])
q7 = state["ask_states"]["Q7"]
results.append(check("a reopened question is Pending again while the trail keeps the old outcome",
                     q7["state"] == "Pending" and q7["recorded"]["kind"] == "reopen"
                     and len(state["events"]) == 2 and not state["new_events"],
                     f"q7={q7}"))
ISSUE["body"] = REGISTER_BODY
WRITES.clear()
d.fetch_comments = lambda R, n: [request_comment(),
                                 human("2026-11-01T06:00:00Z", "Q7: C\nQ8: B"),
                                 audit_comment([seed_events[0], reopen_event])]
d.issue_view = lambda R, n: (ISSUE["body"], ISSUE["updated"])
code, out, err = run(d.cmd_register, "42", [], None, True, False)
results.append(check("the reopened row says Reopened and points at the trail",
                     code == 0 and "Reopened" in ISSUE["body"]
                     and "audit trail" in ISSUE["body"]
                     and "| D05 |" in ISSUE["body"], f"code={code} out={out[:200]}"))

# a gated question: the answer is recorded as a preference, the owner keeps the decision
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C")],
             gates=["Q7=@armin11:standards review"])
results.append(check("a gated answer is a preference, and the decision waits for its owner",
                     state["ask_states"]["Q7"]["state"] == "Awaiting review"
                     and state["decisions"]["D04"]["state"] == "Awaiting @armin11",
                     f"state={state['ask_states']['Q7']} decisions={state['decisions']}"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", who="armin11",
                                       dbid=22)], gates=["Q7=@armin11:standards review"])
results.append(check("the owner's own answer lifts the gate",
                     state["ask_states"]["Q7"]["state"] == "Awaiting review"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C")],
             maps=["Q7=D04", "Q7=D77"])
results.append(check("--map adds a decision link the request text does not carry",
                     "D77" in state["decisions"] and state["decisions"]["D77"]["state"] == "Accepted"))

# the trail carries the link: after record persisted --map into the event,
# a later reconcile without --map must still see the decision
mapped = recorded_event(did=("D04", "D88"))
state = scan([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C"),
              audit_comment([mapped])])
results.append(check("a decision link recorded in the trail survives a scan without --map",
                     "D88" in state["decisions"]
                     and state["decisions"]["D88"]["state"] == "Accepted"
                     and state["decisions"]["D04"]["state"] == "Accepted",
                     f"decisions={state['decisions']}"))

# a decision nobody decided cannot be written into the register by --map alone
ISSUE["body"] = REGISTER_BODY
WRITES.clear()
stub([request_comment()], body=REGISTER_BODY)
d.fetch_comments = lambda R, n: [request_comment()]
code, out, err = run(d.cmd_register, "42", [], None, True, False, map_specs=["Q7=D04"])
results.append(check("an unanswered question cannot move a register row",
                     code == 0 and ISSUE["body"] == REGISTER_BODY and not WRITES,
                     f"code={code} body={ISSUE['body'][:120]}"))

# ---------- 7. reopen and override need a human source ----------

STORAGE = {"21": human("2026-11-03T06:00:00Z", "Q7 was decided too early, please reopen it",
                       who="maintainer", dbid=21)}
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C")], comment_store=STORAGE)
code, out, err = run(d.cmd_reopen, "42", "Q7",
                     "https://github.com/o/r/issues/42#issuecomment-21", "reopened", None, False)
results.append(check("reopen verifies the cited human comment before writing",
                     code == 0 and not WRITES and "would be reopened" in out,
                     f"code={code} out={out[:200]} err={err}"))
code, out, err = run(d.cmd_reopen, "42", "Q7",
                     "https://github.com/o/r/issues/42#issuecomment-99", "reopened", None, True)
results.append(check("reopen refuses a source comment that does not exist",
                     code == 1 and "does not exist" in err and not WRITES, f"err={err}"))
STORAGE["22"] = human("2026-11-03T06:00:00Z", "let us take option B", who="stranger",
                      assoc="NONE", dbid=22)
code, out, err = run(d.cmd_reopen, "42", "Q7",
                     "https://github.com/o/r/issues/42#issuecomment-22", "reopened", None, True)
results.append(check("reopen refuses a source comment from someone who may not decide",
                     code == 1 and "cannot decide" in err, f"err={err}"))
STORAGE["23"] = human("2026-11-03T06:00:00Z", "please revisit this", who="maintainer", dbid=23)
code, out, err = run(d.cmd_reopen, "42", "Q7",
                     "https://github.com/o/r/issues/42#issuecomment-23", "reopened", None, True)
results.append(check("a source comment that never names the question is refused",
                     code == 1 and "does not mention Q7" in err, f"err={err}"))
STORAGE["24"] = human("2026-11-03T06:00:00Z",
                      "<!-- agent-claim {\"v\":1} -->\n\nQ7 reopen please",
                      who="agentbot", assoc="NONE", dbid=24)
code, out, err = run(d.cmd_reopen, "42", "Q7",
                     "https://github.com/o/r/issues/42#issuecomment-24", "reopened", None, True)
results.append(check("an agent comment cannot be the source of a decision",
                     code == 1 and "machine-managed" in err, f"err={err}"))
WRITES.clear()
code, out, err = run(d.cmd_override, "42", "Q7", "Rejected",
                     "https://github.com/o/r/issues/42#issuecomment-21",
                     "the maintainer changed their mind", None, True)
results.append(check("an override records the outcome with its verified human source",
                     code == 0 and len([w for w in WRITES if w[0] == "comment"]) == 1
                     and "override" in WRITES[0][1] and "issuecomment-21" in WRITES[0][1],
                     f"code={code} writes={WRITES}"))
code, out, err = run(d.cmd_override, "42", "Q7", "Merged",
                     "https://github.com/o/r/issues/42#issuecomment-21", "x", None, True)
results.append(check("an outcome outside the vocabulary is refused",
                     code == 1 and "--outcome" in err, f"err={err}"))

# a reopen recorded from a human comment really does send the question back to Pending
stub([request_comment(), human("2026-11-01T06:00:00Z", "Q7: C", dbid=20),
      audit_comment([reopen_event], dbid=96)])
results.append(check("a reopen event makes an older answer stop counting",
                     d.reconcile("o/r", 42, (), None, True, False)["ask_states"]["Q7"]["state"]
                     == "Pending"))

# --- which issue does a branch name? (the #1196 class: a prompt echo is not a claim)
# The rule is scripts/wip's function, not a copy of its pattern, so this checks
# the reuse holds rather than comparing two strings that could drift.
results.append(check("the branch rule is scripts/wip's, not a copy of its pattern",
                     getattr(d, "BRANCH_ISSUE_RE", None) is None
                     and hasattr(d.wip, "branch_issue")))
for branch, want in [("ao/issue-123-add-x", 123),        # what the controller asks AO for
                     ("feature/issue-123-topic", 123),   # the repository convention
                     ("issue_123", 123), ("issue123", 123), ("#123-topic", 123),
                     ("ao/implement-github-issue-6/root", None),  # a prompt echo
                     ("fix-issue-123", None),                      # mid-segment
                     ("release-2024-issue-3", None),
                     ("main", None), ("", None), (None, None)]:
    got = d.wip.branch_issue(branch)
    results.append(check("branch_issue(%r) is %r" % (branch, want), got == want, f"got={got}"))


def infer(branch, explicit):
    d.cur_branch = lambda: branch
    return run(d.infer_issue, explicit)


code, out, err = infer("ao/issue-9-fix-x", None)
results.append(check("a convention-shaped branch names its own issue",
                     code == 0, f"code={code} err={err}"))
code, out, err = infer("ao/implement-github-issue-6/root", None)
results.append(check("a branch that only echoes a prompt infers nothing",
                     code == 1 and "--issue" in err, f"code={code} err={err}"))
code, out, err = infer("ao/implement-github-issue-6/root", "981")
results.append(check("an explicit number still works from a prompt-echo branch",
                     code == 0 and not err.strip(), f"code={code} err={err}"))
code, out, err = infer("ao/issue-9-fix-x", "42")
results.append(check("an explicit number over another issue's branch is named, not refused",
                     code == 0 and "issue 9" in err and "42" in err,
                     f"code={code} err={err}"))
code, out, err = infer("main", "not-a-number")
results.append(check("a non-numeric issue number dies instead of raising",
                     code == 1 and "not an issue number" in err, f"code={code} err={err}"))
d.cur_branch = lambda: "main"

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
