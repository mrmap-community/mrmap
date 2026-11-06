"""The operator's command line.

Everything a human needs to run and check the supervisor without reading code:
what the configuration says, whether the labels exist, why a specific issue may
or may not be started, the loop itself (`run`, `daemon`), per-issue hands
(`start`, `stop`, `pause`, `resume`, `logs`, `retry`), what the watchers know,
and the host numbers (`metrics`, `doctor`). The gate is a black box only from
the outside; `explain` is what makes it inspectable, and it is the same code
path the scheduler uses in every tick, so an answer here is the answer there.

Exit codes are for scripts and timers: usually 0 for "yes" or "done", 1 for
"no" or "something waits for a human", 2 for "the question could not be asked"
(no gh, unusable configuration). `run` adds 3 ("another daemon holds this state
directory") and 4 ("the configuration refuses everything"); see its own help.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

from . import VERSION
from . import approvals
from . import config as config_module
from . import gh
from .scheduler import Scheduler
from .runner import Runner, StartError
from .store import Store, human_age


def _load(args):
    return config_module.load(args.config)


def _emit(decisions, as_json):
    if as_json:
        print(json.dumps([d.as_dict() for d in decisions], indent=2, sort_keys=True))
        return
    for decision in decisions:
        print(decision.line())


def cmd_explain(args):
    cfg = _load(args)
    decisions = [approvals.explain(cfg, number) for number in args.issues]
    _emit(decisions, args.json)
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for problem in cfg.problems:
        print(f"config: {problem}", file=sys.stderr)
    if all(d.eligible for d in decisions):
        return 0
    return 1


def cmd_eligible(args):
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        print("no issue can be eligible while the configuration is broken", file=sys.stderr)
        return 2
    label = str(cfg.get("approved_label"))
    try:
        issues = gh.list_paginated(f"repos/{cfg.repo}/issues",
                                   {"state": "open", "labels": label})
    except gh.GhError as exc:
        print(f"cannot list issues labelled '{label}' ({exc.kind}): {exc}", file=sys.stderr)
        return 2
    decisions = approvals.pick_eligible(cfg, issues)
    _emit(decisions, args.json)
    if not decisions:
        print(f"nothing carries '{label}'; a human has to add it first")
        return 1
    return 0 if any(d.eligible for d in decisions) else 1


def cmd_labels(args):
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        return 2
    wanted = [(str(cfg.get("approved_label")), str(cfg.get("approved_label_color"))),
              (str(cfg.get("paused_label")), str(cfg.get("paused_label_color")))]
    descriptions = cfg.get("label_descriptions") or {}
    worst = 0
    for name, color in wanted:
        try:
            exists = gh.label_exists(cfg.repo, name)
        except gh.GhError as exc:
            print(f"{name}: cannot read the label list ({exc.kind}): {exc}", file=sys.stderr)
            return 2
        if exists:
            print(f"{name}: exists")
            continue
        if not args.create:
            print(f"{name}: MISSING - run with --create, or create it in the repository")
            worst = 1
            continue
        try:
            result = gh.create_label(cfg.repo, name, color,
                                     str(descriptions.get(name, "managed by the agent supervisor")))
            print(f"{name}: {result}")
        except gh.GhError as exc:
            print(f"{name}: cannot create ({exc.kind}): {exc}", file=sys.stderr)
            print("       creating a label needs write access on the repository; the "
                  "account that installs the supervisor is meant to have it, the workers "
                  "do not", file=sys.stderr)
            worst = 2
    if args.create:
        print("labels are only defined, never applied: applying the approval label is a "
              "human act and stays a human act")
    return worst


def cmd_config(args):
    if args.example:
        print(json.dumps(config_module.example(), indent=2, sort_keys=True))
        return 0
    cfg = _load(args)
    print(json.dumps(cfg.describe(), indent=2, sort_keys=True))
    if cfg.problems:
        print(f"\n{len(cfg.problems)} problem(s) close the gate:", file=sys.stderr)
        for problem in cfg.problems:
            print(f"  - {problem}", file=sys.stderr)
    if cfg.warnings:
        print(f"\n{len(cfg.warnings)} warning(s) do not:", file=sys.stderr)
        for warning in cfg.warnings:
            print(f"  - {warning}", file=sys.stderr)
    return 1 if cfg.problems else 0


def cmd_plan(args):
    """One tick, with nothing started. The command an operator runs to see what
    the queue would do, and the shape #1063's daemon loop will repeat."""
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        return 2
    runner = Runner(cfg) if args.start else None
    reconciled = []
    if runner is not None:
        # Before starting anything, work out what a crash or a reboot left
        # behind. Starting a worker into an unreconciled lease is how a host ends
        # up with two clients on one branch.
        reconciled = runner.reconcile()
    scheduler = Scheduler(cfg, runner=runner)
    report = scheduler.tick(plan_only=not args.start)
    report["reconciled"] = reconciled
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report, plan_only=not args.start)
        for row in reconciled:
            print(f"  reconciled #{row['issue']}: {row['reading']} - {row['action']}")
    return 0 if not report["errors"] else 1


