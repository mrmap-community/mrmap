"""Protected host configuration for the supervisor - and why it is fail-closed.

The supervisor decides which issues an autonomous agent may work on. That
decision must not be readable-and-writable by the accounts it supervises, so it
lives in one JSON file outside the repository, owned by the operator, with a
strict default: **nothing is authorized until an operator says otherwise**. An
absent file, an unreadable file, an empty allowlist or a config that contradicts
itself all mean "no issue is eligible", never "let everything through".

The file holds no credentials. GitHub access runs over the host's ``gh`` and the
workers over OpenCode's own authentication, so there is nothing here to leak and
nothing for a log line to print.

Default location: ``~/.config/mrmap-agent-supervisor/config.json``
(or ``$MRMAP_SUPERVISOR_CONFIG``). ``scripts/agent_supervisor/cli.py config
--example`` prints a documented starting point.
"""

import json
import os
import stat

CONFIG_ENV = "MRMAP_SUPERVISOR_CONFIG"
DEFAULT_PATH = os.path.expanduser("~/.config/mrmap-agent-supervisor/config.json")

# The roles an operator may name in trusted_associations, and the coarse ones
# approvals.association_of() can actually report. NONE and UNKNOWN are results,
# never a trustworthy choice, so they are not in the first set.
KNOWN_ROLES = ("OWNER", "MEMBER", "COLLABORATOR", "ADMIN", "MAINTAIN",
               "WRITE", "TRIAGE", "READ")
REPORTED_ROLES = ("OWNER", "COLLABORATOR", "READ", "NONE", "UNKNOWN")

# Everything the supervisor can be told, with the value that is safe when the
# operator says nothing. Keys the operator does not set keep these; unknown keys
# are reported as problems instead of being silently ignored.
DEFAULTS = {
    "repo": "mrmap-community/mrmap",
    # The two labels of the authorization contract (#1058).
    "approved_label": "agent: approved",
    "paused_label": "agent: paused",
    "approved_label_color": "0E8A16",
    "paused_label_color": "D4A72C",
    "label_descriptions": {
        "agent: approved": "a human authorized automated work on this issue",
        "agent: paused": "automated work on this issue is temporarily suspended",
    },
    # Who may authorize. Empty means nobody: fail closed.
    "authorized_humans": [],
    # Accounts the automation itself acts as. An approval event by one of these
    # is the agent approving its own work, even if the login is also allowed.
    "agent_accounts": [],
    # Escape hatch ONLY for a host where one GitHub account both drives the
    # agents and reviews them. It relaxes exactly one check - the one that
    # refuses an approval from an account the automation acts with. The
    # allowlist still has to name that account, so it cannot open anything on
    # its own. Off by default; the CLI shouts when it is on.
    "allow_same_account": False,
    # An approval counts only if GitHub rates the actor's role on the repository
    # as one of these. MEMBER is GitHub's word for "in the organisation"; the
    # permission endpoint cannot tell it from a plain collaborator, so it answers
    # COLLABORATOR for both - keeping the name costs nothing and reads correctly.
    "trusted_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
    "require_repo_association": True,
    # 0 means "an approval stands until it is revoked", which is what #1058
    # asks for; a positive number adds a re-approval interval.
    "approval_max_age_days": 0,
    # Where the supervisor works. repo_root is the checkout it branches from.
    "repo_root": "",
    "worktree_root": "~/.local/share/mrmap-agent-supervisor/worktrees",
    "state_dir": "~/.local/share/mrmap-agent-supervisor",
    # Ignored files a Compose stack needs but a fresh worktree does not have.
    "worktree_env_files": [".env", "docker/backend/.mrmap.env"],
    # Scheduling limits (#1059). The capacity gate has the last word; these are
    # the supervisor's own ceilings, and a job class the gate cannot measure
    # never becomes one agent's opinion about what the host can take.
    "max_opencode_processes": 2,
    "max_test_stacks": 1,
    "tick_seconds": 60,
    # Daemon loop (#1063). A random part of this is added to and subtracted from
    # the tick, so several supervisors started together do not align their GitHub
    # reads into one spike every minute. 0 means "exactly every tick_seconds".
    "tick_jitter_s": 0,
    # The rotating log next to the state file. maxBytes of 0 means "do not
    # rotate" - on a host that ships logs itself, not a mistake.
    "log_max_bytes": 5242880,
    "log_backups": 3,
    # One heartbeat event per this many quiet ticks: enough to answer "was it
    # alive at 3 am" without an event per minute.
    "heartbeat_ticks": 30,
    # Order: these labels first, then the oldest issue, then the number. Issues
    # with none of them share the second rank and are worked oldest-first.
    "priority_labels": ["priority: critical", "priority: high"],
    # Reading the board and the timeline per candidate is the expensive part of
    # a tick; both bounds keep one tick from fanning out across the repository.
    "max_candidates_per_tick": 10,
    # A refusal whose cause is a human who has not labelled anything yet does not
    # need a fresh timeline read every minute. A refusal whose cause is GitHub
    # being unreachable is never cached.
    "verdict_cache_s": 600,
    "retry_backoff_s": 900,
    # A plan whose runner never appeared (a supervisor killed mid-start) is
    # forgotten after this long so the issue is not blocked forever.
    "plan_ttl_s": 900,
    # Worker lifecycle (#1060).
    "opencode_command": "opencode",
    "opencode_model": "",
    "opencode_agent": "",
    # What a session is called. It is the handle a restarted supervisor resumes
    # on, so it names the issue rather than the run.
    "session_prefix": "mrmap",
    "worker_timeout_s": 14400,
    "resume_timeout_s": 7200,
    # How long a withdrawn approval may take to take effect on a running worker:
    # the group gets TERM, waits this long, then KILL.
    "cancel_grace_s": 30,
    # Empty means the built-in deny list of config.WORKER_DENY_PERMISSIONS, which
    # a worker cannot override from inside its own session. A list here replaces
    # it - an operator who weakens it weakens it visibly, in one place.
    "worker_permissions": [],
    # Pull-request supervision (#1061, #1062).
    "ci_repair_attempts": 2,
    "pr_poll_seconds": 300,
    "review_debounce_seconds": 120,
    # How many answer-a-review cycles one pull request may cost over its whole
    # life. The per-review dedupe is in the ledger, not here: this is the bound
    # for a human and an agent going back and forth forever.
    "review_response_attempts": 3,
}

