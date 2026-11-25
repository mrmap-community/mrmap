#!/usr/bin/env python3
"""test_release_planning: the release planner's config is one story, told once.

Run from the repository root:  python3 scripts/test_release_planning.py
(also run by scripts/check_repo_tooling.sh). Standard library only; git is
read-only. No docker, no network, no node.

Why this suite exists
---------------------
#1581 wires the release planner of epic #1577: release-please-config.json,
.release-please-manifest.json and .github/workflows/release-planning.yml
together decide the next version of `develop` and its changelog entry. The
three files, the canonical version mechanism of #1579, the classification
vocabulary of #1580 and the changelog of the baseline of #1578 must agree on
every point, and nothing else fails when they drift: a section mapping that
stops matching scripts/pr_classify silently moves notes under the wrong
heading, a manifest that stops matching VERSION silently releases the wrong
number, and a workflow that loses its `skip-github-release` line silently
starts putting tags on `develop` - the one thing the issue forbids. CI reads
none of these files otherwise, so the coherence is pinned here.

What this suite does NOT do
---------------------------
* It does not run the planner. That is
  scripts/test_release_planning_synthetic.py, which replays synthetic
  histories through the real tool where node is available and skips out loud
  where it is not.
* It decides no policy of its own: every value it pins is the value
  docs/source/development/release-planning.rst explains, and a change there
  changes the expectation here in the same pull request.
"""
import importlib.machinery
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(HERE))
import canonical_version as cv  # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, None if ok is None else bool(ok), detail))
    return bool(ok)


def load_module(name, path):
    # `scripts/pr_classify` has no .py suffix, so the spec has to be built
    # from an explicit source loader instead of from the file location.
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args],
                          capture_output=True, text=True)


def load_files():
    config = json.loads((REPO / 'release-please-config.json').read_text(encoding='utf-8'))
    manifest = json.loads((REPO / '.release-please-manifest.json').read_text(encoding='utf-8'))
    workflow = (REPO / '.github' / 'workflows' / 'release-planning.yml').read_text(encoding='utf-8')
    changelog = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')
    return config, manifest, workflow, changelog


def config_checks(config, pr_classify):
    check('release-type is simple', config.get('release-type') == 'simple',
          'the whole repository is one version; a language release type would '
          'start writing files this project does not have')
    check('packages is the single root component',
          config.get('packages') == {'.': {}},
          'one version for one application, the manifest keys itself "."')
    check('the planner never tags develop', config.get('skip-github-release') is True,
          'tags and GitHub releases belong to the promotion (#1584) and to people')
    check('the bump knob is the recorded reversible choice',
          config.get('bump-minor-pre-major') is True and
          'bump-patch-for-minor-pre-major' not in config,
          'Q2 of #1578 is Accepted: A (ADR-0002) - below 1.0.0 a breaking '
          'change is the MINOR this project promised; the alternative stays '
          'one key away (docs: release-planning)')

    check('the canonical VERSION is the planner version file',
          config.get('version-file') == cv.VERSION_FILE,
          'the planner rewrites the file the generator of #1579 owns')
    extra = config.get('extra-files') or []
    check('the backend projection rides along in the release PR',
          str(cv.PROJECTION) in extra,
          'a release PR that moves VERSION without backend/MrMap/version.py '
          'would break scripts/test_canonical_version.py on its own branch')

    # The section table is the release-facing echo of the classification
    # table of #1580. Compare both directions, and compare against the
    # vocabulary module rather than a copy of it.
    sections = config.get('changelog-sections') or []
    by_type = {s.get('type'): s for s in sections}
    types = pr_classify.TYPES
    check('every class of the classification vocabulary has a section',
          set(by_type) == set(types),
          f'config has {sorted(by_type)}, pr_classify knows {sorted(types)}')
    visible = {t for t, s in by_type.items() if not s.get('hidden')}
    consuming = {t for t, meta in types.items() if meta['consumes_version']}
    check('exactly the version-consuming classes are visible',
          visible == consuming,
          'docs/chore/ci/style/test/build-only windows must produce no '
          'release PR (the Q4A reading); a consuming class must never be hidden')
    expect = {'feat': 'Added', 'fix': 'Fixed', 'perf': 'Changed',
              'refactor': 'Changed', 'revert': 'Changed'}
    actual = {t: by_type[t]['section'] for t in expect if t in by_type}
    check('the visible sections are the Keep a Changelog headings',
          actual == expect, f'{actual} != {expect}')

    check('the window is anchored on the approved baseline',
          bool(re.fullmatch(r'[0-9a-f]{40}', config.get('last-release-sha') or '')),
          'last-release-sha is the machine reading of the baseline "0.1.0 '
          '(2023-03-23)" of #1578: everything merged after it is unreleased')
    depth = config.get('commit-search-depth')
    check('the search depth is a number', isinstance(depth, int), f'{depth!r}')


