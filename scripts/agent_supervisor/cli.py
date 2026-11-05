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
    scheduler = Scheduler(cfg)
    report = scheduler.tick(plan_only=not args.start)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report, plan_only=not args.start)
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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