def _print_report(report, plan_only):
    capacity = report.get("capacity") or {}
    print(f"considered {report.get('considered', 0)} issue(s) carrying the approval label; "
          f"capacity {capacity.get('verdict', 'not asked')} {capacity.get('explanation', '')}")
    key = "planned" if plan_only else "started"
    for number, branch, needs in report.get(key, []):
        print(f"  {key}: #{number} -> {branch} ({needs})")
    for number, reason, detail in report.get("skipped", []):
        print(f"  skipped #{number}: {reason} - {detail}")
    for number, reason in report.get("stopping", []):
        print(f"  stopping #{number}: {reason}")
    for error in report.get("errors", []):
        print(f"  error: {error}", file=sys.stderr)
    if plan_only and report.get("planned"):
        print("planned only: nothing was started; run with --start to hand the work to "
              "the runner (#1060)")


def cmd_status(args):
    cfg = _load(args)
    store = Scheduler(cfg).store
    info = store.status()
    waiting = store.waiting_for_human()
    events = store.recent_events(limit=args.events)
    if args.json:
        print(json.dumps({"config": cfg.path, "ok": cfg.ok, "problems": cfg.problems,
                          "warnings": cfg.warnings, "state": info["path"],
                          "leases": info["leases"],
                          "waiting_for_human": [lease["issue"] for lease in waiting],
                          "pull_requests": info["pulls"],
                          "review_watches": info["reviews"],
                          "events": events}, indent=2, default=str))
        return 1 if cfg.problems else 0
    print(f"state: {info['path']}")
    if not info["leases"]:
        print("leases: none")
    for lease in info["leases"]:
        print(f"  #{lease['issue']} {lease['state']:9s} {lease.get('needs') or '-':7s} "
              f"{lease.get('branch') or ''} pid={lease.get('pid')} "
              f"since {human_age(lease['started_at'])}"
              + (f" - {lease['detail']}" if lease.get("detail") else ""))
    if waiting:
        print(f"waiting for a human: {', '.join('#%d' % lease['issue'] for lease in waiting)}")
    # The CI watcher's rows belong here too: the question an operator asks at 8 am
    # is "is anything waiting for me", and after #1061 that includes a pull request
    # whose pipeline is red in a way no worker is allowed to fix.
    pulls = [row for row in info["pulls"] if row["state"] != "closed"]
    if pulls:
        print("pull requests under CI watch:")
        for row in pulls:
            print(f"  #{row['issue']} pr #{row['pr']} {row['state']:14s} "
                  f"repair attempts {row['attempts']}"
                  + (f" - {row['detail']}" if row.get("detail") else ""))
    needs_human = [row["issue"] for row in pulls if row["state"] == "waiting-human"]
    # Review feedback belongs to the same 8 am question. A pull request whose
    # reviewer asked for something an agent may not do is waiting just as hard as
    # one whose pipeline is red, and an operator should not have to know which
    # watcher noticed it.
    reviews = [row for row in info["reviews"] if row["state"] != "closed"]
    if reviews:
        print("pull requests under review watch:")
        for row in reviews:
            print(f"  #{row['issue']} pr #{row['pr']} {row['state']:14s} "
                  f"answer attempts {row['attempts']}"
                  + (f" - {row['detail']}" if row.get("detail") else ""))
        needs_human += [row["issue"] for row in reviews if row["state"] == "waiting-human"]
    if needs_human:
        print("pull requests waiting for a human: "
              f"{', '.join('#%d' % issue for issue in sorted(set(needs_human)))}")
    print("recent events:" if events else "no events recorded")
    for event in events:
        stamp = datetime.fromtimestamp(event["at"], timezone.utc).strftime("%m-%d %H:%M:%S")
        print(f"  {stamp} {event['kind']}"
              + (f" #{event['issue']}" if event.get("issue") else "")
              + (f" - {event['detail']}" if event.get("detail") else ""))
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for problem in cfg.problems:
        print(f"config: {problem}", file=sys.stderr)
    return 1 if cfg.problems else 0


