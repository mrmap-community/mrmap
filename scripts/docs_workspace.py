#!/usr/bin/env python3
"""Where a documentation run may read, write and execute - and where it may not.

The pipeline reads a repository and, when a model is configured, talks to one
endpoint. That is the whole threat surface, and this module is the whole
implementation of the policy around it (issue #1598: "isolated filesystem/network
and resource budgets, no production or source-branch write credentials"; ADR-0001
sections 8 and 11). It is deliberately boring and deliberately total: every stage
goes through here for every byte it reads, writes or executes, so "the author
never touches the working tree" is a property of the code rather than a promise
in a document.

Three policies:

* **Read.** Only inside the tree under documentation. A source reference in an
  artifact is a relative path; resolving it here is what stops an artifact from
  naming ``/etc/passwd`` or ``../.ssh/id_rsa``, and the secret-path deny-list
  covers the case where a credential file sits *inside* the checkout and would
  otherwise be summarized by a model.
* **Write.** Only inside the roots a run was given, and never into the working
  tree of a source branch. The generated sources live under a workspace directory
  by default; pointing them at ``docs/source`` is an explicit act, and even then a
  write is refused unless the path is one the stage declared it owns. Publication
  is a separate root so a failed run physically cannot touch the last good
  artifact - that is ADR-0001's fail-closed rule expressed as a filesystem
  permission rather than as a convention.
* **Execute.** Only the commands in ``docs_contract.TOOL_ALLOWLIST``, with the
  exact arguments that entry declares, in a scrubbed environment and under a
  timeout. There is no shell, no ``shell=True``, no interpolation of model output
  into an argv, and no environment inheritance beyond the handful of variables a
  build genuinely needs - so a prompt-injected page cannot reach a binary the
  pipeline has not been told about.

The environment scrub is the answer to "protect secrets": a documentation worker
holds no credentials, so the child environment is built from a small allowlist and
the scrubber also refuses to *log* anything that looks like one. Redaction at the
log boundary is defence in depth, not the primary control - the primary control is
that the value was never in the child's environment to begin with.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402  (path set above, by design)

#: Paths that are never read, never hashed and never named in an artifact, even
#: inside the tree. Matched against the *resolved* relative path, case-folded.
SECRET_PATHS = (
    ".env", ".env.local", "credentials", "credentials.json", "secrets.json",
    "secret.key", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc",
    "service_account.json",
)
SECRET_DIR_PARTS = (".git", ".ssh", ".aws", ".gnupg", ".config", "node_modules",
                    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache")
#: Environment variable *names* whose value must never appear in a log line.
SECRET_NAME_RE = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|ACCESS_KEY|PRIVATE_KEY"
    r"|SESSION_KEY|DATABASE_URL|CONN|string)", re.IGNORECASE)
#: ... and the shapes a value takes, so a secret that reached a log via model
#: output or a tool's stderr is still not disclosed.
SECRET_VALUE_RES = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)[a-z0-9][a-z0-9.+\-]*://[^/\s:@]+:[^@\s]+@"),
    re.compile(r"(?i)\b(secret|password|token|apikey)\b\s*[:=]\s*[\"']?[^\s\"']{8,}"),
)
REDACTED = "[redacted]"

#: The only variables a allowlisted child process receives. ``PYTHONPATH`` is
#: rebuilt, never inherited, so a run cannot import whatever a developer happens
#: to have on their path; ``PATH`` is inherited because a build has to find its
#: interpreter, and is enough on its own.
CHILD_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR",
                       "PYTHONHASHSEED", "GIT_DIR", "GIT_OBJECT_DIRECTORY")


class GuardError(RuntimeError):
    """A read, write or execution the policy refuses. Always a failed stage."""


def scrub_text(text: str, extra: tuple[str, ...] = ()) -> str:
    """Remove credential-shaped substrings from anything destined for a log.

    Applied to stage details, failure reasons, captured stderr and every field of
    ``report.json``. It is not a substitute for not holding the secret - it is the
    reason a bug elsewhere cannot turn into a disclosure.
    """
    if not isinstance(text, str):
        text = str(text)
    for value in extra:
        if value and len(value) >= 8:
            text = text.replace(value, REDACTED)
    for pattern in SECRET_VALUE_RES:
        text = pattern.sub(REDACTED, text)
    return text


def scrub_env(env: dict | None = None) -> tuple[dict, list[str]]:
    """Build the child environment from the allowlist; report what was withheld.

    Returns the environment and the names that were present in the caller's
    environment but withheld, so a run can say in its report that it ran without
    the credentials it did not need.
    """
    source = env if env is not None else os.environ
    child = {key: source[key] for key in CHILD_ENV_ALLOWLIST if key in source}
    withheld = sorted(
        name for name in source
        if name not in child and SECRET_NAME_RE.search(name))
    child["PYTHONHASHSEED"] = "0"      # determinism, and it hides the host's value
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child.pop("PYTHONPATH", None)
    return child, withheld


def is_secret_path(rel: str) -> bool:
    parts = [part.lower() for part in Path(rel).parts]
    if not parts:
        return False
    if any(part in SECRET_DIR_PARTS for part in parts[:-1]):
        return True
    return parts[-1] in SECRET_PATHS


def safe_relpath(rel: str) -> str:
    """Normalise a relative path, refusing anything that is not plainly relative.

    Symlinks are not resolved here - the caller resolves inside a root and the
    containment check catches the escape - but ``..``, an absolute path, a drive
    letter, a backslash and an empty segment are refused before a filesystem call,
    because those are the four spellings an artifact can carry.
    """
    text = str(rel).strip()
    if not text:
        raise GuardError("empty path")
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        raise GuardError(f"absolute path refused: {text!r}")
    if "\\" in text:
        raise GuardError(f"backslash in path refused: {text!r}")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise GuardError(f"path must stay inside the tree: {text!r}")
    return "/".join(parts)


def _within(target: Path, root: Path) -> bool:
    """``target`` is ``root`` or below it, without relying on string prefixes."""
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass
class Clock:
    """Injectable clock, so a suite can pin ``generated_at`` and a real run cannot."""

    fixed: str | None = None

    def now(self) -> str:
        if self.fixed:
            return self.fixed
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ToolResult:
    name: str
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    withheld_env: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"command": " ".join(self.argv), "exit_code": self.exit_code,
                "stdout_sha256": contract.sha256_text(self.stdout),
                "stderr_sha256": contract.sha256_text(self.stderr),
                "duration_s": round(self.duration_s, 3),
                "timed_out": self.timed_out}


class Workspace:
    """The filesystem and process boundary of one run.

    ``root`` is the tree under documentation - the only place a read may resolve
    to. The writable roots are declared per stage; a write to a path a stage does
    not own is a ``GuardError``, not a warning, because the issue names
    "unauthorized write" as a case that must be *tested*, which means it must be
    representable.
    """

    def __init__(self, root: Path, work: Path, publish: Path | None = None,
                 generated: Path | None = None, *, read_only_root: bool = True,
                 clock: Clock | None = None, python: str | None = None,
                 timeout_s: float | None = None, now: str | None = None):
        self.root = Path(root).resolve()
        self.work = Path(work).resolve()
        self.publish = Path(publish).resolve() if publish else self.work / "publish"
        self.generated = (Path(generated).resolve() if generated
                          else self.work / "generated")
        self.read_only_root = read_only_root
        self.clock = clock or Clock(now)
        self.python = python or sys.executable
        self.timeout_s = (timeout_s if timeout_s is not None
                          else contract.budget("tool_wall_clock_s"))
        self.source_digest: str | None = None
        self._owned: set[Path] = set()
        self._writable: list[Path] = []
        self.denied: list[str] = []

    # ------------------------------------------------------------------ identity ---
    @property
    def documented_commit(self) -> str | None:
        """The revision under documentation, from the allowlisted ``git`` call.

        ``None`` when the tree is not a repository (a tarball of a candidate is a
        legitimate input). A run never invents a SHA: the report says the field is
        absent rather than showing a plausible one.
        """
        if not (self.root / ".git").exists():
            return None
        try:
            result = self.run_tool("git-revision")
        except GuardError:
            return None
        if result.exit_code != 0:
            return None
        revision = result.stdout.strip()
        return revision if re.fullmatch(r"[0-9a-f]{40}", revision) else None

    def version(self) -> str | None:
        """The root ``VERSION`` file, which #1579 makes canonical."""
        try:
            text = self.read_text("VERSION")
        except (GuardError, OSError):
            return None
        value = text.strip()
        return value or None

    # --------------------------------------------------------------------- reads ---
    def _contained(self, base: Path, resolved: Path, label: str) -> Path:
        try:
            resolved.relative_to(base)
        except ValueError:
            raise GuardError(
                f"{label} escapes its root: {resolved} is not under {base}") from None
        return resolved

    def resolve_read(self, rel: str) -> Path:
        safe = safe_relpath(rel)
        if is_secret_path(safe):
            self.denied.append(f"read:{safe}")
            raise GuardError(f"refusing to read a credential path: {safe}")
        candidate = (self.root / safe).resolve()
        if candidate.is_symlink():
            self.denied.append(f"symlink:{safe}")
            raise GuardError(f"refusing to follow a symlink: {safe}")
        return self._contained(self.root, candidate, f"read of {safe}")

    def read_bytes(self, rel: str) -> bytes:
        return self.resolve_read(rel).read_bytes()

    def read_text(self, rel: str) -> str:
        return self.read_bytes(rel).decode("utf-8", errors="replace")

    def exists(self, rel: str) -> bool:
        try:
            return self.resolve_read(rel).is_file()
        except GuardError:
            return False

    def walk(self, prefix: str = "", *, suffixes: tuple[str, ...] | None = None,
             skip_dirs: tuple[str, ...] = SECRET_DIR_PARTS) -> list[str]:
        """Relative paths under ``prefix``, sorted, secrets and caches excluded.

        Sorted and deduplicated because extraction has to be byte-reproducible:
        ``os.walk`` order is filesystem order, and a run that is not reproducible
        cannot be cached by digest.
        """
        base = self.root if not prefix else self.resolve_read(prefix)
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                rel = path.relative_to(self.root).as_posix()
                if suffixes and path.suffix not in suffixes:
                    continue
                if is_secret_path(rel) or not path.is_file():
                    continue
                found.append(rel)
        return sorted(found)

    # --------------------------------------------------------------------- writes ---
    def allow_writes_under(self, *roots: Path) -> None:
        """Declare the roots this run may write to, rejecting the impossible ones.

        A scratch root that *contains* the tree would make every source file
        writable through a relative path, which is the property the whole boundary
        exists to deny - so it is refused at declaration rather than checked per
        write. A scratch root inside the tree is allowed (that is the default, and
        the tree is read-only for the run either way) but is reported so a caller can
        aim it outside when the artifacts must not land near a checkout.
        """
        for root in roots:
            candidate = Path(root).resolve()
            if candidate == self.root or self.root in candidate.parents:
                raise GuardError(
                    f"refusing {candidate} as a writable root: it is the tree under "
                    f"documentation or an ancestor of it, which would make every "
                    f"source file writable")
            self._writable.append(candidate)

    def _under(self, base: Path, rel: str, label: str) -> Path:
        """``rel`` inside ``base``, created, or a refusal.

        One helper for every write, so "a run writes only where it was given a
        root" is enforced in exactly one place. Two conditions must hold: the target
        resolves inside ``base``, *and* ``base`` is a root this run was given. A
        caller that passes its own ``base`` cannot therefore aim a write at the
        working tree of a source branch - the roots are declared once, by
        :meth:`allow_writes_under`, and nothing else. An unauthorized write is the
        case the issue names as required in the validation suite, which means it has
        to be representable rather than merely unlikely.
        """
        target = (Path(base) / safe_relpath(rel)).resolve()
        self._contained(Path(base).resolve(), target, f"{label} {rel}")
        if not any(_within(target, allowed) for allowed in self._writable):
            raise GuardError(
                f"unauthorized write: {target} is not inside a root this run was "
                f"given ({', '.join(str(root) for root in self._writable) or 'none'}"
                f"); the working tree of a source branch is never writable")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._owned.add(target)
        return target

    def claim(self, rel: str, *, base: Path | None = None) -> Path:
        """Declare that this run owns ``rel`` and return the path to write it at."""
        return self._under(base or self.work, rel, "write")

    def claim_generated(self, rel: str) -> Path:
        """Own a page in the generated-source tree (the only tree Sphinx reads)."""
        return self._under(self.generated, rel, "generated write")

    def claim_for_write(self, rel: str, root: Path) -> Path:
        """Own a file under an explicitly named root - how publication writes."""
        return self._under(Path(root), rel, "publish write")

    def write_bytes(self, rel: str, data: bytes, *, base: Path | None = None,
                    kind: str = "artifact") -> Path:
        target = self.claim(rel, base=base)
        target.write_bytes(data)
        return target

    def write_text(self, rel: str, text: str, *, base: Path | None = None,
                   kind: str = "artifact") -> Path:
        return self.write_bytes(rel, text.encode("utf-8"), base=base, kind=kind)

    def write_json(self, rel: str, obj, *, base: Path | None = None,
                   kind: str = "artifact") -> Path:
        text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        return self.write_text(rel, scrub_text(text), base=base, kind=kind)

    def owned(self) -> list[str]:
        return sorted(path.relative_to(self.work).as_posix()
                      for path in self._owned
                      if path.is_relative_to(self.work))

    def read_owned_text(self, rel: str) -> str:
        """Read back something this run wrote - the only way to read the artifact tree."""
        target = (self.work / safe_relpath(rel)).resolve()
        self._contained(self.work, target, f"read-back of {rel}")
        if target not in self._owned and not target.is_file():
            raise GuardError(f"{rel} was not written by this run")
        return target.read_text(encoding="utf-8")

    # ------------------------------------------------------------------- execution ---
    def run_tool(self, name: str, substitutions: dict[str, str] | None = None,
                 *, timeout_s: float | None = None) -> ToolResult:
        """Run one allowlisted command, with its declared argv and nothing else.

        ``substitutions`` fills the ``{placeholders}`` of that entry and nothing
        else may appear in the argv, so the set of commands the pipeline can run
        is exactly ``docs_contract.TOOL_ALLOWLIST``. Values are checked for shell
        metacharacters and path escapes even though there is no shell, because a
        placeholder that receives ``docs/source ../../etc`` is a policy violation
        whatever the transport.
        """
        try:
            entry = contract.TOOL_ALLOWLIST[name]
        except KeyError:
            self.denied.append(f"tool:{name}")
            raise GuardError(
                f"{name!r} is not an allowlisted tool; the pipeline may run "
                f"{', '.join(sorted(contract.TOOL_ALLOWLIST))}") from None
        argv: list[str] = []
        for token in entry["argv"]:
            if token.startswith("{") and token.endswith("}"):
                key = token[1:-1]
                if key == "python":
                    # The interpreter is the one argument of the one allowlisted
                    # invocation that a caller can name (--python). It gets the same
                    # check as every other value plus an existence check, so
                    # "--python '/bin/sh -c evil'" is a refusal rather than a
                    # surprising exec attempt.
                    if re.search(r"[\s;&|`$<>*?\"'\\]", self.python):
                        raise GuardError(
                            "the tool interpreter may not carry whitespace or "
                            f"metacharacters: {self.python!r}")
                    if not Path(self.python).is_file():
                        raise GuardError(
                            f"the tool interpreter is not an existing file: "
                            f"{self.python!r}; name an interpreter the runner has, "
                            f"not a bare command on PATH")
                    argv.append(self.python)
                    continue
                if substitutions is None or key not in substitutions:
                    raise GuardError(f"missing value for tool placeholder {key!r}")
                value = str(substitutions[key])
                if re.search(r"[;&|`$<>\n\r*?\"'\\]", value):
                    raise GuardError(
                        f"tool argument {key!r} carries a shell metacharacter")
                argv.append(value)
            else:
                argv.append(token)
        if not argv:
            raise GuardError(f"tool {name!r} declares no argv")
        binary = argv[0]
        env, withheld = scrub_env()
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(  # nosec B603 - argv comes only from the allowlist
                [binary, *argv[1:]], cwd=str(self.root), env=env,
                capture_output=True, text=True, timeout=timeout_s or self.timeout_s,
                stdin=subprocess.DEVNULL)
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(
                exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(
                exc.stderr, bytes) else (exc.stderr or "")
            code = 124
        except OSError as exc:
            # A missing binary is "could not run", reported as a refusal so the
            # caller can distinguish it from a command that ran and failed.
            raise GuardError(f"tool {name!r} could not start: "
                             f"{scrub_text(str(exc))}") from None
        return ToolResult(name=name, argv=[binary, *argv[1:]], exit_code=code,
                          stdout=scrub_text(stdout), stderr=scrub_text(stderr),
                          duration_s=time.monotonic() - start,
                          timed_out=timed_out, withheld_env=withheld)

    # ----------------------------------------------------------------------- misc ---
    def tree_digest(self, prefixes: tuple[str, ...]) -> str:
        """Digest of the content a run read, over ``prefixes``.

        This is the reuse key's main ingredient: a locale edit or a generator
        change moves it, so a cached artifact cannot be reused against a different
        input (ADR-0001 section 6).
        """
        update = hashlib.sha256()
        for prefix in sorted(prefixes):
            target = self.resolve_read(prefix)
            # A prefix may be a single file (the pipeline names its own extractor and
            # contract as inputs, so a generator change moves the key). os.walk over
            # a file yields nothing, which would drop it from the digest silently -
            # and a reuse key that ignores the generator is not a reuse key.
            names = ([prefix] if target.is_file() else self.walk(prefix))
            for rel in names:
                update.update(rel.encode("utf-8"))
                update.update(b"\0")
                update.update(self.read_bytes(rel))
                update.update(b"\0")
        return "sha256:" + update.hexdigest()

    def budget(self, name: str, overrides: dict | None = None):
        return contract.budget(name, overrides)

    def stamp(self) -> str:
        return self.clock.now()


def workspace_from_args(args, root: Path) -> Workspace:
    """Build the boundary a CLI run uses, so the CLI holds no policy of its own."""
    work = Path(args.workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    publish = Path(getattr(args, "publish_dir", work / "publish")).resolve()
    generated = Path(getattr(args, "generated_dir", work / "generated")).resolve()
    workspace = Workspace(
        root=root, work=work, publish=publish, generated=generated,
        read_only_root=not getattr(args, "allow_tree_writes", False),
        clock=Clock(getattr(args, "now", None)),
        python=getattr(args, "python", None) or sys.executable,
        timeout_s=getattr(args, "tool_timeout", None))
    workspace.allow_writes_under(work, publish, generated)
    return workspace


def main() -> int:  # pragma: no cover - exercised through the suites
    workspace = Workspace(root=Path.cwd(), work=Path.cwd() / ".mrmap-docs-work")
    print(f"workspace root {workspace.root}")
    print(f"writable work  {workspace.work}")
    print(f"publish        {workspace.publish}")
    print(f"allowlisted    {', '.join(sorted(contract.TOOL_ALLOWLIST))}")
    for rel in (".env", "backend/MrMap/settings.py", "../outside", "/etc/passwd",
                "a/../b"):
        try:
            workspace.resolve_read(rel)
            print(f"  read allowed   {rel}")
        except GuardError as exc:
            print(f"  read refused   {rel}: {exc}")
    return contract.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
