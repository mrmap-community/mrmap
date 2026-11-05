"""The approval gate: which issue may an agent start work on, and why not.

One rule runs through this module. **A human must have said so, and the saying
must be provable from GitHub's own record.** Not a comment that reads like
approval, not a label the automation put there, not an absence of objection:
the last label event for the approval label, by an account the operator listed,
recorded as a human, with a role on the repository the operator trusts.

Two properties were chosen deliberately and are worth stating before the code:

*Fail closed.* Every way an answer can be missing - no configuration, no label
history, a rate limit in the middle of reading it, an approver whose role cannot
be looked up - is a *refusal*. A supervisor that treats "I could not check" as
"nobody objected" is worse than one that does nothing, because its inaction is
invisible while its action is not.

*Idempotent and stateless.* Nothing here remembers a previous answer. The gate
is a pure function of GitHub's current state plus the operator's configuration,
so a restart cannot resurrect a decision an operator has since revoked, and two
runners on one host cannot disagree.

Revocation is immediate and needs no new code: revoking is removing the label,
which makes the *last* label event an ``unlabeled`` event, and the next tick
sees it.

The reason codes are part of the interface - the CLI prints them, the operator
docs list them, and the tests assert on them. They are prefixed with the thing
that stopped the gate, so `explain` output reads as an instruction.
"""

from datetime import datetime, timedelta, timezone

from . import gh
from .config import REPORTED_ROLES, normalize_label

# Reason codes, in the order the gate reaches them.
CONFIG_INVALID = "config-invalid"
ISSUE_UNAVAILABLE = "issue-unavailable"
IS_PULL_REQUEST = "is-pull-request"
NOT_OPEN = "not-open"
PAUSED = "paused"
NO_APPROVAL_LABEL = "no-approval-label"
ALLOWLIST_EMPTY = "allowlist-empty"
HISTORY_UNAVAILABLE = "history-unavailable"
HISTORY_INCOMPLETE = "history-incomplete"
APPROVAL_REVOKED = "approval-revoked"
NON_HUMAN_APPROVER = "non-human-approver"
SELF_APPROVAL = "self-approval"
UNAUTHORIZED_APPROVER = "unauthorized-approver"
UNVERIFIED_ASSOCIATION = "unverified-association"
APPROVAL_TOO_OLD = "approval-too-old"

ELIGIBLE = "eligible"

# The coarse roles `association_of` can report, and the names an operator may
# list in `trusted_associations`, both live in `config.py` - the operator-facing
# vocabulary has one home.


class Decision:
    """The answer for one issue: `eligible`, plus the reason and what was read."""

    def __init__(self, number, eligible, reason, detail="", facts=None):
        self.number = number
        self.eligible = eligible
        self.reason = reason
        self.detail = detail
        self.facts = facts or {}

    def __repr__(self):
        return f"<Decision {self.number} {'yes' if self.eligible else 'no'} {self.reason}>"

    @property
    def code(self):
        """Reason without the identifying suffix, for counting and for tests."""
        return self.reason.split(":", 1)[0]

    def as_dict(self):
        return {"issue": self.number, "eligible": self.eligible,
                "reason": self.reason, "detail": self.detail, "facts": self.facts}

    def line(self):
        if self.eligible:
            return f"#{self.number}: eligible ({self.approver_line()})"
        return f"#{self.number}: not eligible - {self.reason}: {self.detail}"

    def approver_line(self):
        who = self.facts.get("approver")
        when = self.facts.get("approved_at")
        if not who:
            return "no approver recorded"
        return f"approved by {who}" + (f" at {when}" if when else "")


def parse_ts(value):
    """GitHub timestamps are ISO 8601 with a Z. Unparsable is None, not a guess."""
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        stamp = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def label_names(issue):
    """Label names of an issue payload, folded for comparison the way GitHub
    compares them (see config.normalize_label)."""
    return {normalize_label(one.get("name")) for one in (issue.get("labels") or [])}


def issue_of(repo, number):
    """The issue as GitHub has it now. Raises gh.GhError; `pull_request` key
    marks the number as a pull request, which is not a work item."""
    return gh.gh_json(f"repos/{repo}/issues/{number}")