def _runner(args):
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        return None, None
    return cfg, Runner(cfg)


def cmd_logs(args):
    """What the worker of one issue wrote, newest lines last.

    Read from the state directory, not from the worktree: a branch that was never
    pushed still has to explain itself, and the log is the only record of a run
    that died before it could comment anywhere.
    """
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    text, path = runner.logs(args.issue, tail=args.tail)
    if not text:
        print(f"no worker log for #{args.issue} under {cfg.state_dir}", file=sys.stderr)
        return 1
    print(f"# {path}")
    print(text)
    return 0


def cmd_pause(args):
    """Stop the worker of one issue and leave its branch standing."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    try:
        outcome = runner.pause(args.issue, args.reason)
    except StartError as exc:
        print(f"not paused: {exc}", file=sys.stderr)
        return 1
    print(f"#{args.issue} stopped"
          + (" (had to be killed)" if outcome.get("forced") else "")
          + "; branch, worktree and logs are left as they are")
    return 0


def cmd_resume(args):
    """Continue the recorded session of one issue, if the gate still allows it."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    try:
        handle = runner.resume(args.issue)
    except StartError as exc:
        print(f"not resumed: {exc}", file=sys.stderr)
        return 1
    print(f"#{args.issue} resumed on session {handle['session']} "
          f"(pid {handle['pid']}, log {handle['log']})")
    return 0


def cmd_reconcile(args):
    """What a crash or a reboot left behind, and what was done about it."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    rows = runner.reconcile()
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    elif not rows:
        print("nothing to reconcile: no lease of this supervisor is unaccounted for")
    for row in rows:
        print(f"  #{row['issue']}: {row['reading']} - {row['action']} ({row['detail']})")
    return 0


def cmd_stack_down(args):
    """Tear down one job's Compose stack, by the project its lease recorded."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    lease = runner.store.lease(args.issue)
    if not lease or not lease.get("project"):
        print(f"#{args.issue} has no recorded Compose project here", file=sys.stderr)
        return 1
    try:
        runner.cleanup_stack(args.issue, lease["project"], volumes=not args.keep_volumes)
    except StartError as exc:
        print(f"not torn down: {exc}", file=sys.stderr)
        return 1
    print(f"{lease['project']} torn down"
          + ("" if not args.keep_volumes else " (volumes kept)"))
    return 0