# What a worker may not do, whatever --auto grants. The supervisor pushes and
# opens pull requests itself; a worker that could merge would be the hole.
WORKER_DENY_PERMISSIONS = [
    {"action": "shell", "resource": "gh pr merge *", "effect": "deny"},
    {"action": "shell", "resource": "gh pr review *", "effect": "deny"},
    {"action": "shell", "resource": "gh pr edit *", "effect": "deny"},
    {"action": "shell", "resource": "gh api *merge*", "effect": "deny"},
    {"action": "shell", "resource": "gh api *reviews*", "effect": "deny"},
    # A review thread is settled by the human who raised it. This is not a
    # theoretical hole: the worker that #1062 wakes up to answer feedback is the
    # one process on the host with both the reason and the opportunity to mark
    # those threads closed. Replying underneath one stays possible - no pattern
    # here matches the reply route - because "what I changed" is the worker's job
    # and "settled" is not.
    {"action": "shell", "resource": "gh api *threads*", "effect": "deny"},
    {"action": "shell", "resource": "git push --force*", "effect": "deny"},
    {"action": "shell", "resource": "docker system prune *", "effect": "deny"},
    {"action": "read", "resource": "*.env", "effect": "deny"},
    {"action": "read", "resource": "*.env.*", "effect": "deny"},
]


def normalize_label(name):
    """A label name the way GitHub compares it.

    GitHub matches label names case-insensitively, and a label created through
    the API can hold an inner run of spaces that nobody sees in the web UI, so
    both are folded here. Comparing raw strings would let `Agent:  Approved`
    look like the approval label to a human eye and miss it in the gate.
    """
    return " ".join(str(name or "").strip().lower().split())


