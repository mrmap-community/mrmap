#!/usr/bin/env python3
"""Synchronize MrMap GitHub issues into organization Project #3.

Project state is a *view*, never an authorization or issue-closing authority.
Run without --apply for a read-only preview. Requires gh CLI and project scope.
"""
import argparse
import json
import re
import subprocess
import sys

OWNER = "mrmap-community"
REPO = "mrmap-community/mrmap"
PROJECT = 3
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
ISSUE_BRANCH = re.compile(r"(?:^|/)issue[-_](\d+)(?:\b|[-_/])", re.I)


def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
    if p.returncode:
        raise RuntimeError("gh " + " ".join(args[:3]) + ": " + p.stderr.strip())
    return p.stdout


def gh_json(*args):
    return json.loads(gh(*args))


def issue_phase(issue, prs):
    """Conservative UI hint; it is NOT the AO eligibility decision."""
    if issue["state"].upper() != "OPEN":
        return "Done"
    labels = {x["name"] for x in issue.get("labels", [])}
    if "agent: paused" in labels:
        return "Blocked"
    matching = prs.get(issue["number"], [])
    if any(not pr["isDraft"] for pr in matching):
        return "Review"
    if matching:
        return "In Progress"
    # DO NOT infer Ready from the approved label alone. Real eligibility also
    # requires trusted label provenance, satisfied blockers, no claims and no PR.
    return "Backlog"


def pr_index(prs):
    index = {}
    for pr in prs:
        refs = {int(n) for n in CLOSES.findall(pr.get("body") or "")}
        refs.update(int(n) for n in ISSUE_BRANCH.findall(pr.get("headRefName") or ""))
        for n in refs:
            index.setdefault(n, []).append(pr)
    return index


def project_url(item):
    content = item.get("content") or {}
    return content.get("url") or item.get("url")


def project_item_fields(item):
    fields = {}
    for value in (item.get("fieldValues") or {}).get("nodes") or []:
        field = value.get("field") or {}
        name = field.get("name")
        if not name:
            continue
        if value.get("__typename") == "ProjectV2ItemFieldSingleSelectValue":
            fields[name] = value.get("name")
        elif value.get("__typename") == "ProjectV2ItemFieldTextValue":
            fields[name] = value.get("text")
    return fields


def project_items():
    query = """
query($owner: String!, $number: Int!, $first: Int!, $after: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      items(first: $first, after: $after) {
        nodes {
          id
          content {
            ... on Issue { url }
            ... on PullRequest { url }
          }
          fieldValues(first: 100) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""
    items = []
    after = None
    while True:
        args = ["api", "graphql", "-f", "query=" + query,
                "-F", "owner=" + OWNER, "-F", "number=" + str(PROJECT),
                "-F", "first=100"]
        if after:
            args.extend(["-F", "after=" + after])
        response = gh_json(*args)
        project = (((response.get("data") or {}).get("organization") or {})
                   .get("projectV2") or {})
        connection = project.get("items") or {}
        items.extend(connection.get("nodes") or [])
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after:
            raise RuntimeError("Project items pagination ended without a cursor")
    return {"items": items}


def synchronize(apply=False):
    issues = gh_json("issue", "list", "-R", REPO, "--state", "all",
                     "--limit", "1000", "--json", "number,title,state,url,labels")
    prs = gh_json("pr", "list", "-R", REPO, "--state", "open",
                  "--limit", "1000", "--json", "number,body,headRefName,isDraft,url")
    raw = project_items()
    fields = gh_json("project", "field-list", str(PROJECT), "--owner", OWNER,
                     "--format", "json")
    names = {f["name"] for f in fields.get("fields", [])}
    if "Development Phase" not in names or "Agent Status" not in names:
        raise RuntimeError("Project fields missing; refusing partial sync")

    by_url = {}
    for project_item in raw["items"]:
        url = project_url(project_item)
        if url:
            by_url[url] = {**project_item, **project_item_fields(project_item)}
    # Do not delete, archive or mutate unrelated project entries.
    idx = pr_index(prs)
    counts = {"add": 0, "phase": 0, "agent": 0, "unchanged": 0}
    for issue in sorted(issues, key=lambda x: x["number"]):
        url = issue["url"]
        item = by_url.get(url)
        # Import current backlog only; keep existing closed items for history.
        if item is None and issue["state"].upper() != "OPEN":
            continue
        phase = issue_phase(issue, idx)
        labels = {x["name"] for x in issue.get("labels", [])}
        agent = ("Paused" if "agent: paused" in labels else
                 "Approved" if "agent: approved" in labels else "Not Approved")
        if phase == "Done":
            agent = "Completed"
        if not item:
            counts["add"] += 1
            print(f"ADD #{issue['number']}: {phase}", flush=True)
            if apply:
                gh("project", "item-add", str(PROJECT), "--owner", OWNER, "--url", url)
        # Fields may be omitted in some CLI versions: compare only when present.
        for field, desired, key in [("Development Phase", phase, "phase"),
                                     ("Agent Status", agent, "agent")]:
            current = (item or {}).get(field)
            if current == desired:
                counts["unchanged"] += 1
                continue
            counts[key] += 1
            print(f"SET #{issue['number']} {field}: {current!r} -> {desired}", flush=True)
            if apply:
                gh("project", "item-edit", str(PROJECT), "--owner", OWNER,
                   "--url", url, "--field", field, "--value", desired)
    print(json.dumps({"mode": "apply" if apply else "dry-run", "issue_count": len(issues),
                      "project_item_count": len(raw["items"]), "changes": counts},
                     sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="write fields and add missing issues (default: dry run)")
    args = p.parse_args()
    try:
        synchronize(args.apply)
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as e:
        print("Project sync failed closed: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
