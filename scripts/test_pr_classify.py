#!/usr/bin/env python3
"""Offline checks for scripts/pr_classify (issue #1580).

Runs without docker, without network and without `gh`: every title rule, every merge
shape and the whole history traversal are exercised on in-memory commit records, and
the traversal is run end to end once against a throw-away git repository in a temporary
directory, with real merge commits, so what is under test includes the parentage the
folding depends on rather than only a hand-drawn picture of it.

The checks are grouped by the acceptance of #1580, because that is the list a reviewer
reads:

  * valid and invalid pull request titles, and that a failure says what to write;
  * breaking changes, by `!` and by footer, and that the marker survives the merge;
  * security fixes, dependency updates, reverts and the classes that ship nothing;
  * merge, squash, sync, epic and promotion histories: one change counted once;
  * the rollout, so the branches that exist today are not blocked on day one;
  * the input shapes CI feeds in, because CI cannot be tested by a fixture that agrees
    to look like CI.

Run from the repository root: `python3 scripts/test_pr_classify.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
GUARD = SCRIPTS / "pr_classify"

loader = importlib.machinery.SourceFileLoader("pr_classify", str(GUARD))
spec = importlib.util.spec_from_loader("pr_classify", loader)
pc = importlib.util.module_from_spec(spec)
loader.exec_module(pc)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def codes(findings, severity=None):
    return [f.code for f in findings if severity is None or f.severity == severity]


def errors(findings):
    return codes(findings, "error")


def rec(sha, subject, body="", parents=()):
    return {"sha": sha, "parents": list(parents), "subject": subject, "body": body}


def entries_of(records):
    return pc.fold_reverts(pc.fold_carrier_duplicates(pc.history_entries(records)))


def by_pr(entries, pr):
    for entry in entries:
        if entry.get("pr") == pr and entry["kind"] == "carrier":
            return entry
    return None


# ------------------------------------------------------- titles: the vocabulary enforced


def test_valid_titles():
    valid = [
        "feat: adds the classification check",
        "fix: answers the schema cache key again",
        "fix(proxy-security): closes the open redirect",
        "feat(proxy-security)!: moves the proxy onto the session cookie",
        "fix(security): bounds the csw request body",
        "build(deps): bumps postgis to 18-3.6-alpine",
        "chore(deps): bumps the dev requirements",
        "perf: what the save paths decide, no more than that (#1482)",
        "refactor: one reader for both role axes",
        "docs: explains the classification",
        "test: pins the count shapes of the alert lists (#1478)",
        "ci: runs the classification on every pull request",
        "style: orders the imports as the linter sorts them",
        "chore: drops the dead conformity tasks",
        "revert: reverts the celery send_task routing (#1574)",
        "chore(release-management): enforces the classification (#1580)",
    ]
    for title in valid:
        findings, header, _consumes = pc.title_findings(title)
        check("title valid: %s" % title[:52], not errors(findings) and header is not None,
              ", ".join(codes(findings)))


def test_invalid_titles():
    invalid = [
        ("mcp-setup: reads the slot's env by key", "unknown-type"),
        ("Remove the legacy conformity check family", "no-header"),
        ("adds the release baseline audit for #1578", "no-header"),
        ("security: closes the open redirect", "unknown-type"),
        ("sec: closes the open redirect", "unknown-type"),
        ("deps: bumps postgis", "unknown-type"),
        ("wip: half of it", "unknown-type"),
        ("fixup! the previous commit", "no-header"),
        ("hotfix: the proxy again", "unknown-type"),
        ("release: cut 0.2.0", "unknown-type"),
        ("Fix: the type is lowercase", "unknown-type"),
        ("FEAT: shouts", "unknown-type"),
        ("fix:", "empty-summary"),
        ("feat!: ", "empty-summary"),
        ("fix:nospace", "missing-space"),
        ("feat:  ", "empty-summary"),
        ("", "empty"),
    ]
    for title, expected in invalid:
        findings, _header, consumes = pc.title_findings(title)
        got = errors(findings)
        # What makes a title invalid is the error named for it, and that it classifies
        # nothing: `consumes_version` stays None for every one of these.
        check("title invalid: %s" % (title[:44] or "(empty)"),
              expected in got and consumes is None,
              "expected %s, got %s" % (expected, got))


def test_component_prefix_says_what_to_write():
    """The #1578 history is full of component names in the type position (#1649)."""
    findings, _header, _consumes = pc.title_findings(
        "mcp-setup: reads the slot's env by key instead of sourcing it (#1434)")
    fix = " ".join(f.fix or "" for f in findings if f.code == "unknown-type")
    check("a component prefix names a class and a scope in the fix",
          "(mcp-setup)" in fix and any(cls in fix for cls in pc.TYPES), fix)
    check("a component prefix classifies nothing",
          pc.title_findings("mcp-setup: reads the slot's env")[2] is None)