class Config:
    """Resolved configuration plus the operator-visible problems with it.

    ``problems`` close the gate - the supervisor refuses to consider any issue
    eligible while one stands. ``warnings`` do not: they describe a posture the
    operator chose deliberately (the single-account escape hatch, a config file
    that is group readable) and that must stay visible in every status output.
    """

    def __init__(self, data=None, path=None, problems=None, warnings=None):
        self.data = dict(DEFAULTS)
        self.data.update(data or {})
        self.path = path
        self.problems = list(problems or [])
        self.warnings = list(warnings or [])

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def __getitem__(self, key):
        return self.data[key]

    @property
    def repo(self):
        return self.data["repo"]

    @property
    def authorized_humans(self):
        return [str(x) for x in (self.data.get("authorized_humans") or [])]

    @property
    def agent_accounts(self):
        return [str(x) for x in (self.data.get("agent_accounts") or [])]

    @property
    def state_dir(self):
        return os.path.expanduser(self.data["state_dir"])

    @property
    def worktree_root(self):
        return os.path.expanduser(self.data["worktree_root"])

    @property
    def repo_root(self):
        """The checkout new worktrees are branched from.

        Empty means "the directory this was started from", which is right for a
        developer running ``plan`` in their own checkout. A deployment says so
        explicitly, because the daemon of #1063 runs as a service and its working
        directory is not something anyone should have to reason about.
        """
        return os.path.expanduser(self.data.get("repo_root") or os.getcwd())

    @property
    def log_dir(self):
        return os.path.join(self.state_dir, "logs")

    @property
    def ok(self):
        """No configuration problem means the gate may even be consulted."""
        return not self.problems

    def describe(self):
        """A printable view. Nothing in the configuration is a secret, but the
        allowlists are printed sorted so an operator can diff what they typed."""
        out = dict(self.data)
        out["_path"] = self.path
        out["_problems"] = self.problems
        out["_warnings"] = self.warnings
        return out


def config_path(explicit=None):
    return os.path.abspath(os.path.expanduser(
        explicit or os.environ.get(CONFIG_ENV) or DEFAULT_PATH))


def load(explicit=None):
    """Read the configuration. Never raises: a broken config is a problem list
    and a closed gate, because a supervisor that guesses its own allowlist is
    worse than one that does nothing."""
    path = config_path(explicit)
    problems = []
    if not os.path.exists(path):
        problems.append(
            f"no configuration file at {path}: no issue can be authorized. "
            f"Create it (see `cli.py config --example`) or point "
            f"{CONFIG_ENV} at one.")
        return Config(path=path, problems=problems)
    try:
        with open(path) as f:
            raw = json.load(f)
    except ValueError as exc:
        return Config(path=path, problems=[f"{path} is not valid JSON: {exc}"])
    except OSError as exc:
        return Config(path=path, problems=[f"{path} cannot be read: {exc}"])
    if not isinstance(raw, dict):
        return Config(path=path, problems=[f"{path} must hold one JSON object"])

    cfg = Config(raw, path=path, problems=problems)
    _validate(cfg)
    return cfg


