"""The claim board, reused instead of reimplemented.

`scripts/wip` already owns the question "who is working on this issue": one
comment per issue per client, the `status: wip` label and the board issue #917.
The supervisor is one more client in that system, not a parallel one - so this
module *reads through* wip's own parsing rather than guessing at the comment
format, and it writes with wip's own commands run in the worker's worktree.

Two consequences worth stating, because they are the reason the code looks
indirection-heavy:

*The supervisor never writes a claim from its own process.* A claim comment is
keyed by the client tag, which wip derives from the checkout it was run in
(`<host>:<directory>`). Run from the repository root the supervisor would be
`<host>:mrmap`; the worker in `…/mrmap-1042` is `<host>:mrmap-1042`. If the
supervisor claimed from its own directory and the worker later refreshed its
claim, the issue would carry two claim comments - which is exactly the duplicate
scheduling the board exists to prevent. So the scheduler only *reads* claims,
and the claim itself is one of the first things the runner does inside the
worktree it just created (#1060).

*A claim held by anybody else is enough.* The supervisor does not care whether
the holder is a human in VS Code, a Codex session or another host's supervisor:
fresh claim, no start. Stale claims are not stolen here - `wip claim` already
has the deliberate `--force` for that, and a daemon should not be the one using
it.
"""

import importlib.machinery
import importlib.util
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(_HERE)
WIP_PATH = os.environ.get("MRMAP_WIP_SCRIPT") or os.path.join(SCRIPTS_DIR, "wip")


def load_wip(path=None):
    """Import `scripts/wip` as a module. It has no .py suffix, so it has to come
    in through a loader - the same way scripts/test_wip_board_sync.py does."""
    path = path or WIP_PATH
    spec = importlib.util.spec_from_loader(
        "wip", importlib.machinery.SourceFileLoader("wip", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Claims:
    """Reads the board through wip, writes through wip's own command."""

    def __init__(self, cfg, wip=None):
        self.cfg = cfg
        self._wip = wip

    @property
    def wip(self):
        if self._wip is None:
            self._wip = load_wip()
        return self._wip

    def claims_on(self, numbers):
        """{issue: [claim payloads]} - every live claim comment, whoever holds it."""
        numbers = [int(n) for n in numbers]
        if not numbers:
            return {}
        return self.wip.claims_index(self.cfg.repo, numbers)

    def holders(self, payloads):
        """The clients with a live claim on one issue, as wip reads them.

        A payload list is what `claims_on` returns: (comment id, payload) pairs.
        `active_claims` unwraps them to the claim dicts, so the holders are read
        from there - and a claim whose heartbeat went stale is reported
        separately, because the board's own rule is that a stale claim warns
        rather than blocks.
        """
        try:
            active = self.wip.active_claims(payloads or [])
        except Exception:              # a malformed board comment is not our fault
            return [], []
        fresh, stale = [], []
        for payload in active:
            holder = payload.get("client", "?")
            try:
                (stale if self.wip.is_stale(payload) else fresh).append(holder)
            except Exception:
                fresh.append(holder)
        return fresh, stale

    def blocked_by_other(self, payloads, our_client=None):
        """True when somebody other than `our_client` holds a fresh claim.

        Fails open on a board we cannot read, on purpose, and says so: this is
        not the security gate, it is the politeness layer, and the authoritative
        protection against two workers on one issue is the claim the runner
        itself files before it edits a single file (wip refuses a foreign fresh
        claim there and the worker then stops). Refusing to start anything
        because `gh` is offline would take the supervisor down with a GitHub
        incident, which is a worse failure than one extra attempt that the claim
        gate then refuses anyway.
        """
        if payloads is None:
            return False
        fresh, _stale = self.holders(payloads)
        return any(holder != our_client for holder in fresh)

    def stale_claims(self, payloads):
        """Claims that are held but whose heartbeat went stale - for the tick
        report, so an operator sees why an eligible issue waited."""
        if payloads is None:
            return []
        return self.holders(payloads)[1]

    def our_client_tag(self, worktree):
        """What wip will call a worker started in this worktree, so a status
        line can tell our own claim from somebody else's."""
        try:
            return self.wip.client_id(worktree)
        except Exception:
            return os.path.basename(os.path.abspath(worktree))

    def claim(self, worktree, issue, reason=""):
        """File the claim the way a human-run agent would: wip, in the worktree.

        Returns (ok, output). The runner treats a refusal here as "not mine to
        work on" and stops without touching a file - which is also the answer to
        a second supervisor process or host reaching the same issue first.
        """
        return self._run_wip(worktree, ["claim", str(issue)]
                             + (["--reason", reason] if reason else []))

    def wait(self, worktree, reason):
        return self._run_wip(worktree, ["wait", reason])

    def done(self, worktree, reason=""):
        return self._run_wip(worktree, ["done"] + (["--reason", reason] if reason else []))

    def heartbeat(self, worktree, issue):
        return self._run_wip(worktree, ["claim", str(issue)])

    def _run_wip(self, worktree, args):
        cmd = [self.wip.__file__] + list(args)
        try:
            proc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"cannot run scripts/wip in {worktree}: {exc}"
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out