def test_every_hint_is_a_real_correction():
    """The hint table may not point at a class the checker itself would reject."""
    bad = [word for word in HINTS if not any(
        cls in HINTS[word] for cls in pc.TYPES)]
    check("every non-class hint names an accepted class", not bad, ", ".join(bad))
    drift = [word for word in HINTS if word in pc.TYPES]
    check("no hint shadows an accepted class", not drift, ", ".join(drift))


HINTS = pc.HINTS


# ------------------------------------------------------------- breaking change semantics


def test_breaking_marker_on_title():
    for title in ("feat!: the answer shape moves", "fix(proxy-security)!: the proxy moves"):
        findings, header, consumes = pc.title_findings(title)
        check("breaking marker read: %s" % title[:40],
              header and header["breaking"] and consumes is True and not errors(findings),
              ", ".join(codes(findings)))


def test_breaking_on_a_silent_class_is_flagged():
    findings, _header, _consumes = pc.title_findings("docs!: rewrites the policy")
    check("a breaking docs change is questioned",
          "breaking-non-release-class" in codes(findings, "warning"), ", ".join(codes(findings)))


def test_footer_spellings_are_both_footers():
    for footer in ("BREAKING CHANGE: the shape moves", "BREAKING-CHANGE: the shape moves",
                   "breaking change: lowercase still counts"):
        check("footer recognised: %s" % footer[:28],
              pc.breaking_footer("body line\n\n%s\n" % footer) is not None)


def test_pr_body_breaking_without_title_marker_fails():
    result = pc.check_pr("feat: moves the proxy onto the session cookie",
                         "Nothing useful.\n\nBREAKING CHANGE: the proxy needs a cookie\n",
                         [], today="2027-01-01", mode="auto")
    check("a breaking description with no '!' on the title is an error",
          "breaking-not-on-title" in errors(result["findings"]),
          ", ".join(codes(result["findings"])))
    result = pc.check_pr("feat!: moves the proxy onto the session cookie",
                         "BREAKING CHANGE: the proxy needs a cookie", [],
                         today="2027-01-01")
    check("the same with '!' on the title passes",
          "breaking-not-on-title" not in errors(result["findings"]) and result["breaking"],
          ", ".join(codes(result["findings"])))


def test_commit_breaking_without_title_marker_fails():
    """The measured loss: a merge keeps the title, so a marker only in a commit is gone."""
    commits = [rec("a" * 12, "fixes the proxy", "BREAKING CHANGE: the cookie axis moves")]
    result = pc.check_pr("fix: repairs the proxy", "", commits, today="2027-01-01")
    check("a commit's breaking footer with no '!' on the title is an error",
          "breaking-lost-at-merge" in errors(result["findings"]),
          ", ".join(codes(result["findings"])))
    commits = [rec("a" * 12, "fix!: repairs the proxy")]
    result = pc.check_pr("fix: repairs the proxy", "", commits, today="2027-01-01")
    check("the same for a '!' written only on a commit",
          "breaking-lost-at-merge" in errors(result["findings"]),
          ", ".join(codes(result["findings"])))
    result = pc.check_pr("fix!: repairs the proxy", "", commits, today="2027-01-01")
    check("and it is silent once the title carries the marker",
          "breaking-lost-at-merge" not in errors(result["findings"]))


def test_breaking_without_a_note_is_warned():
    result = pc.check_pr("feat!: the answer shape moves", "the usual text", [],
                         today="2027-01-01")
    check("a breaking title with nothing to curate is a warning",
          "breaking-without-note" in codes(result["findings"], "warning"),
          ", ".join(codes(result["findings"])))


# ------------------------------------------------------------- security, deps, reverts


def test_security_fix_is_a_scope_not_a_type():
    _f, header, consumes = pc.title_findings("fix(security): bounds the csw request body")
    check("fix(security) is a fix and consumes a version",
          header["type"] == "fix" and consumes is True)