def association_of(repo, login):
    """How GitHub rates this account for this repository: OWNER, COLLABORATOR,
    READ, NONE or UNKNOWN.

    The permission endpoint is the only one that answers for an arbitrary
    account, and it needs push access on the repository to answer at all. Any
    error therefore yields UNKNOWN rather than a guess, and the caller decides
    whether an unknown role can be trusted (it cannot, unless the operator
    switched the requirement off).
    """
    try:
        data = gh.gh_json(f"repos/{repo}/collaborators/{login}/permission")
    except gh.GhError:
        return "UNKNOWN"
    permission = (data or {}).get("permission")
    role = (data or {}).get("role_name")
    if permission == "admin" or role in ("Admin", "Owner"):
        candidate = "OWNER"
    elif permission in ("maintain", "write") or role in ("Maintain", "Write"):
        candidate = "COLLABORATOR"
    elif permission in ("triage", "read"):
        candidate = "READ"
    elif permission in (None, "none"):
        candidate = "NONE"
    else:
        candidate = "UNKNOWN"
    # A GitHub vocabulary this module does not know yet stays UNKNOWN: an
    # unrecognised answer cannot be a trusted one.
    return candidate if candidate in REPORTED_ROLES else "UNKNOWN"


def trusted(role, cfg):
    wanted = {str(x).upper() for x in (cfg.get("trusted_associations") or [])}
    return role in wanted


def approval_events(repo, number, label):
    """Every labeled/unlabeled event for `label`, oldest first.

    Reads the whole timeline rather than the issue's current labels: the labels
    say what is true now, the timeline says who made it true, and only the
    second one is evidence. Raises gh.GhError if any page is unreadable - a
    partial timeline is not evidence either.
    """
    wanted = normalize_label(label)
    events = gh.list_paginated(f"repos/{repo}/issues/{number}/timeline",
                                       {"per_page": gh.PER_PAGE})
    out = []
    for event in events:
        if event.get("event") not in ("labeled", "unlabeled"):
            continue
        name = normalize_label((event.get("label") or {}).get("name"))
        if name != wanted:
            continue
        actor = event.get("actor") or {}
        out.append({
            "action": event["event"],
            "login": actor.get("login") or "",
            "actor_type": actor.get("type") or "",
            "at": parse_ts(event.get("created_at")),
        })
    out.sort(key=lambda e: e["at"] or datetime.min.replace(tzinfo=timezone.utc))
    return out


def _agent_logins(cfg):
    """Accounts whose approval is not independent: the ones listed as agents,
    plus whatever this host's gh credential acts as."""
    logins = {str(x).lower() for x in cfg.agent_accounts}
    me = gh.whoami()
    if me:
        logins.add(me.lower())
    return logins