def cmd_prs(args):
    """What the CI watcher knows about the pull requests of this supervisor's work."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    rows = runner.store.status()["pulls"] if args.all else runner.store.watched_prs()
    if args.json:
        # JSON only: #1063's daemon reads this output, and a human line after a
        # closing bracket is not parseable.
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("no pull request is under CI watch yet (watch-prs records them)")
    for row in rows:
        print(f"  #{row['issue']} pr #{row['pr']} [{row['state']}] "
              f"attempts {row['attempts']} - {row['detail'] or 'nothing recorded'}")
    return 0


def cmd_watch_prs(args):
    """One look at the CI of every pull request this supervisor's workers opened."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    from .ci_monitor import Monitor

    monitor = Monitor(cfg, store=runner.store, runner=runner)
    try:
        report = monitor.watch(issue=args.issue, dry_run=args.dry_run)
    except gh.GhError as exc:
        print(f"cannot watch CI: {exc}", file=sys.stderr)
        return 2
    actions = {}
    for row in report:
        actions[row["action"]] = actions.get(row["action"], 0) + 1
    # A pull request that is red and cannot be repaired is a human's decision, and
    # a non-zero exit is how a cron entry notices that one is waiting.
    waiting = sum(count for key, count in actions.items()
                  if key in ("escalated", "escalation-failed", "held", "repair-refused"))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 1 if waiting else 0
    for row in report:
        print(f"  #{row.get('issue')} "
              + (f"pr #{row['pr']} " if row.get("pr") else "")
              + f"{row['action']}"
              + (f" [{row['verdicts']}]" if row.get("verdicts") else "")
              + (f" - {row['detail']}" if row.get("detail") else ""))
    if not report:
        print("nothing to watch: no lease of this supervisor has an open pull request")
    print("watched: " + (", ".join(f"{key} {count}" for key, count in sorted(actions.items()))
                         or "nothing"))
    return 1 if waiting else 0