def test_dependency_updates():
    for title in ("build(deps): bumps postgis", "chore(deps): bumps the dev requirements",
                  "build(deps-dev): bumps the linter"):
        _f, _header, consumes = pc.title_findings(title)
        check("dependency scope consumes a version: %s" % title[:34], consumes is True)
    for title in ("build: wraps the image build", "chore: drops a dead task"):
        _f, _header, consumes = pc.title_findings(title)
        check("a class outside the notes consumes nothing: %s" % title[:34],
              consumes is False)


def test_non_release_classes_are_valid_but_consume_nothing():
    for title in ("docs: explains it", "test: pins it", "ci: runs it",
                  "style: formats it", "chore: tidies it"):
        findings, _header, consumes = pc.title_findings(title)
        check("no-version class valid and silent: %s" % title[:28],
              not errors(findings) and consumes is False, ", ".join(codes(findings)))


def test_revert_has_to_name_what_it_reverts():
    findings, header, _consumes = pc.title_findings("revert: reverts the routing (#1574)")
    check("a revert naming its pull request is fine",
          header["type"] == "revert" and not errors(findings), ", ".join(codes(findings)))
    findings, _header, _c = pc.title_findings("revert: undoes the routing")
    check("a nameless revert is warned when only the title is visible",
          "revert-names-nothing" in codes(findings, "warning"), ", ".join(codes(findings)))
    result = pc.check_pr("revert: undoes the routing", "whatever", [], today="2027-01-01")
    check("a nameless revert is an error once the body is visible",
          "revert-names-nothing" in errors(result["findings"]),
          ", ".join(codes(result["findings"])))
    result = pc.check_pr("revert: undoes the routing", "Reverts #1574", [], today="2027-01-01")
    check("GitHub's own 'Reverts #N' line names it",
          "revert-names-nothing" not in errors(result["findings"]),
          ", ".join(codes(result["findings"])))
    result = pc.check_pr("revert: undoes the routing", "",
                         [rec("f" * 12, "reverts the routing", "This reverts commit abc1234")],
                         today="2027-01-01")
    check("'This reverts commit <sha>' in a commit names it",
          "revert-names-nothing" not in errors(result["findings"]),
          ", ".join(codes(result["findings"])))


def test_commit_that_classifies_differently_is_warned():
    commits = [rec("b" * 12, "fix: something else entirely")]
    result = pc.check_pr("feat: the actual change", "", commits, today="2027-01-01")
    check("a commit of a different class is warned",
          "commit-class-differs" in codes(result["findings"], "warning"),
          ", ".join(codes(result["findings"])))
    commits = [rec("b" * 12, "adds the changelog entry for #1580")]
    result = pc.check_pr("feat: the actual change", "", commits, today="2027-01-01")
    check("a commit that only assembles the pull request is not",
          "commit-class-differs" not in codes(result["findings"], "warning"),
          ", ".join(codes(result["findings"])))


# ------------------------------------------------------------- the rollout of the check


def test_rollout_advisory_then_strict():
    today = pc.STRICT_FROM
    check("the day itself is already strict", pc.mode_for(today, "auto") == "strict")
    check("the day before still advises",
          pc.mode_for("2026-01-01", "auto") == "advisory")
    check("an explicit mode wins over the date",
          pc.mode_for("2030-01-01", "advisory") == "advisory"
          and pc.mode_for("2020-01-01", "strict") == "strict")
    os.environ[pc.STRICT_FROM_ENV] = "2026-01-01"
    try:
        check("the deployment may move the date", pc.mode_for("2026-06-01", "auto") == "strict")
    finally:
        del os.environ[pc.STRICT_FROM_ENV]


def test_exit_codes_of_both_halves():
    out = io.StringIO()
    keep, sys.stdout = sys.stdout, out
    try:
        advisory = pc.main(["title", "mcp-setup: reads the env", "--mode", "advisory"])
        strict = pc.main(["title", "mcp-setup: reads the env", "--mode", "strict"])
        good = pc.main(["title", "fix: reads the env", "--mode", "strict"])
        try:
            # argparse answers a missing argument itself, on stderr, with exit 2.
            with contextlib.redirect_stderr(io.StringIO()):
                usage = pc.main(["title"])
        except SystemExit as exit_request:
            usage = exit_request.code
    finally:
        sys.stdout = keep
    check("advisory exits 0 on a title that does not classify", advisory == 0, str(advisory))
    check("strict exits 1 on the same title", strict == 1, str(strict))
    check("strict exits 0 on a title that classifies", good == 0, str(good))
    check("a missing argument is a usage error", usage == 2, str(usage))
    check("the advisory run says it only reports", "ADVISORY" in out.getvalue(),
          out.getvalue()[-120:])