def decide(cfg, number, issue=None, now=None):
    """May an agent start (or continue) work on this issue right now?

    Returns a Decision. `issue` lets a caller that already listed the issue pass
    the payload through; it is re-read only if it is missing.
    """
    now = now or datetime.now(timezone.utc)
    if not cfg.ok:
        return Decision(number, False, CONFIG_INVALID,
                        "the configuration is not usable, so nothing is authorized: "
                        + "; ".join(cfg.problems))

    repo = cfg.repo
    approved = str(cfg.get("approved_label"))
    paused = str(cfg.get("paused_label"))

    if issue is None:
        try:
            issue = issue_of(repo, number)
        except gh.GhError as exc:
            return Decision(number, False, f"{ISSUE_UNAVAILABLE}:{exc.kind}", str(exc))
    if not isinstance(issue, dict):
        return Decision(number, False, ISSUE_UNAVAILABLE, "GitHub answered no issue")

    facts = {"repo": repo, "labels": sorted(label_names(issue))}
    if issue.get("pull_request"):
        return Decision(number, False, IS_PULL_REQUEST,
                        "this number is a pull request, not a work item", facts)
    if issue.get("state") != "open":
        return Decision(number, False, NOT_OPEN,
                        f"the issue is {issue.get('state')}", facts)

    names = label_names(issue)
    facts["labels"] = sorted(names)
    if normalize_label(paused) in names:
        return Decision(number, False, PAUSED,
                        f"'{paused}' is set; a human suspended automated work here", facts)
    if normalize_label(approved) not in names:
        return Decision(number, False, NO_APPROVAL_LABEL,
                        f"'{approved}' is not on the issue; a human has to add it "
                        f"before any agent may work on it", facts)

    allowlist = {h.lower() for h in cfg.authorized_humans}
    if not allowlist:
        return Decision(number, False, ALLOWLIST_EMPTY,
                        "authorized_humans is empty", facts)

    try:
        events = approval_events(repo, number, approved)
    except gh.GhError as exc:
        return Decision(number, False, f"{HISTORY_UNAVAILABLE}:{exc.kind}",
                        f"the label history could not be read ({exc.kind}), and an "
                        f"unprovable approval is a denial: {exc}", facts)

    facts["events"] = [{"action": e["action"], "login": e["login"],
                        "type": e["actor_type"], "at": e["at"].isoformat() if e["at"] else None}
                       for e in events]

    if not events:
        return Decision(number, False, HISTORY_INCOMPLETE,
                        f"'{approved}' is on the issue but no label event for it is in "
                        f"the timeline; refusing to infer an approver", facts)

    last = events[-1]
    if last["action"] == "unlabeled":
        return Decision(number, False, APPROVAL_REVOKED,
                        f"the last word on '{approved}' was {last['login'] or 'someone'} "
                        f"removing it", facts)

    login = last["login"]
    facts["approver"] = login
    facts["approved_at"] = last["at"].isoformat() if last["at"] else None
    who = login or "an account GitHub did not name"

    if last["actor_type"] and last["actor_type"] != "User":
        return Decision(number, False, f"{NON_HUMAN_APPROVER}:{login}",
                        f"'{approved}' was set by {who}, which GitHub reports as "
                        f"{last['actor_type']}, not a person", facts)
    if not login:
        return Decision(number, False, "unknown-approver",
                        "the label event names no account to check", facts)

    same_account = bool(cfg.get("allow_same_account"))
    if not same_account and login.lower() in _agent_logins(cfg):
        return Decision(number, False, f"{SELF_APPROVAL}:{login}",
                        f"'{approved}' was set by {who} - an account the automation "
                        f"itself acts with. Approvals must come from an account that "
                        f"does not push the work", facts)
    if login.lower() not in allowlist:
        return Decision(number, False, f"{UNAUTHORIZED_APPROVER}:{login}",
                        f"{who} is not in authorized_humans", facts)

    if cfg.get("require_repo_association"):
        role = association_of(repo, login)
        facts["association"] = role
        if not trusted(role, cfg):
            return Decision(number, False, f"{UNVERIFIED_ASSOCIATION}:{login}",
                            f"{who} is {role} on {repo}; the gate accepts "
                            f"{', '.join(sorted(cfg.get('trusted_associations') or []))}. "
                            f"Set require_repo_association=false to allow the "
                            f"allowlist alone", facts)

    max_age = cfg.get("approval_max_age_days") or 0
    if max_age:
        if last["at"] is None:
            return Decision(number, False, APPROVAL_TOO_OLD,
                            "the approval event carries no readable time", facts)
        if now - last["at"] > timedelta(days=float(max_age)):
            return Decision(number, False, APPROVAL_TOO_OLD,
                            f"the approval is older than {max_age} days "
                            f"({facts['approved_at']})", facts)

    return Decision(number, True, ELIGIBLE, "", facts)


def explain(cfg, number):
    """The decision for one issue, with the reason phrased as an instruction."""
    return decide(cfg, number)


def pick_eligible(cfg, issues):
    """Filter a listing of issue payloads down to the eligible ones.

    The scheduler (#1059) calls this with the result of one list request; each
    candidate still gets its own history read, because that read is the point.
    """
    out = []
    for issue in issues or []:
        number = issue.get("number")
        if number is None:
            continue
        decision = decide(cfg, number, issue=issue)
        out.append(decision)
    return out