def cmd_reviews(args):
    """What the review watcher knows about this supervisor's pull requests."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    rows = runner.store.reviewed_prs() if not args.all else runner.store.status()["reviews"]
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("no pull request is under review watch yet (watch-reviews records them)")
    for row in rows:
        pending = runner.store.review_items(row["pr"], statuses=("pending",))
        print(f"  #{row['issue']} pr #{row['pr']} [{row['state']}] "
              f"attempts {row['attempts']} - {row['detail'] or 'nothing recorded'}")
        for item in pending[:args.items]:
            print(f"      open: {item['kind']} {item['github_id']} by {item['author']} "
                  + (f" at {item['path']}:{item['line']}" if item.get("path") else "")
                  + (f" - {item['detail']}" if item.get("detail") else ""))
        if len(pending) > args.items:
            print(f"      and {len(pending) - args.items} more")
    return 0


def cmd_watch_reviews(args):
    """One look at the review feedback on those pull requests."""
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    from .reviews import Reviews

    watcher = Reviews(cfg, store=runner.store, runner=runner)
    try:
        report = watcher.watch(issue=args.issue, dry_run=args.dry_run)
    except gh.GhError as exc:
        print(f"cannot watch reviews: {exc}", file=sys.stderr)
        return 2
    actions = {}
    for row in report:
        actions[row["action"]] = actions.get(row["action"], 0) + 1
    # Feedback that only a human can settle has to leave a non-zero exit, or a
    # timer runs it for a year and nobody reads it.
    waiting = sum(count for key, count in actions.items()
                  if key in ("escalated", "escalation-failed", "held", "respond-refused"))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 1 if waiting else 0
    for row in report:
        counts = [f"{row['work']} work", f"{row['asks']} ask(s)", f"{row['context']} context"]
        print(f"  #{row.get('issue')} "
              + (f"pr #{row['pr']} " if row.get("pr") else "")
              + f"{row['action']}"
              + (f" [{', '.join(counts)}]" if row.get("items") else "")
              + (f" - {row['detail']}" if row.get("detail") else ""))
    if not report:
        print("nothing to watch: no pull request of this supervisor is open")
    print("watched: " + (", ".join(f"{key} {count}" for key, count in sorted(actions.items()))
                         or "nothing"))
    return 1 if waiting else 0


# ---------------------------------------------------------------------------
# the loop and its controls (#1063)

def cmd_run(args):
    """The supervisor loop: plan, follow CI, follow review feedback, sleep.

    This is what systemd starts and what a human runs to watch one tick. The
    exit codes are the timer's contract, continued from the watchers: 0 nothing
    waits, 1 something needs a human, 3 another daemon holds this state
    directory, 4 the configuration refuses everything.
    """
    from .daemon import Daemon, setup_logging
    cfg = _load(args)
    if args.json and not args.once:
        print("--json belongs to --once: a stream of JSON documents is not JSON",
              file=sys.stderr)
        return 2
    # Foreground means stderr too: under systemd that is how the journal gets
    # its copy, and beside the rotated file it costs nothing.
    daemon = Daemon(cfg, log=setup_logging(cfg, foreground=True))
    code = daemon.run(once=args.once, dry_run=args.dry_run)
    if args.json and daemon.last_report is not None:
        print(json.dumps(daemon.last_report, indent=2, default=str))
    return code


def cmd_daemon(args):
    """Start, stop, pause, resume or read the background supervisor."""
    from . import daemon as daemon_module
    cfg = _load(args)
    action = args.daemon_action
    if action == "start":
        if not cfg.ok:
            for problem in cfg.problems:
                print(f"config: {problem}", file=sys.stderr)
            return 4
        outcome = daemon_module.spawn(cfg)
        if outcome.get("started"):
            print(f"supervisor started detached: pid {outcome['pid']}, log "
                  f"{outcome['log']}")
            return 0
        print(f"not started: {outcome['reason']}", file=sys.stderr)
        return 1
    if action == "stop":
        outcome = daemon_module.stop(cfg, timeout_s=args.timeout)
        if outcome.get("stopped"):
            print(f"supervisor stopped ({outcome['reason']}); any worker it was "
                  "watching keeps running and the next start adopts it")
            return 0
        print(f"not stopped: {outcome['reason']}", file=sys.stderr)
        return 1
    if action == "pause":
        payload = daemon_module.pause(cfg, args.reason)
        Store.for_config(cfg).event("daemon-paused", args.reason)
        print("supervisor paused: watchers and starts are report-only now, and "
              "stay so across a restart until `daemon resume`")
        print(f"  reason: {payload['reason']}")
        return 0
    if action == "resume":
        if not daemon_module.resume(cfg):
            print("nothing was paused")
            return 0
        Store.for_config(cfg).event("daemon-resumed", "watchers and starts are active again")
        print("supervisor resumed: the next tick acts again")
        return 0
    info = daemon_module.status(cfg)
    if args.json:
        print(json.dumps(info, indent=2, default=str))
    else:
        print(f"daemon: {'running' if info['running'] else 'not running'}"
              + (f", pid {info['pid']}" if info.get("pid") else ""))
        print(f"state: {info['state_dir']}, log {info['log']}")
        if info["paused"]:
            print(f"paused: {(info['paused'] or {}).get('reason', '')}")
        unit = info["systemd"]
        print(f"systemd unit: {'installed' if unit['installed'] else 'not installed'}"
              f", {unit['active']}"
              + (f" (shipped at {unit['shipped_at']})" if unit.get("shipped_at") else ""))
        print(f"config: {info['config']}"
              + ("" if info["config_ok"] else " - refusing: " + "; ".join(info["problems"])))
    return 0 if info["running"] and info["config_ok"] else 1


def cmd_start(args):
    """Run the tick's whole path for exactly one issue the operator named.

    The gate first, then the board, then the host's capacity - the same order
    every tick keeps. What is skipped is the slot arithmetic: naming one issue
    is the operator making that decision by hand.
    """
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        return 2
    runner = Runner(cfg)
    runner.reconcile()  # the same precondition `plan --start` insists on
    scheduler = Scheduler(cfg, runner=runner)
    report = scheduler.start_one(args.issue, plan_only=args.plan)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report, plan_only=args.plan)
    if report["errors"]:
        return 2
    if report["started"] or (args.plan and report["planned"]):
        return 0
    return 1


def cmd_stop(args):
    """Stop one issue's worker and tear down the stack its lease recorded.

    The difference from `pause` is the Compose project: `pause` leaves the job's
    stack standing because a resume may want it back; `stop` takes the whole job
    down. The branch, the worktree, the claim and the logs stay either way.
    """
    cfg, runner = _runner(args)
    if runner is None:
        return 2
    lease = runner.store.lease(args.issue)
    if not lease:
        print(f"#{args.issue} has no lease here - nothing to stop", file=sys.stderr)
        return 1
    project = lease.get("project") or ""
    outcome = runner.pause(args.issue, args.reason or "stopped by an operator")
    print(f"#{args.issue} stopped"
          + (" (had to be killed)" if outcome.get("forced") else ""))
    if not project:
        print("no Compose project was recorded, so there is no stack to tear down")
        return 0
    try:
        runner.cleanup_stack(args.issue, project, volumes=not args.keep_volumes)
    except StartError as exc:
        print(f"stack {project} was NOT torn down: {exc}", file=sys.stderr)
        return 1
    print(f"{project} torn down" + ("" if not args.keep_volumes else " (volumes kept)"))
    return 0


def cmd_retry(args):
    """Forget an issue's failed attempts so the next tick may try it again."""
    cfg = _load(args)
    if not cfg.ok:
        for problem in cfg.problems:
            print(f"config: {problem}", file=sys.stderr)
        return 2
    Store.for_config(cfg).reset_attempts(args.issue)
    decision = approvals.explain(cfg, args.issue)
    print(decision.line())
    print(f"#{args.issue}: backoff cleared - the next tick will try it again"
          if decision.eligible else
          f"#{args.issue}: backoff cleared, but the gate still refuses - "
          "the reason above has to change first")
    return 0 if decision.eligible else 1


