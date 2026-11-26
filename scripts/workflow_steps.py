#!/usr/bin/env python3
"""Read the parts of a GitHub Actions workflow that the release suites execute.

PyYAML is not a stdlib dependency and no CI runner has it, so a suite that
needs a workflow's step scripts cannot import a parser (the same reading
`scripts/test_dev_image_gate.py` records for dev-images.yml). The promotion
workflow of #1798 IS the implementation, so its shell is what the tests run -
which means reading it well enough to be exact about a `run: |` body, the one
place a line-based regex silently loses half a script.

Scope, stated so nothing is trusted further than it goes: this reads the
indentation-mapping subset Actions files of this repository use - nested
mappings, `- ` step lists, block scalars and plain scalars - and raises rather
than guessing at anything else (flow collections, anchors, folded `run:`).
The two consumers assert exact key sets, so a reader that over- or
under-collects goes red there rather than here.

Run `python3 scripts/workflow_steps.py` to print what it reads from the
promotion workflow.
"""
import sys
from pathlib import Path

PROMOTION_WORKFLOW = (Path(__file__).resolve().parent.parent
                      / ".github" / "workflows" / "release-promotion.yml")


class WorkflowReadingError(Exception):
    """The file is not shaped the way these helpers read it."""


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def region(lines, key, indent):
    """The lines belonging to `key:` written at column `indent`.

    The region ends at the first non-blank line at or left of that column, so
    passing a sub-region scopes the search: two `inputs:` keys of two triggers
    never answer each other.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()
    want = " " * indent + key + ":"
    for i, line in enumerate(lines):
        if line.rstrip() == want:
            break
    else:
        raise WorkflowReadingError(f"no {key!r} at column {indent}")
    out = []
    for line in lines[i + 1:]:
        if line.strip() and _indent(line) <= indent:
            break
        out.append(line)
    return out


def keys(lines, indent):
    """The mapping keys written at exactly `indent`, comments excluded."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _indent(line) != indent or stripped.startswith(("#", "-")):
            continue
        if ":" not in stripped:
            continue
        out.append(stripped.split(":", 1)[0].strip())
    return out


def scalar(lines, key, indent):
    """The scalar written after `key:` at column `indent`, unquoted."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    block = False
    for line in lines:
        if not line.strip() or _indent(line) != indent:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith(key + ":"):
            continue
        value = stripped[len(key) + 1:].strip()
        if value:
            return _unquote(value)
        block = True
    if block:
        raise WorkflowReadingError(f"{key!r} at column {indent} is a block, "
                                   f"not a scalar; read it with region()")
    raise WorkflowReadingError(f"no {key!r} at column {indent}")


def job_block(text, job):
    """The text of one job under `jobs:`.

    The region ends at the first non-blank line left of the job's body, which
    is also where a job's own indented comments stop and the file's
    between-job explanations begin - those are written at column 0.
    """
    lines = text.splitlines()
    try:
        where = region(lines, "jobs", 0)
    except WorkflowReadingError:
        raise WorkflowReadingError("the workflow has no jobs: block")
    start = None
    want = "  " + job + ":"
    for i, line in enumerate(where):
        if line.rstrip() == want:
            start = i
            break
    if start is None:
        raise WorkflowReadingError(f"no job {job!r}")
    body = []
    for line in where[start + 1:]:
        if line.strip() and _indent(line) < 4:
            break
        body.append(line)
    return "\n".join(body)


def step_scripts(text, job):
    """`[(step name, script)]` for the `run:` steps of one job, in file order.

    A `run: |` body is every following line indented deeper than the `run:`
    key, kept verbatim: the `#` lines inside it are content, not comments to
    strip - these steps name in their comments the very commands they forbid,
    and stripping them would edit the script the runner executes.
    """
    body = job_block(text, job).splitlines()
    out = []
    name = None
    i = 0
    while i < len(body):
        stripped = body[i].strip()
        if stripped.startswith("- name:"):
            name = _unquote(stripped[len("- name:"):])
        elif stripped.startswith("name:") and _indent(body[i]) >= 6:
            name = _unquote(stripped[len("name:"):])
        elif stripped.startswith("run:"):
            indicator = stripped[len("run:"):].strip()
            if indicator not in ("|", "|-", "|+"):
                raise WorkflowReadingError(
                    f"step {name!r} of job {job!r} writes its run as "
                    f"{indicator!r}; these helpers read only the literal block "
                    "scalar, because a folded or inline one is not what the "
                    "release steps use")
            indent = _indent(body[i])
            block = []
            i += 1
            while i < len(body):
                line = body[i]
                if line.strip() and _indent(line) <= indent:
                    break
                block.append(line)
                i += 1
            while block and not block[0].strip():
                block.pop(0)
            while block and not block[-1].strip():
                block.pop()
            if not block:
                raise WorkflowReadingError(f"step {name!r} of job {job!r} has an "
                                           "empty run block")
            depth = min(_indent(line) for line in block if line.strip())
            # One trailing newline, the way a `|` block scalar is clipped: what
            # bash receives from Actions ends in a newline, and these scripts
            # are run verbatim.
            script = "\n".join(line[depth:] if line.strip() else ""
                               for line in block)
            out.append((name, script + "\n"))
            continue
        i += 1
    if not out:
        raise WorkflowReadingError(f"job {job!r} has no run: step to read")
    return out


def step_script(text, job, step_name):
    """The script of one named step; absent, an error rather than a silent None."""
    for name, script in step_scripts(text, job):
        if name == step_name:
            return script
    found = [name for name, _ in step_scripts(text, job)]
    raise WorkflowReadingError(f"job {job!r} has no step named {step_name!r} "
                               f"(it has {found})")


def scripts_of(text, job):
    """Every script of a job joined, for the checks about what a job never does."""
    return "\n".join(script for _, script in step_scripts(text, job))


def main():
    text = PROMOTION_WORKFLOW.read_text(encoding="utf-8")
    triggers = region(text, "on", 0)
    print("triggers:", keys(triggers, 2))
    print("concurrency:", scalar(region(text, "concurrency", 0), "group", 2),
          "/", scalar(region(text, "concurrency", 0), "cancel-in-progress", 2))
    for job in keys(region(text, "jobs", 0), 2):
        block = job_block(text, job)
        steps = step_scripts(text, job)
        lines = sum(len(script.splitlines()) for _, script in steps)
        needs = scalar(block, "needs", 4) if "needs:" in block else "-"
        env = (scalar(block, "environment", 4)
               if "environment:" in block else "-")
        print(f"job {job}: steps={[name for name, _ in steps]} lines={lines} "
              f"needs={needs} environment={env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
