"""The operator's command line, part 1: asking the gate.

Everything a human needs to check the authorization contract without reading
code: what the configuration says, whether the labels exist, and - the one that
matters - why a specific issue may or may not be started. The gate is a
black box only from the outside; `explain` is what makes it inspectable, and it
is the same code path the scheduler will use in #1059, so an answer here is the
answer there.

Exit codes are for scripts: 0 means "yes" (every issue asked about is eligible,
or at least one is when listing), 1 means "no", 2 means the question could not
be asked at all (no gh, unusable configuration). The daemon commands arrive with
#1063; this file grows rather than forks.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from . import VERSION
from . import approvals
from . import config as config_module
from . import gh
from .scheduler import Scheduler
from .runner import Runner, StartError
from .store import human_age


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
    if needs_human:
        print(f"pull requests waiting for a human: "
              f"{', '.join('#%d' % issue for issue in needs_human)}")
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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
