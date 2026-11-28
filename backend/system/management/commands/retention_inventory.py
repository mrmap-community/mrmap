"""Report what the deployment persists and how fast it grows (#1498).

The operator-facing half of the V1 retention inventory. The declarations — which
dataset grows, who owns it, what holds it, which decision gates it — live in
``system/retention_datasets.py`` and are reviewed as content; what PostgreSQL and
the filesystem actually hold is measured by ``system/retention_inventory.py`` on
every run. This command only puts one on top of the other and prints it.

It **reads and never changes anything**: every statement runs inside one
``READ ONLY``, ``REPEATABLE READ`` transaction, so a write would fail instead of
happening, and nothing here deletes a row, removes a file, drops a cache key or
dispatches a task. That is a hard rule of #1498 ("reproducible read-only
commands; no production mutation"), and it is why the command has no
``--confirm``, no ``--dry-run`` and no ``--force``: there is no second mode.

Read this output before writing any retention policy (#1499 and the domain
issues), and read the reasons as carefully as the numbers. A dash is a measured
absence of knowledge, never a zero: the report says which of the two it is, and
``provenance.not_measured`` names what no run of this command can tell you.
"""

from django.core.management.base import BaseCommand, CommandError

from system import retention_inventory
from system.retention_datasets import DECLARATION_VERSION, gated_datasets


class Command(BaseCommand):
    help = ("Report the persistent data of this deployment and its measured "
            "growth: every table of an inventoried app, every declared media "
            "prefix, the caches, the disk and the open decisions which gate a "
            "retention policy (#1498). Reads only — it never deletes, vacuums, "
            "flushes or dispatches anything.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--format", choices=("text", "json"), default="text",
            help="text for a human reading the terminal, json for a ticket, a "
                 "file or a diff between two runs (default: text)")
        parser.add_argument(
            "--output", metavar="PATH", default=None,
            help="write the report to this path instead of stdout; the command "
                 "creates or replaces only this one file")
        parser.add_argument(
            "--window-days", type=int,
            default=retention_inventory.MEASUREMENT_WINDOW_DAYS,
            metavar="DAYS",
            help="how far back the growth rate is measured (default: "
                 f"{retention_inventory.MEASUREMENT_WINDOW_DAYS}); the window "
                 "travels with every rate it produces")
        parser.add_argument(
            "--horizon-days", type=int,
            default=retention_inventory.HORIZON_DAYS, metavar="DAYS",
            help="how far the measured rate is projected for the risk ranking "
                 f"(default: {retention_inventory.HORIZON_DAYS})")
        parser.add_argument(
            "--table", action="append", dest="tables", metavar="TABLE",
            help="measure only this physical table (repeatable); narrows the "
                 "database half and fails loudly for an unknown name rather "
                 "than answering with an empty report")
        parser.add_argument(
            "--dataset", action="append", dest="datasets", metavar="ID",
            help="measure only this declared dataset and the tables of its "
                 "family (repeatable); see the report's dataset ids")
        parser.add_argument(
            "--wal", action="store_true",
            help="also read pg_wal_bytes(); it needs superuser or "
                 "pg_read_all_stats and reports the reason rather than zero "
                 "when the role has neither")
        parser.add_argument(
            "--no-media", action="store_true",
            help="skip the walk of the media storage and the log directory; "
                 "useful on a host which does not mount them, where every "
                 "source would otherwise report a reason")

    def handle(self, *args, **options):
        if options["window_days"] < 1:
            raise CommandError("--window-days must be at least 1")
        if options["horizon_days"] < 1:
            raise CommandError("--horizon-days must be at least 1")
        try:
            report = retention_inventory.build_inventory(
                window_days=options["window_days"],
                horizon_days=options["horizon_days"],
                tables=options["tables"],
                datasets=options["datasets"],
                with_wal=options["wal"],
                include_media=not options["no_media"])
        except retention_inventory.RetentionInventoryError as error:
            raise CommandError(str(error))
        text = retention_inventory.format_report(report, options["format"])
        if options["output"]:
            self._write(options["output"], text)
        else:
            self.stdout.write(text)
        self._note_gates(options)

    def _write(self, path, text):
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.write("\n")
        except OSError as error:
            raise CommandError(f"cannot write {path}: {error}")
        self.stdout.write(self.style.SUCCESS(
            f"wrote {path} (declaration v{DECLARATION_VERSION})"))

    def _note_gates(self, options):
        """Say the one thing an operator must not miss while reaching for a sweep.

        A report of large growing tables invites the next command to be a
        deletion, so the gates are printed after the report rather than buried
        inside it: that is the moment the decision gets made (#1497 — unresolved
        decisions stay explicitly gated, and a new destructive policy is disabled
        until an operator opts in).
        """
        if options["format"] == "json" or options["output"]:
            return
        gates = gated_datasets()
        if not gates:
            return
        self.stderr.write(self.style.WARNING(
            f"{len(gates)} dataset(s) are gated behind an unresolved decision; "
            f"no retention policy for them may be enabled, or shipped "
            f"preview-only, until it is answered. See --format json's "
            f"'gates'. Nothing this command printed deleted anything."))
