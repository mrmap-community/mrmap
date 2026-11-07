.. _development-decision-requests:

=====================================
Decision Requests: Human-Agent Protocol
=====================================

.. sidebar:: Issue #1069

   The tool is ``scripts/decisions``; its offline checks are
   ``scripts/test_decisions.py`` (no ``gh``, no network — every GitHub-touching
   function is stubbed). The copy-paste rule for agents stays in ``AGENTS.md``
   under "Asking for human decisions"; this page is the background: the exact
   schema of the marker payloads, how actors are verified, and how an agent
   resumes a half-answered request after a context loss.

The repository rule is that only a person decides: only a person applies
``agent: approved``, only a person reviews and merges a pull request, and a
thread a human raised stays open until that human resolves it. Design
questions agents genuinely cannot answer — normative ISO/OGC reading, product
scope, migration risk appetite — used to be asked as prose questionnaires, and
their answers rotted: RFC #992 carried a Decision register reading
"Open / blocking" for weeks after a maintainer had answered every question
with ``Q7: C``-style replies nobody could point at. ``scripts/decisions``
makes those decisions auditable instead of buried in comment prose.

The three gates — do not conflate them
======================================

A change passes three distinct gates, and a decision request only ever moves
the first one:

1. **Design decisions** — what the thing should *be*. These belong to the
   issue, are taken by answering numbered questions, and are what this tool
   records.
2. **Implementation approval** — the ``agent: approved`` label. Only a person
   applies it; no answer to any question implies it, and the tool never
   writes labels. Every generated comment says this explicitly.
3. **Human PR review** — the quality gate on a concrete diff. Independent of
   both above; nothing here reviews, approves or merges a pull request.

The schema
==========

Everything the protocol writes is a normal GitHub comment or issue body, and
everything machine-read is delimited by an HTML comment marker. The audit
trail comments are the truth; the register table in the issue body is a
generated view of them — the same relationship the claim comments have to the
WIP board.

**Request comment** — first line is the marker
``<!-- decision-request {"v":1,"id":"dr-…","client":"…","issue":N,"asks":[…],"rx":bool,
"hash":"…","status":"pending",…} -->``. Each entry of ``asks`` carries ``q``
(the ``Q<n>`` id), ``d`` (the Decision-register rows it feeds), ``title``,
``options`` (letter → text), ``recommend`` (the agent's own stated view) and
optional ``blocking``. The rendered comment is readable without the marker:
headings ``### Q7 — Topic [BLOCKING] → D04``, option lines ``- C: …``,
``**Agent recommendation: C** — …``. Requests without a marker (the original
#992 shape) are still parsed, but the tool warns: an agent posts through a
maintainer's ``gh``, so an unmarked comment's provenance cannot be verified
after the fact.

**Answer** — plain grammar, one answer per line, ``;`` separating two:

.. code-block:: text

    Q7: C
    Q7: C - the reason, if you want to give one
    Q7: C; Q8: B
    Q7: defer              (keywords: approve(d)/yes/agree, reject/no/veto,
                            defer, discuss, unclear)

Free prose after the id is kept verbatim as long as it is unambiguous. Code
blocks, indented blocks, ``>`` quotes and the request's own copy/paste
template are blanked before parsing, so a template never answers its own
question; a machine-managed comment never answers either — an agent cannot
answer the questions it posted. Two answers run together in prose ("Q7: C and
Q8: B") are detected and refused as ambiguous, never guessed apart, and an
answer naming two options is clarified the same way. The letter test is
case-sensitive on purpose: the article "a" is not option A.

**Actor verification** — an answer decides only when GitHub's
``author_association`` on that comment is ``OWNER``, ``MEMBER`` or
``COLLABORATOR`` and the account is not a Bot. ``FIRST_TIME_CONTRIBUTOR`` and
``NONE`` do not decide; the refusal is printed with the reason. A project can
narrow who decides per run with ``--approvers`` or the
``MRMAP_DECISION_APPROVERS`` environment variable. (The org-membership API
answers 403 with a fine-grained token, which is why ``author_association`` —
present on every comment payload — is the verification path.)

**Reactions** decide only under an explicit opt-in and never alone: the
request must hold exactly one question *and* state a recommendation (the 👍
approves *that option*), an approver allowlist must be configured, the
reactor must be a non-Bot account on it, and a 👍/👎 conflict on the same
request decides nothing. A word answer always beats emoji.

**Audit trail** — ``decisions record`` appends one comment per run whose first
line is ``<!-- decision-audit {"v":1,…,"events":[…]} -->``. Each event names
its question, the decision rows it feeds, the outcome and option, the actor
and their ``author_association``, the source comment URL and a body hash, and
— when the question was gated — the owner whose review it still waits for.
Events are idempotent: re-running ``record`` posts nothing for outcomes
already on the trail. An event is refused before it is written if it carries
no source, if it is an agent recommendation dressed as a decision, or if a
reaction comes from a Bot.

**Gated questions** — ``--gate 'Q1-Q6=@armin11:standards review'`` records
answers as preferences: the event keeps the answer and gains a ``gate`` field,
the question's state reads *Awaiting review*, and the register row reads
``Awaiting @armin11`` — never ``Accepted`` — until @armin11 answers or
overrides. This is how a maintainer keeps ownership of a decision while still
leting the recorded preferences pile up underneath it.

**Question-to-decision links** — when the request text does not name the
register row a question feeds, ``--map 'Q1-Q4=D03'`` supplies the link;
``record`` persists it in the event, so every later ``register`` and ``scan``
run reads it back from the trail and the flag does not have to be repeated.

**Decision register** — ``decisions register`` rewrites only the rows of the
managed table (``ID | Topic | Status | Decision / evidence | Reviewer``) that
the trail can say something about, plus one managed note line below it. A row
whose evidence still names an unanswered question is reported as *waiting* and
never marked Accepted; rows without events (D01, D02 on #992) keep whatever a
human wrote; a body without a parseable register table is refused outright
instead of being rewritten; and the write re-reads the body first and stops
if a human edited it in the meantime.

**Reopen and override** — a human can undo or replace a recorded decision
without re-answering: ``reopen --question Q7 --source <comment-url>`` and
``override --question Q7 --outcome Rejected --source <url> --reason …``. Both
verify the cited comment the same way answers are verified — it must exist,
be written by a human who may decide, be machine-free and mention the
question — and then append a trail event. A reopen sends the row back to
*Reopened*; the old outcome stays in the trail.

Agent resume flow
=================

The point of the trail being on GitHub is that an agent's context is
disposable. After a context loss, crash or a handover between OpenCode and
Codex sessions, a resumed agent needs nothing but the issue number:

.. code-block:: text

    scripts/decisions --issue 992 scan        # what is asked, answered, open
    scripts/decisions --issue 992 record      # dry: what would be recorded
    scripts/decisions --issue 992 register    # dry: what the table would say

``scan`` reports every question with its state and prints unstructured reply
comments it could not read, so the agent asks the human to re-answer in the
grammar instead of interpreting prose. Because all state is re-derived from
the issue on every run, two agents can run the same commands in parallel
without any local file to reconcile, and a half-answered request resumes
exactly where the humans left it.

Running the checks
==================

The protocol's tests are attacks first and features second — strangers, bots,
edited answers, run-on lines, template self-answers and racing issue bodies
all get a check. They need neither ``gh`` nor network:

.. code-block:: text

    python3 scripts/test_decisions.py

Exit code ``0`` means every check passed. Like ``scripts/wip``, the tool only
reads and writes issue content — there is no code path that labels, reviews,
approves, merges or closes anything.
