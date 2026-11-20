#!/usr/bin/env python3
"""Offline checks for scripts/release_lifecycle.json (issue #1585, epic #1577).

The JSON file is the machine-readable description of the release lifecycle:
the documentation automation (#1604) generates the operator prose from it and
the interface tests (#1586) consume it. A generated page is only as honest as
its source, so this suite binds every fact in the file to the committed
reality it names - the workflows, the scripts, the Sphinx configuration, the
runbook page - and fails the moment description and tooling drift apart.

Runs without docker, without network and without a GitHub token: every check
reads repository files, one parses the tag-selection regex out of
docs/source/conf.py and exercises it against sample refs, and the git check
inspects committed refs through the git CLI the same way the migration-graph
suite does.

Run from the repository root: `python3 scripts/test_release_lifecycle.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIFECYCLE_PATH = ROOT / "scripts" / "release_lifecycle.json"
CONF = ROOT / "docs" / "source" / "conf.py"
RUNBOOK = ROOT / "docs" / "source" / "administration" / "release-operator-runbook.rst"
PROMOTION_WORKFLOW = ROOT / ".github" / "workflows" / "release-promotion.yml"

failures = []


def check(name, ok, detail=""):
    if not ok:
        failures.append(f"{name}: {detail}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail and not ok else ""))


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"<unreadable: {exc}>"


def doc_labels():
    labels = set()
    for rst in (ROOT / "docs" / "source").rglob("*.rst"):
        labels.update(re.findall(r"^\.\. _([\w-]+):\s*$", read(rst), re.MULTILINE))
    return labels


def argparse_subcommands(path):
    return set(re.findall(r'add_parser\("([\w-]+)"', read(path)))


def git_ref_exists(ref):
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode == 0


def main():
    print("release_lifecycle.json holds against the committed tooling")
    raw = read(LIFECYCLE_PATH)
    try:
        life = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL  the lifecycle file parses - {exc}")
        return 1
    check("the lifecycle file parses", True)

    # --- the canonical version -------------------------------------------------
    version_file = ROOT / life["version_file"]
    version = read(version_file).strip()
    check("VERSION exists and matches version_pattern",
          version_file.is_file() and re.match(life["version_pattern"], version),
          f"VERSION={version!r} pattern={life['version_pattern']}")

    # --- every named file and tool exists --------------------------------------
    named = set()
    for phase in life["phases"]:
        for token in re.findall(r"[\w./-]+\.(?:yml|py|md|json|rst)", phase["evidence"]):
            named.add(token)
    named.add(life["operator_runbook"]["page"])
    named.add("scripts/image_release.py")
    dev_images = life["channels"]["development"]["images"]["published_by"]
    named.add(dev_images)
    for rel in sorted(named):
        check(f"named file exists: {rel}", (ROOT / rel).is_file())

    # --- the promotion workflow is what the phases claim -----------------------
    wf = read(PROMOTION_WORKFLOW)
    promote = next(p for p in life["phases"] if p["id"] == "promote")
    check("the dispatch runs behind the declared environment",
          re.search(rf"environment: {re.escape(promote['environment'])}\b", wf),
          promote["environment"])
    options = re.search(r"options: \[([^\]]*)\]", wf)
    wf_modes = [m.strip() for m in options.group(1).split(",")] if options else []
    check("dispatch_modes are exactly the workflow's choices",
          set(wf_modes) == set(promote["dispatch_modes"]),
          f"workflow={wf_modes} json={promote['dispatch_modes']}")
    tool_subs = argparse_subcommands(ROOT / "scripts" / "release_promotion.py")
    check("every dispatch mode is a real subcommand of the tool",
          set(promote["dispatch_modes"]) <= tool_subs,
          f"tool knows {sorted(tool_subs)}")

    # --- image promotion is by digest through the committed tool ---------------
    check("image_release.py really carries the --promote path",
          '--promote' in read(ROOT / "scripts" / "image_release.py"))

    # --- the documentation version selection lives in conf.py ------------------
    docs_sel = life["channels"]["stable"]["documentation_versions"]
    conf = read(CONF)
    conf_tags = re.search(r"^smv_tag_whitelist = r'([^']*)'", conf, re.MULTILINE)
    conf_branches = re.search(r"^smv_branch_whitelist = r'([^']*)'", conf, re.MULTILINE)
    check("conf.py smv_tag_whitelist equals the described one",
          conf_tags and conf_tags.group(1) == docs_sel["tag_whitelist"],
          f"conf={conf_tags and conf_tags.group(1)!r}")
    check("conf.py smv_branch_whitelist equals the described one",
          conf_branches and conf_branches.group(1) == docs_sel["branch_whitelist"],
          conf_branches and conf_branches.group(1))

    tag_re = re.compile(docs_sel["tag_whitelist"])
    for ref, documented in [
        ("v0.2", True),        # historical two-component names stay documented
        ("v0.2.0", True),     # what promotion tags today
        ("v10.20.30", True),
        ("v0.2.0-rc.1", False),  # prereleases have no published documentation
        ("latest", False),
        ("develop", False),
        ("v0.2.0.1", False),
    ]:
        check(f"documentation selection on {ref} is {'included' if documented else 'excluded'}",
              bool(tag_re.match(ref)) == documented)

    rel_re = re.compile(life["tag_pattern"])
    check("every release tag pattern match is also documented",
          all(tag_re.match(t) for t in ("v0.2.0", "v1.2.3", "v10.0.1")))
    check("the historical two-component name is the deliberate wider exception",
          tag_re.match("v0.2") and not rel_re.match("v0.2"))

    # --- phases -----------------------------------------------------------------
    allowed_actors = {"contributor", "human", "ci"}
    labels = doc_labels()
    check("phases cover the six documented lifecycle stages",
          [p["id"] for p in life["phases"]] ==
          ["pre-release", "cut", "build-and-gate", "promote",
           "verify-on-master", "post-release"],
          str([p["id"] for p in life["phases"]]))
    for phase in life["phases"]:
        check(f"phase {phase['id']} has a permitted actor",
              phase["actor"] in allowed_actors, phase["actor"])
        if "docs" in phase:
            check(f"phase {phase['id']} links a label that exists",
                  phase["docs"] in labels, phase["docs"])
    humans = {p["id"] for p in life["phases"] if p["actor"] == "human"}
    check("humans hold the cut, the promotion dispatch and the post-release",
          {"cut", "promote", "post-release"} == humans, str(sorted(humans)))

    # --- the runbook page is the documented one ----------------------------------
    book = life["operator_runbook"]
    book_text = read(ROOT / book["page"])
    check("the runbook carries its declared label",
          f".. _{book['label']}:" in book_text, book["label"])
    for section in book["sections"]:
        check(f"runbook section exists: {section}",
              re.search(rf"^{re.escape(section)}\n=+\n", book_text, re.MULTILINE))

    # --- constraints hold against the platform state ------------------------------
    check("release-please owns the changelog (config and manifest committed)",
          (ROOT / "release-please-config.json").is_file()
          and (ROOT / ".release-please-manifest.json").is_file())
    check("the branch model exists: origin/develop and origin/master",
          git_ref_exists("origin/develop") and git_ref_exists("origin/master"))
    check("the described channel branches match the branch model",
          life["channels"]["development"]["branch"] == "develop"
          and life["channels"]["stable"]["branch"] == "master")

    print(f"\n{len(failures)} failed of the checks above" if failures
          else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