def window_checks(config):
    """The depth must still reach the anchor, or the window truncates silently.

    Both checks below need the anchor commit in the local object store; the
    CI runner for scripts/ checks out shallow, and a suite must report a
    missing input as a skip out loud, never as a failure it cannot know.
    """
    anchor = config.get('last-release-sha')
    if not anchor or not re.fullmatch(r'[0-9a-f]{40}', anchor):
        return
    if git('cat-file', '-e', f'{anchor}^{{commit}}').returncode != 0:
        RESULTS.append(('the commit search depth still spans the window', None,
                        'SKIP: the anchor commit is not in this checkout '
                        '(shallow clone); the check runs on full clones'))
        return
    counted = git('rev-list', '--count', f'{anchor}..HEAD')
    if counted.returncode != 0:
        return
    distance = int(counted.stdout.strip())
    depth = config.get('commit-search-depth') or 0
    check('the commit search depth still spans the window', depth > distance,
          f'depth {depth} vs {distance} commits between the anchor and HEAD; '
          'raise the depth or land the promotion of #1584, which anchors the '
          'window on a tag and retires this key')


def manifest_checks(manifest):
    version = cv.read_version(REPO)
    check('the manifest tracks the canonical version',
          manifest == {'.': version},
          f'manifest {manifest} vs VERSION {version}')


def workflow_checks(workflow):
    check('the planner is pinned to a release of the action',
          re.search(r'release-please-action@v5\.0\.0', workflow) is not None,
          'v5.0.0 pins release-please ^17.6.0; the ADR of #1578 measured 17.11.2')
    check('it only plans against develop', 'target-branch: develop' in workflow)
    check('the workflow repeats the config gate, not the config',
          'skip-github-release: true' in workflow,
          'the line that keeps tags and releases off develop - its loss would '
          'otherwise be a quiet one-line diff')
    for forbidden in ('environment:', 'secrets.', 'deploy:'):
        check(f'no {forbidden!r} in the planner workflow',
              forbidden not in workflow,
              'the planner has no deployment path of any kind')
    check('dispatch carries the reviewed override',
          'release_as' in workflow and 'release-as: ${{ inputs.release_as }}' in workflow)


def changelog_checks(changelog, config, manifest):
    check('the approved baseline entry survives',
          '## [0.1.0] - 2023-03-23' in changelog)
    check('the curated Unreleased section survives',
          '## Unreleased\n' in changelog)
    # release-please inserts its release before the FIRST heading matching
    # its DEFAULT_VERSION_HEADER_REGEX ('\n###? v?[0-9[]', mirrored here).
    # The invariant that must survive the planner's own releases: that
    # heading carries the canonical version - today the baseline 0.1.0,
    # after a release PR whatever VERSION that PR moved to - so no edit of
    # this suite is ever needed inside the release flow.
    version = cv.read_version(REPO)
    first = re.search(r'\n#{2,3} v?[0-9[]', changelog)
    lands_on_canonical = (first is not None and
                          changelog.startswith(f'## [{version}]', first.start() + 1))
    check('the first version-shaped heading carries the canonical version',
          lands_on_canonical,
          f'expected "## [{version}]" where the planner inserts, found '
          f'{changelog[first.start():first.start() + 24].strip() if first else None!r}; '
          'the curated section must not look like a version (it is spelled '
          '"## Unreleased" for this reason)')


def projection_checks():
    projection = (REPO / cv.PROJECTION).read_text(encoding='utf-8')
    check('the projection carries the planner marker',
          'x-release-please-version' in projection and
          f"VERSION = '{cv.read_version(REPO)}'  # x-release-please-version" in projection,
          'the marker is what lets the release PR rewrite the projection and '
          'the generator template, not a hand, keeps it coherent')
    generator = (HERE / 'canonical_version.py').read_text(encoding='utf-8')
    check('the generator template carries the marker too',
          'x-release-please-version' in generator,
          'otherwise the next --write erases it and the planner loses the file')


def main():
    pr_classify = load_module('pr_classify', HERE / 'pr_classify')
    config, manifest, workflow, changelog = load_files()
    config_checks(config, pr_classify)
    window_checks(config)
    manifest_checks(manifest)
    workflow_checks(workflow)
    changelog_checks(changelog, config, manifest)
    projection_checks()

    skipped = [r for r in RESULTS if r[1] is None]
    failed = [r for r in RESULTS if r[1] is False]
    for name, ok, detail in RESULTS:
        label = 'SKIP' if ok is None else ('PASS' if ok else 'FAIL')
        print(f'{label}  {name}' + (f'  - {detail}' if ok is not True and detail else ''))
    print(f'{"FAILED" if failed else "OK"} ({len(RESULTS) - len(skipped)} ran, '
          f'{len(skipped)} skipped)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