def test_actions_annotations_are_actionable():
    out = io.StringIO()
    keep, sys.stdout, env = sys.stdout, out, os.environ.get("GITHUB_ACTIONS")
    os.environ["GITHUB_ACTIONS"] = "true"
    try:
        pc.render_report(pc.check_pr("security: closes it", "", [], "2027-01-01"), "strict",
                        stream=out)
    finally:
        sys.stdout = keep
        if env is None:
            os.environ.pop("GITHUB_ACTIONS", None)
        else:
            os.environ["GITHUB_ACTIONS"] = env
    text = out.getvalue()
    check("a failure is an ::error:: annotation", "::error title=classification" in text,
          text[-200:])
    check("the annotation carries the fix, not just the complaint",
          "fix(security)" in text, text[-200:])
    check("the verdict names where to read the rule",
          "commit-classification.rst" in text or "pr_classify types" in text)


# ------------------------------------------------------------------ merge and sync shapes


def test_merge_commit_carrier_reads_the_title():
    """Measured: GitHub writes the pull request title as the merge commit's body."""
    records = [
        rec("c1", "adds the thing", parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base", "c1"]),
    ]
    entries = entries_of(records)
    entry = by_pr(entries, 42)
    check("the merge commit is the carrier", entry is not None)
    check("the carrier is classified by the title in its body",
          entry and entry["type"] == "feat" and entry["class_source"] == "merge-commit-body")
    counted = pc.counted_entries(entries)
    check("one pull request is one entry, not one per commit",
          len(counted) == 1 and len([e for e in entries if e["kind"] == "folded"]) == 1,
          "%d counted, %d folded" % (len(counted), len(entries) - len(counted)))


def test_squash_commit_carrier():
    records = [rec("s1", "feat: adds the thing (#42)", parents=["base"])]
    entries = entries_of(records)
    entry = by_pr(entries, 42)
    check("a squash subject carries the change",
          entry and entry["type"] == "feat" and entry["class_source"] == "squash-subject")


def test_sync_merge_contributes_nothing():
    records = [
        rec("c1", "adds the thing", parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base", "c1"]),
        rec("s1", "Merge remote-tracking branch 'origin/develop' into topic", "",
            parents=["c1", "m1"]),
        rec("s2", "merge develop into the issue-1481 branch to resolve the changelog conflict",
            "", parents=["c1", "m1"]),
    ]
    entries = entries_of(records)
    sync = [e for e in entries if e["kind"] == "sync"]
    check("both sync shapes are recognised", len(sync) == 2, str(len(sync)))
    check("a sync merge answers no class and no finding",
          all(not e["findings"] and not e["type"] for e in sync))
    check("a sync merge is not an entry a release counts",
          all(e not in pc.counted_entries(entries) for e in sync))


def test_promotion_remerge_counts_once():
    """develop -> master re-carries the same pull request: one change, one entry."""
    develop = [
        rec("c1", "adds the thing", parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base", "c1"]),
    ]
    entries = entries_of(develop)
    first = pc.counted_entries(entries)
    with tempfile.TemporaryDirectory() as tmp:
        seen = Path(tmp) / "seen.json"
        seen.write_text(json.dumps({"entries": [
            {k: v for k, v in e.items() if k != "findings"} for e in first]}))
        previous = pc.load_seen(str(seen))
        kept, dropped = pc.dedupe_seen(first, previous)
    check("--seen folds a re-carried pull request away",
          kept == [] and len(dropped) == 1, "%d kept, %d dropped" % (len(kept), len(dropped)))


def test_a_remerged_pull_request_counts_once():
    records = [
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base"]),
        rec("m2", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["m1"]),
    ]
    entries = entries_of(records)
    counted = [e for e in pc.counted_entries(entries) if not (e.get("net") or "").startswith("none")]
    check("the same pull request entering twice is one change", len(counted) == 1,
          str(len(counted)))
    check("and the later copy says it is already counted",
          any((e.get("net") or "").startswith("none") for e in entries))


def test_remerged_copy_may_not_drop_a_breaking_marker():
    records = [
        rec("m1", "Merge pull request #42 from x/y", "feat!: adds the thing (#42)",
            parents=["base"]),
        rec("m2", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["m1"]),
    ]
    entries = entries_of(records)
    entry = by_pr(entries, 42)
    check("the breaking copy wins over the copy that lost '!' ",
          entry and entry["breaking"], str(entry and entry["breaking"]))
    check("and the disagreement is reported",
          "breaking-in-duplicate" in errors(entry["findings"]), ", ".join(codes(entry["findings"])))


# ------------------------------------------------------------------ epic and revert shapes


def test_epic_history_counts_each_feature_once():
    """An epic branch merged into develop: N features, not N and not 1."""
    records = [
        rec("a1", "adds the first half", parents=["base"]),
        rec("ma", "Merge pull request #101 from x/f1", "feat: the first half (#101)",
            parents=["base", "a1"]),
        rec("b1", "fixes the second half", parents=["ma"]),
        rec("mb", "Merge pull request #102 from x/f2", "fix: the second half (#102)",
            parents=["ma", "b1"]),
        rec("me", "Merge pull request #110 from x/epic-release",
            "chore(epic): integrates the release-management epic (#110)",
            parents=["base", "mb"]),
    ]
    entries = entries_of(records)
    counted = pc.counted_entries(entries)
    classes = sorted(e["type"] for e in counted if e["type"])
    check("an epic merge answers one entry per feature pull request",
          classes == ["chore", "feat", "fix"], str(classes))
    check("the epic's own commits are folded, not counted",
          len([e for e in entries if e["kind"] == "folded"]) == 2,
          str([e["kind"] for e in entries]))
    check("a feature inside an epic keeps its own pull request number",
          by_pr(entries, 101) is not None and by_pr(entries, 102) is not None)


def test_epic_integration_should_not_claim_a_feature():
    """#1578's matrix: an epic PR typed `feat` would be one change too many."""
    records = [
        rec("a1", "adds the first half", parents=["base"]),
        rec("ma", "Merge pull request #101 from x/f1", "feat: the first half (#101)",
            parents=["base", "a1"]),
        rec("me", "Merge pull request #110 from x/epic", "feat: integrates the epic (#110)",
            parents=["base", "ma"]),
    ]
    entries = entries_of(records)
    feats = [e for e in pc.counted_entries(entries) if e["type"] == "feat"]
    check("a mis-typed epic PR does show up as an extra feature (so do not do it)",
          len(feats) == 2, str([e["pr"] for e in feats]))


def test_breaking_survives_the_fold():
    records = [
        rec("c1", "moves the cookie axis", "BREAKING CHANGE: the cookie axis moves",
            parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base", "c1"]),
    ]
    entries = entries_of(records)
    entry = by_pr(entries, 42)
    check("a folded commit's breaking fact is unioned into the entry",
          entry and entry["breaking"], str(entry and entry["breaking"]))
    check("and the loss is reported as an error to fix on the title",
          "breaking-folded-up" in errors(entry["findings"]), ", ".join(codes(entry["findings"])))
    relevant = pc.release_relevant(entries)
    check("the entry still counts as release-relevant, now as breaking",
          len(relevant) == 1 and relevant[0]["breaking"], str(len(relevant)))


def test_revert_pair_nets_to_nothing():
    records = [
        rec("c1", "adds the feature", parents=["base"]),
        rec("m1", "Merge pull request #50 from x/f", "feat: adds the feature (#50)",
            parents=["base", "c1"]),
        rec("m2", "Merge pull request #51 from x/r",
            "revert: reverts the feature (#50)\n\nReverts #50", parents=["m1"]),
    ]
    entries = entries_of(records)
    feature = by_pr(entries, 50)
    revert = by_pr(entries, 51)
    check("the feature and its revert inside one window net to nothing",
          (feature.get("net") or "").startswith("none") and revert["net"] == "none",
          "%s / %s" % (feature.get("net"), revert.get("net")))
    check("and the pair ships no release note at all",
          pc.release_relevant(entries) == [], str(pc.release_relevant(entries)))


def test_revert_of_released_work_is_its_own_change():
    records = [rec("m2", "Merge pull request #51 from x/r",
                   "revert: reverts the feature (#50)\n\nReverts #50", parents=["base"])]
    entries = entries_of(records)
    revert = by_pr(entries, 51)
    check("a revert whose target is outside the window keeps its own class",
          not (revert.get("net") or "").startswith("none")
          and revert["net"].startswith("its own class"), revert.get("net", ""))
    check("and it is release-relevant on its own",
          len(pc.release_relevant(entries)) == 1)


def test_breaking_revert_pair_leaves_no_breaking_note():
    records = [
        rec("m1", "Merge pull request #50 from x/f", "feat!: adds the feature (#50)",
            parents=["base"]),
        rec("m2", "Merge pull request #51 from x/r",
            "revert: reverts the feature (#50)\n\nReverts #50", parents=["m1"]),
    ]
    entries = entries_of(records)
    revert = by_pr(entries, 51)
    check("a breaking change taken back inside the window answers no breaking note",
          not revert["breaking"] and not by_pr(entries, 50)["breaking"],
          str([e["breaking"] for e in entries]))
    check("but the pair is reported as the reason",
          "breaking-reverted-in-window" in codes(revert["findings"]),
          ", ".join(codes(revert["findings"])))


# --------------------------------------------------------------- the shapes CI feeds in


def test_github_api_shape_and_plain_list_and_stream():
    api = [{"sha": "a1", "commit": {"message": "adds the thing", "parents": [{"sha": "b"}]}},
           {"sha": "m1", "commit": {"message": "Merge pull request #42 from x/y\n\n"
                                              "feat: adds the thing (#42)",
                                    "parents": [{"sha": "b"}, {"sha": "a1"}]}}]
    records = pc.records_from_json(json.dumps(api), "api")
    entries = entries_of(records)
    check("GitHub's pulls/<n>/commits shape classifies",
          by_pr(entries, 42) is not None and len(pc.counted_entries(entries)) == 1,
          str([(e["kind"], e["pr"]) for e in entries]))

    plain = json.dumps([{"sha": "s1", "parents": [], "subject": "docs: explains it"}])
    check("a plain list of subjects classifies",
          pc.records_from_json(plain)[0]["subject"] == "docs: explains it")

    stream = "s1\x1f\x1fdocs: explains it\x1fbecause it is worth saying\x1e"
    from_stream = pc.records_from_stream(stream)
    check("the git record stream round-trips",
          len(from_stream) == 1 and from_stream[0]["body"].startswith("because"),
          str(from_stream))

    mixed = "not json at all\n\nand no separators"
    check("a stream in a --commits-json file is still read as a stream",
          len(pc.records_from_json(mixed)) == 1)


def test_the_order_the_records_arrive_in_changes_nothing():
    records = [
        rec("c1", "adds the thing", parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat: adds the thing (#42)",
            parents=["base", "c1"]),
    ]
    newest_first = entries_of(records)
    oldest_first = entries_of(list(reversed(records)))
    check("newest-first and oldest-first input agree",
          len(pc.counted_entries(newest_first)) == len(pc.counted_entries(oldest_first))
          and len([e for e in newest_first if e["kind"] == "folded"]) == 1
          and len([e for e in oldest_first if e["kind"] == "folded"]) == 1,
          "%s vs %s" % ([e["kind"] for e in newest_first], [e["kind"] for e in oldest_first]))


def test_json_output_of_history():
    records = [
        rec("c1", "adds the thing", parents=["base"]),
        rec("m1", "Merge pull request #42 from x/y", "feat!: adds the thing (#42)",
            parents=["base", "c1"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "commits.json"
        path.write_text(json.dumps([
            {"sha": r["sha"], "parents": r["parents"], "subject": r["subject"],
             "body": r["body"]} for r in records]))
        out, keep = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            code = pc.main(["history", "--commits-json", str(path), "--json",
                            "--mode", "strict"])
        finally:
            sys.stdout = keep
    payload = json.loads(out.getvalue())
    check("history --json answers the counts #1581 needs",
          payload["counts"]["counted_entries"] == 1
          and payload["counts"]["folded"] == 1
          and payload["counts"]["release_relevant"] == 1
          and payload["counts"]["breaking"] == 1, json.dumps(payload["counts"]))
    check("and it exits 0 when nothing is wrong", code == 0, str(code))


# ------------------------------------------------------------- the traversal on real git


def build_repo(tmp):
    """A throw-away repository with the three shapes #1580 has to survive."""
    repo = Path(tmp) / "repo"
    repo.mkdir()

    def run(*cmd, **kwargs):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
        env.update(kwargs.pop("env", {}))
        return subprocess.run(["git"] + list(cmd), cwd=repo, check=True, env=env,
                              capture_output=True, text=True)

    run("init", "-q", "-b", "develop")
    (repo / "base").write_text("base\n")
    run("add", "base")
    run("commit", "-qm", "the base commit")
    base = run("rev-parse", "HEAD").stdout.strip()

    run("checkout", "-qb", "feature")
    (repo / "one").write_text("one\n")
    run("add", "one")
    run("commit", "-qm", "adds the first half")
    (repo / "two").write_text("two\n")
    run("add", "two")
    run("commit", "-qm", "moves the cookie axis", "-m",
        "BREAKING CHANGE: the cookie axis moves")
    tip = run("rev-parse", "HEAD").stdout.strip()

    run("checkout", "-q", "develop")
    run("merge", "--no-ff", "-q", "feature", "-m", "Merge pull request #42 from x/y",
        "-m", "feat: adds the thing (#42)")
    merge = run("rev-parse", "HEAD").stdout.strip()

    # A branch that merges develop back into itself: the sync #1578 measured.
    run("checkout", "-qb", "syncer", base)
    (repo / "three").write_text("three\n")
    run("add", "three")
    run("commit", "-qm", "adds a third thing")
    run("merge", "--no-ff", "-q", "develop",
        "-m", "Merge remote-tracking branch 'origin/develop' into syncer")
    sync_tip = run("rev-parse", "HEAD").stdout.strip()

    run("checkout", "-q", "develop")
    run("merge", "--no-ff", "-q", "syncer", "-m", "Merge pull request #44 from x/sync",
        "-m", "fix: repairs the sync (#44)")
    return dict(repo=repo, base=base, tip=tip, merge=merge, sync_tip=sync_tip,
                head=run("rev-parse", "HEAD").stdout.strip())


def test_the_traversal_against_real_merge_commits(repo):
    records = pc.git_log_records("%s..%s" % (repo["base"], repo["head"]),
                             repo=str(repo["repo"]))
    entries = entries_of(records)
    counted = pc.counted_entries(entries)
    carriers = [e for e in counted if e["kind"] == "carrier"]
    folded = [e for e in entries if e["kind"] == "folded"]
    loose = [e for e in counted if e["kind"] == "self"]
    check("real git: both pull requests are carriers",
          sorted(e["pr"] for e in carriers) == [42, 44],
          str([(e["pr"], e["kind"]) for e in counted]))
    # The fold is claimed only where a merge edge proves it. The two commits reached
    # through a merge edge fold; the branch commit that only a plain parent edge leads to
    # stays an entry of its own, because claiming it would mean guessing which pull
    # request a base-branch commit belongs to - under-reporting a fold is honest,
    # mis-attributing somebody's change is not.
    check("real git: the commits a merge edge proves are folded",
          len(folded) == 2, str([e["kind"] for e in entries]))
    check("real git: what no merge edge proves stays its own entry",
          len(loose) == 2, str([e["kind"] for e in counted]))
    check("real git: the branch commit's breaking footer reaches entry #42",
          by_pr(entries, 42)["breaking"], "")
    check("real git: no record is counted twice",
          len({e["sha"] for e in entries}) == len(entries),
          str([e["sha"] for e in entries]))
    check("real git: the sync merge added no entry of its own",
          not [e for e in entries if e["kind"] == "sync" and e["sha"] == repo["sync_tip"]],
          str([e["kind"] for e in entries]))
    check("real git: one feature and one fix are the release-relevant changes",
          sorted(e["type"] for e in pc.release_relevant(entries)) == ["feat", "fix"],
          str([e["type"] for e in pc.release_relevant(entries)]))


def test_the_checker_runs_over_its_own_repository():
    """`history` over this repository's own history has to answer, not crash.

    How much history a checkout carries is not a constant: CI checks a pull request out at
    depth 1, so `HEAD~40` does not exist there and never did. The check therefore asks the
    repository how deep it is first. With depth it reads 40 commits for real; without it,
    the run must fail the way a good tool fails - naming the shallow clone and the way in -
    because that message is the only thing a developer on a CI runner gets, and "unknown
    commit" alone sends them hunting for a typo in a range that is correct.
    """
    here = SCRIPTS.parent
    depth = subprocess.run(["git", "-C", str(here), "rev-list", "--count", "HEAD"],
                           capture_output=True, text=True)
    commits = int(depth.stdout.strip() or 0) if depth.returncode == 0 else 0
    out, err_out = io.StringIO(), io.StringIO()
    keep, sys.stdout = sys.stdout, out
    try:
        with contextlib.redirect_stderr(err_out):
            code = pc.main(["history", "--range", "HEAD~40..HEAD", "--mode", "advisory",
                            "--top", "5"])
    finally:
        sys.stdout = keep
    text, err = out.getvalue(), err_out.getvalue()
    if commits > 40:
        check("history answers over the real repository in advisory mode",
              code == 0 and "records ->" in text, text[:120] + " exit " + str(code))
    else:
        check("on a shallow checkout (%d commit(s)) it says so instead of quoting git" % commits,
              code == 2 and "shallow" in err and "--commits-json" in err,
              "exit %s: %s" % (code, err.strip()[:160]))


def test_unclassifiable_carriers_are_the_error_that_reaches_a_developer():
    out, err_out = io.StringIO(), io.StringIO()
    keep, sys.stdout = sys.stdout, out
    try:
        with contextlib.redirect_stderr(err_out):
            code = pc.main(["history", "--commits-json", "-", "--mode", "strict"])
    except Exception as raised:                    # pragma: no cover - guard
        code = "raised %s" % raised
    finally:
        sys.stdout = keep
    check("history with no input is a usage error, not a crash", code == 2, str(code))
    check("and it says what to give it", "commits-json" in err_out.getvalue(),
          err_out.getvalue())


# -------------------------------------------------------------------------------- main


def test_the_documented_code_list_matches_the_tool():
    """The policy page lists the finding codes, so the list has to be the tool's.

    `commit-classification.rst` says the codes are stable and are what this suite pins.
    A page that names a code the tool never emits, or omits one it does, is worse than no
    page: a developer greps the doc for a code they saw in CI. The claim is checked here
    rather than kept as a hope.
    """
    doc = (SCRIPTS.parent / "docs" / "source" / "development"
           / "commit-classification.rst")
    if not doc.exists():
        check("the policy page is present", False, str(doc))
        return
    text = doc.read_text()
    block = re.search(r"codes are stable(.*?)Run\n``python3", text, re.S)
    check("the page lists the codes", block is not None, "no code list found")
    if not block:
        return
    listed = set(re.findall(r"``([a-z-]+)``", block.group(1)))
    emitted = set(pc.EMITTED_CODES)
    check("every documented code is one the tool emits", listed <= emitted,
          "invented: %s" % ", ".join(sorted(listed - emitted)))
    check("every emitted code is documented", emitted <= listed,
          "undocumented: %s" % ", ".join(sorted(emitted - listed)))


def main():
    test_valid_titles()
    test_invalid_titles()
    test_component_prefix_says_what_to_write()
    test_every_hint_is_a_real_correction()
    test_breaking_marker_on_title()
    test_breaking_on_a_silent_class_is_flagged()
    test_footer_spellings_are_both_footers()
    test_pr_body_breaking_without_title_marker_fails()
    test_commit_breaking_without_title_marker_fails()
    test_breaking_without_a_note_is_warned()
    test_security_fix_is_a_scope_not_a_type()
    test_dependency_updates()
    test_non_release_classes_are_valid_but_consume_nothing()
    test_revert_has_to_name_what_it_reverts()
    test_commit_that_classifies_differently_is_warned()
    test_rollout_advisory_then_strict()
    test_exit_codes_of_both_halves()
    test_actions_annotations_are_actionable()
    test_merge_commit_carrier_reads_the_title()
    test_squash_commit_carrier()
    test_sync_merge_contributes_nothing()
    test_promotion_remerge_counts_once()
    test_a_remerged_pull_request_counts_once()
    test_remerged_copy_may_not_drop_a_breaking_marker()
    test_epic_history_counts_each_feature_once()
    test_epic_integration_should_not_claim_a_feature()
    test_breaking_survives_the_fold()
    test_revert_pair_nets_to_nothing()
    test_revert_of_released_work_is_its_own_change()
    test_breaking_revert_pair_leaves_no_breaking_note()
    test_github_api_shape_and_plain_list_and_stream()
    test_the_order_the_records_arrive_in_changes_nothing()
    test_json_output_of_history()
    test_the_documented_code_list_matches_the_tool()
    test_unclassifiable_carriers_are_the_error_that_reaches_a_developer()

    with tempfile.TemporaryDirectory(prefix="pr-classify-") as tmp:
        repo = build_repo(tmp)
        test_the_traversal_against_real_merge_commits(repo)
    test_the_checker_runs_over_its_own_repository()

    failed = 0
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}"
              + (f"  [{detail}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