def _validate(cfg):
    """Type and contradiction checks, including unknown keys. Every problem here
    closes the gate; a warning describes a posture the operator chose and keeps
    visible."""
    problems = cfg.problems
    warnings = cfg.warnings
    unknown = sorted(set(cfg.data) - set(DEFAULTS))
    if unknown:
        problems.append("unknown configuration keys (a typo is not a default): "
                        + ", ".join(unknown))
    for key, want in (("repo", str), ("approved_label", str), ("paused_label", str),
                      ("worktree_root", str), ("state_dir", str)):
        if not isinstance(cfg.data.get(key), want):
            problems.append(f"{key} must be a string")
    if not cfg.authorized_humans:
        problems.append("authorized_humans is empty: no account can authorize an "
                        "issue, so nothing is eligible (fail closed)")
    duplicates = [h for h in set(cfg.authorized_humans) if cfg.authorized_humans.count(h) > 1]
    if duplicates:
        problems.append("authorized_humans repeats: " + ", ".join(sorted(duplicates)))
    if not isinstance(cfg.data.get("agent_accounts"), list):
        problems.append("agent_accounts must be a list of logins")
    unknown_roles = sorted(
        {str(x).upper() for x in (cfg.data.get("trusted_associations") or [])} - set(KNOWN_ROLES))
    if unknown_roles:
        problems.append("trusted_associations holds roles GitHub cannot report ("
                        + ", ".join(unknown_roles) + "); the gate would then never "
                        "trust anyone. Known: " + ", ".join(sorted(KNOWN_ROLES)))
    if cfg.data.get("trusted_associations") == []:
        problems.append("trusted_associations is empty while require_repo_association "
                        "is on: no approver could ever be trusted")
    overlap = sorted(set(cfg.authorized_humans) & set(cfg.agent_accounts))
    if overlap and not cfg.data.get("allow_same_account"):
        problems.append(
            "these accounts are both approvers and agent accounts, which would let "
            f"the automation approve its own work: {', '.join(overlap)}. Use separate "
            "accounts, or set allow_same_account=true knowingly on a single-account host")
    if cfg.data.get("allow_same_account"):
        warnings.append(
            "allow_same_account=true: an approval by the account the agents push with "
            "is accepted. This is the documented escape hatch for a host where one "
            "GitHub account both reviews and drives the automation, and it is the one "
            "weakening of the model - the human is still required, but GitHub can no "
            "longer tell the two roles apart")
    if not cfg.data.get("approved_label") or not cfg.data.get("paused_label"):
        problems.append("approved_label and paused_label must both be set")
    if normalize_label(cfg.data.get("approved_label")) == \
            normalize_label(cfg.data.get("paused_label")):
        problems.append("approved_label and paused_label must differ")
    for key in ("approved_label", "paused_label"):
        if not normalize_label(cfg.data.get(key)):
            problems.append(f"{key} must be a label name, not blanks")
    if not isinstance(cfg.data.get("approval_max_age_days"), (int, float)):
        problems.append("approval_max_age_days must be a number")
    for key in ("max_opencode_processes", "max_test_stacks"):
        value = cfg.data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            problems.append(f"{key} must be a positive whole number")
    # A budget of n allows n cycles; a budget of 0 is not a typo for "one", it is
    # the operator saying "watch and report, never act". A slot count of 0 would
    # mean "run nothing", which is what `dry_run` is for.
    for key in ("ci_repair_attempts", "review_response_attempts"):
        value = cfg.data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"{key} must be a whole number, 0 allowed")
    if not isinstance(cfg.data.get("review_debounce_seconds"), (int, float)) \
            or cfg.data.get("review_debounce_seconds") < 0:
        problems.append("review_debounce_seconds must be a number of seconds, 0 allowed")
    if not isinstance(cfg.data.get("require_repo_association"), bool):
        problems.append("require_repo_association must be true or false")
    # The daemon's own bounds (#1063). A negative tick or jitter would make the
    # loop spin; a heartbeat below 1 would log an event every tick.
    for key in ("tick_seconds", "tick_jitter_s"):
        value = cfg.data.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            problems.append(f"{key} must be a number of seconds, 0 allowed")
    if cfg.data.get("tick_seconds") == 0:
        problems.append("tick_seconds of 0 would spin the loop; the smallest honest "
                        "interval is one second")
    for key in ("log_max_bytes", "log_backups", "heartbeat_ticks"):
        value = cfg.data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"{key} must be a whole number, 0 allowed")
    if cfg.data.get("heartbeat_ticks") == 0:
        problems.append("heartbeat_ticks of 0 would log a heartbeat every tick; "
                        "1 means one per tick already")
    if not cfg.data.get("repo_root"):
        warnings.append("repo_root is not set: the supervisor cannot branch or open a "
                        "worktree, so nothing can be started even when it is eligible")
    if not cfg.data.get("opencode_model"):
        warnings.append("opencode_model is empty: workers run with whatever model the "
                        "host's OpenCode defaults to")
    _warn_file_mode(cfg, warnings)


def _warn_file_mode(cfg, warnings):
    """A configuration that the agent accounts can rewrite is a suggestion. The
    file holds no secret, so this is a warning and not a refusal - but it is the
    kind of warning that should be in every status line until it is fixed."""
    if not cfg.path or not os.path.exists(cfg.path):
        return
    try:
        mode = stat.S_IMODE(os.stat(cfg.path).st_mode)
    except OSError:
        return
    if mode & 0o077:
        warnings.append(f"{cfg.path} is readable and writable by others "
                        f"(mode {oct(mode)}): the allowlist is the one thing the "
                        f"automation must not be able to edit. chmod 600 it")


def example():
    """The documented starting point, as data so docs and CLI cannot drift."""
    return {
        "repo": "mrmap-community/mrmap",
        "authorized_humans": ["your-github-login"],
        "agent_accounts": ["mrmap-agent-bot"],
        "repo_root": "/srv/mrmap/mrmap",
        "worktree_root": "/srv/mrmap/agent-worktrees",
        "state_dir": "/srv/mrmap/agent-state",
        "max_opencode_processes": 2,
        "max_test_stacks": 1,
        "opencode_model": "provider/model",
        "ci_repair_attempts": 2,
    }