def cmd_metrics(args):
    """What the supervisor has run, waited for and cost - host numbers included."""
    from . import metrics as metrics_module
    cfg = _load(args)
    report = metrics_module.collect(cfg)
    print(metrics_module.as_json(report) if args.json else metrics_module.as_text(report))
    return 0


def cmd_doctor(args):
    """The readiness check a fresh host runs first: every precondition answered
    with what was actually found, and never with a guess.

    Failing checks are things that stop the supervisor from working at all;
    warnings are postures an operator chose but should see every time.
    """
    cfg = _load(args)
    rows = []

    def report(name, ok, detail, warn=False):
        rows.append((name, "ok" if ok else ("warn" if warn else "fail"), detail))

    report("config", cfg.ok,
           f"{cfg.path}: " + ("; ".join(cfg.problems) if cfg.problems else "usable"))
    for warning in cfg.warnings:
        rows.append(("config note", "warn", warning))
    who = gh.whoami()
    if who:
        report("gh authentication", True, f"logged in as {who}")
        if who.lower() in [str(x).lower() for x in cfg.authorized_humans]:
            rows.append(("account roles", "warn",
                         f"{who} is both reading the approvals and the account the "
                         "supervisor acts as; the gate may read an approval as "
                         "self-approval - see allow_same_account"))
    else:
        report("gh authentication", False,
               "gh cannot be asked - is it installed and `gh auth login`-ed?")
    if cfg.ok and who:
        for label in (cfg.data["approved_label"], cfg.data["paused_label"]):
            exists = False
            why = ""
            try:
                exists = gh.label_exists(cfg.repo, label)
            except gh.GhError as exc:
                why = str(exc)
            report(f"label '{label}'", exists,
                   "present" if exists else f"missing - create it with `labels --create` {why}")
    binary = cfg.data.get("opencode_command") or "opencode"
    found = shutil.which(binary)
    report("opencode binary", bool(found),
           f"{binary}: {found or 'not on PATH - workers cannot be started'}")
    try:
        probe = Store.for_config(cfg)
        probe.event("doctor", "state directory writable", issue=None)
        report("state directory", True, f"{cfg.state_dir} holds the SQLite file")
    except OSError as exc:
        report("state directory", False, f"{cfg.state_dir}: {exc}")
    from .daemon import paths as daemon_paths
    log_path = daemon_paths(cfg)["log"]
    if os.path.exists(log_path):
        mode = oct(os.stat(log_path).st_mode & 0o777)
        world = ", readable by others - 0600 is the promise" if mode[-1] != "0" else ""
        report("log file", True, f"{log_path} (mode {mode}{world})")
    else:
        report("log file", True, f"{log_path} not written yet (created on first run)")
    wip = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wip")
    report("claim board tool", os.access(wip, os.X_OK), wip)
    if cfg.repo_root:
        present = os.path.isdir(cfg.repo_root)
        report("repo_root", present,
               f"{cfg.repo_root} exists" if present else
               f"{cfg.repo_root} is missing - worktrees cannot be branched")
    from .capacity import Capacity
    verdict = Capacity(cfg).evaluate()
    report("capacity gate", verdict["verdict"] != "unknown",
           f"{verdict['verdict']}: {verdict['explanation']}", warn=True)
    from . import daemon as daemon_module
    info = daemon_module.status(cfg)
    if info["running"]:
        rows.append(("daemon", "ok", f"running, pid {info.get('pid') or '?'}"))
    else:
        rows.append(("daemon", "warn",
                     "not running - `daemon start`, or the systemd unit under "
                     f"{info['systemd']['shipped_at']}"))
    if info["paused"]:
        rows.append(("daemon", "warn", f"paused: {(info['paused'] or {}).get('reason', '')}"))
    fails = [one for one in rows if one[1] == "fail"]
    for name, state, detail in rows:
        print(f"  {state:4s} {name}: {detail}")
    print(f"{len(rows) - len(fails)} check(s) passed, {len(fails)} failing")
    return 1 if fails else 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent_supervisor",
        description="Supervises OpenCode agents on MrMap issues. The gate in front of "
                    "every one of them is 'a human put the approval label on it'.")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--config", help="path to the operator configuration "
                                         f"(default ${config_module.CONFIG_ENV} or "
                                         f"{config_module.DEFAULT_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("explain", help="why a specific issue may or may not be started")
    p.add_argument("issues", nargs="+", type=int, help="issue number")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("eligible", help="list the issues the gate would accept now")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_eligible)

    p = sub.add_parser("labels", help="check the two labels of the contract exist")
    p.add_argument("--create", action="store_true", help="create the ones that are missing")
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("config", help="print the resolved configuration and its problems")
    p.add_argument("--example", action="store_true", help="print a documented starting file")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("plan", help="one scheduler tick: what would start, and why the rest "
                                    "will not (nothing is started without --start)")
    p.add_argument("--start", action="store_true",
                   help="hand the planned jobs to the runner; until #1060 lands this "
                        "only leases them")
    p.add_argument("--json", action="store_true", help="the whole report as one JSON object")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("status", help="leases, recent decisions and events, as the state "
                                      "file holds them")
    p.add_argument("--events", type=int, default=15, help="how many events to print")
    p.add_argument("--json", action="store_true", help="leases and events as one JSON object")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("logs", help="the log one worker wrote, newest lines last")
    p.add_argument("issue", type=int)
    p.add_argument("--tail", type=int, default=40, help="how many lines to print")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("pause", help="stop one worker, keep its branch and worktree")
    p.add_argument("issue", type=int)
    p.add_argument("--reason", default="", help="what the board should say why it stopped")
    p.set_defaults(func=cmd_pause)

    p = sub.add_parser("resume", help="continue one worker on its recorded session, "
                                      "only while the gate still allows the issue")
    p.add_argument("issue", type=int)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("reconcile", help="what a crash or a reboot left behind, and what "
                                         "was done about it")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("stack-down", help="tear down the Compose stack one lease recorded, "
                                          "and only that stack")
    p.add_argument("issue", type=int)
    p.add_argument("--keep-volumes", action="store_true",
                   help="remove the containers and network but keep the volumes")
    p.set_defaults(func=cmd_stack_down)

    p = sub.add_parser("prs", help="what the CI watcher knows about the pull requests "
                                   "of this supervisor's work")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="include pull requests already closed")
    p.set_defaults(func=cmd_prs)

    p = sub.add_parser("watch-prs", help="one look at the CI of those pull requests: repair "
                                         "an actionable failure within the budget, report "
                                         "everything else to a human, never merge")
    p.add_argument("--issue", type=int, help="only the pull request of this issue")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would happen, resume and ask nobody")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_watch_prs)

    p = sub.add_parser("reviews", help="what the review watcher knows about the review "
                                       "feedback on those pull requests")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="include pull requests already closed")
    p.add_argument("--items", type=int, default=8,
                   help="how many open feedback items to list per pull request")
    p.set_defaults(func=cmd_reviews)

    p = sub.add_parser("watch-reviews", help="one look at the human review feedback on those "
                                             "pull requests: answer what a trusted reviewer "
                                             "asked for, hand reserved acts to a human, never "
                                             "approve, merge or resolve a thread")
    p.add_argument("--issue", type=int, help="only the pull request of this issue")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would happen, resume and ask nobody")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_watch_reviews)

    p = sub.add_parser("run", help="the supervisor loop: plan, follow CI, follow review "
                                   "feedback, sleep, repeat - until a TERM arrives")
    p.add_argument("--once", action="store_true",
                   help="one tick and exit; what a timer without a resident process runs")
    p.add_argument("--dry-run", action="store_true",
                   help="every stage reads and reports and nothing is written anywhere")
    p.add_argument("--json", action="store_true",
                   help="with --once: the tick report as exactly one JSON document")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("daemon", help="control the background supervisor of this state "
                                      "directory: one daemon at a time, workers survive "
                                      "every stop")
    dsub = p.add_subparsers(dest="daemon_action", required=True)
    d = dsub.add_parser("start", help="start `run` detached, for a host without systemd")
    d.set_defaults(func=cmd_daemon)
    d = dsub.add_parser("stop", help="ask the daemon to finish its tick and leave; "
                                     "running workers are left alone on purpose")
    d.add_argument("--timeout", type=float, default=120.0,
                   help="how long to wait for the current tick to finish")
    d.set_defaults(func=cmd_daemon)
    d = dsub.add_parser("pause", help="every watcher and every start becomes report-only, "
                                      "until resume - and across a restart")
    d.add_argument("--reason", default="operator paused the supervisor")
    d.set_defaults(func=cmd_daemon)
    d = dsub.add_parser("resume", help="undo daemon pause")
    d.set_defaults(func=cmd_daemon)
    d = dsub.add_parser("status", help="is it running, is it paused, is it under systemd, "
                                       "is the config usable")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_daemon)

    p = sub.add_parser("start", help="run the tick's whole path for one issue the operator "
                                     "names: gate, board, capacity, lease, runner")
    p.add_argument("issue", type=int)
    p.add_argument("--plan", action="store_true",
                   help="walk the path and lease, but start no process")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop",
                       help="stop one issue's worker and tear down the Compose stack its "
                            "lease recorded; branch, worktree, claim and logs stay")
    p.add_argument("issue", type=int)
    p.add_argument("--reason", default="", help="what the board should say why it stopped")
    p.add_argument("--keep-volumes", action="store_true",
                   help="remove the containers and network but keep the volumes")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("retry", help="forget an issue's failed attempts and backoff, so "
                                     "the next tick may try it again")
    p.add_argument("issue", type=int)
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("metrics", help="queue wait, active slots, run durations, PR CI "
                                       "findings, retries, host and OOM numbers, leftovers")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("doctor", help="the readiness check a fresh host starts with: "
                                      "config, gh, labels, OpenCode, state directory, "
                                      "capacity gate, daemon")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
