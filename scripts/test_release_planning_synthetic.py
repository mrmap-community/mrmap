#!/usr/bin/env python3
"""test_release_planning_synthetic: replay the release planner over synthetic
mrmap-shaped histories and assert the plans it prepares. Dry runs only, in a
throwaway directory, against a mock GitHub that answers reads and logs
everything: nothing outside the temporary directory is written, and no
credential is read - this is the dry-run-without-production-writes test of
#1581 itself.

Run from the repository root:  python3 scripts/test_release_planning_synthetic.py

What it needs, and what it says when the needs are missing
----------------------------------------------------------
node, git, and the release-please package itself (the pin the workflow names
in its comment). A CI runner without them gets every scenario reported as
SKIP, out loud, with the reason and the command that makes the suite real -
the honest-green rule of scripts/check_repo_tooling.sh, the same one
test_validator_retirement.py uses for docker.

    npm install --prefix /tmp/rp release-please@17.11.2
    MRMAP_RELEASE_PLEASE_JS=/tmp/rp/node_modules/release-please/build/src/bin/release-please.js \
        python3 scripts/test_release_planning_synthetic.py

Why these scenarios and no others
----------------------------------
Each one is an acceptance criterion of #1581 replayed on the history shapes
#1578 measured on develop: a pull request reaches the branch as a merge commit
whose whole body is the pull request title; 7.5k commits never parse and must
contribute nothing; no tag and no GitHub release has ever existed here. What
this suite cannot replay is left out loud in
docs/source/development/release-planning.rst ("what could not be measured")
instead of being faked: the merged-but-untagged guard speaks through the real
pull-request API, and PR-number links in entries need it too, so both are
recorded from the tool's source there.
"""
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def skip_all(reason, scenarios):
    for scenario in scenarios:
        RESULTS.append((scenario, None, f'SKIP: {reason}'))


# ---------------------------------------------------------------- mock github
class MockGitHub(http.server.BaseHTTPRequestHandler):
    """Answers exactly what the planner reads in a dry run, and logs it.

    Releases: none, ever - develop has none and this suite keeps it that way;
    the anchored scenario anchors on a git tag, which the planner reads from
    the clone, not from the API. Pull requests: none open. Repository: the
    default branch is develop.
    """

    def log_message(self, *args):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        import re
        if re.match(r'^/api/v3/repos/[^/]+/[^/]+$', self.path):
            return self._json({'name': 'mrmap', 'owner': {'login': 'mrmap-community'},
                               'default_branch': 'develop'})
        if '/releases' in self.path or '/pulls' in self.path:
            return self._json([])
        return self._json({})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0)) or 0
        payload = self.rfile.read(length).decode() if length else ''
        try:
            query = json.loads(payload).get('query', '')
        except json.JSONDecodeError:
            query = payload
        if 'releases(' in query:
            # develop has no GitHub release; every anchor in this suite is a
            # git tag read from the clone.
            return self._json({'data': {'repository': {'releases': {
                'nodes': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}})
        return self._json({'data': {}})


def start_mock():
    server = http.server.HTTPServer(('127.0.0.1', 0), MockGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ------------------------------------------------------------ synthetic repos
CHANGELOG = """# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added
- Curated entry that a human wrote and that must survive.

## [0.1.0] - 2023-03-23

### Added
- The old released baseline.
"""

VERSION_PY = """\"\"\"projection\"\"\"

VERSION = '0.1.0'  # x-release-please-version
"""


def git(cwd, *args):
    env = dict(os.environ,
               GIT_AUTHOR_NAME='T', GIT_AUTHOR_EMAIL='t@example.invalid',
               GIT_COMMITTER_NAME='T', GIT_COMMITTER_EMAIL='t@example.invalid')
    r = subprocess.run(['git', *args], cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)}: {r.stderr}')
    return r.stdout.strip()


def build_repo(target):
    """origin.git + clone on develop, seeded with the SHIPPED config.

    The committed planner config is read from the repository, so this suite
    replays the file that ships, not a copy of it; only last-release-sha is
    replaced by the synthetic baseline boundary, which is where the real file
    names the real boundary commit.
    """
    target = pathlib.Path(target)
    bare = target / 'origin.git'
    clone = target / 'clone'
    git(target, 'init', '--bare', '-b', 'develop', str(bare))
    git(target, 'clone', '-q', '--', str(bare), str(clone))

    (clone / 'VERSION').write_text('0.1.0\n', encoding='utf-8')
    (clone / 'CHANGELOG.md').write_text(CHANGELOG, encoding='utf-8')
    (clone / 'backend' / 'MrMap').mkdir(parents=True)
    (clone / 'backend' / 'MrMap' / 'version.py').write_text(VERSION_PY, encoding='utf-8')
    git(clone, 'add', '-A')
    git(clone, 'commit', '-m', 'seed the canonical version and its projections')
    git(clone, 'commit', '--allow-empty', '-m', 'adds a legacy feature and fixes that')

    config = json.loads((REPO / 'release-please-config.json').read_text(encoding='utf-8'))
    config['last-release-sha'] = git(clone, 'rev-parse', 'HEAD^')  # the seed commit
    (clone / 'release-please-config.json').write_text(
        json.dumps(config, indent=2) + '\n', encoding='utf-8')
    (clone / '.release-please-manifest.json').write_text(
        json.dumps({'.': '0.1.0'}, indent=2) + '\n', encoding='utf-8')
    git(clone, 'add', '-A')
    git(clone, 'commit', '-m', 'chore(release-management): adds the release planner')
    return clone


def pr_merge(clone, pr, title):
    """GitHub's merge-merge carrier: a subject that never parses, a body that
    is exactly the pull request title, and real file changes (CommitSplit
    assigns commits by touched files, so an empty commit is dropped there)."""
    branch = f'feature/pr-{pr}'
    git(clone, 'checkout', '-q', '-b', branch)
    (clone / f'change-{pr}.txt').write_text(f'work on pull request {pr}\n', encoding='utf-8')
    git(clone, 'add', '-A')
    git(clone, 'commit', '-q', '-m', f'work on pull request {pr}')
    git(clone, 'checkout', '-q', 'develop')
    git(clone, 'merge', '--no-ff', '-q', branch,
        '-m', f'Merge pull request #{pr} from mrmap-community/{branch}', '-m', title)


def merged_release_pr(clone, version):
    """The state after a release PR was merged onto develop and a person
    tagged it - the file writes are what the planner itself makes: VERSION,
    the projection, the manifest, and a changelog entry inserted before the
    first version heading."""
    import datetime
    branch = 'release-please--branches--develop'
    git(clone, 'checkout', '-q', '-b', branch)
    (clone / 'VERSION').write_text(version + '\n', encoding='utf-8')
    vp = clone / 'backend' / 'MrMap' / 'version.py'
    vp.write_text(vp.read_text(encoding='utf-8').replace(
        "VERSION = '0.1.0'", f"VERSION = '{version}'"), encoding='utf-8')
    (clone / '.release-please-manifest.json').write_text(
        json.dumps({'.': version}, indent=2) + '\n', encoding='utf-8')
    entry = (f'## [{version}](https://github.com/mrmap-community/mrmap/compare/'
             f'v0.1.0...v{version}) ({datetime.date.today().isoformat()})\n\n'
             '### Added\n\n* the first planned feature\n')
    ch = (clone / 'CHANGELOG.md').read_text(encoding='utf-8')
    first = ch.index('\n## [0.1.0]')
    ch = ch[:first] + '\n' + entry + ch[first + 1:]
    (clone / 'CHANGELOG.md').write_text(ch, encoding='utf-8')
    git(clone, 'add', '-A')
    git(clone, 'commit', '-m', f'chore: release {version}')
    git(clone, 'checkout', '-q', 'develop')
    git(clone, 'merge', '--no-ff', '-q', branch,
        '-m', f'Merge pull request #1700 from mrmap-community/{branch}',
        '-m', f'chore: release {version}')
    git(clone, 'tag', f'v{version}')   # the promotion of #1584: a tag, that is all


SCENARIOS = {
    'planned release bumps minor over feat and lists feat and fix only':
        lambda c: [pr_merge(c, 1601, 'feat: the first planned feature'),
                   pr_merge(c, 1602, 'fix: a repair worth a note'),
                   pr_merge(c, 1603, 'docs: explanation nobody releases')],
    'docs and chore windows prepare nothing':
        lambda c: [pr_merge(c, 1610, 'docs: only docs merged'),
                   pr_merge(c, 1611, 'chore: only chores merged')],
    'a bang title alone prepares nothing and says so in the log':
        lambda c: [pr_merge(c, 1620, 'feat!: a breaking change in the title')],
    'an empty window prepares nothing':
        lambda c: [],
    'after a promoted and tagged release the window re-anchors and no note repeats':
        lambda c: [pr_merge(c, 1601, 'feat: the first planned feature'),
                   merged_release_pr(c, '0.2.0'),
                   pr_merge(c, 1640, 'fix: a new repair after the release')],
}

EXPECTATIONS = {
    'planned release bumps minor over feat and lists feat and fix only':
        lambda out: (
            'chore(develop): release 0.2.0' in out
            and '### Added' in out and '### Fixed' in out
            and 'the first planned feature' in out and 'a repair worth a note' in out
            and 'explanation nobody releases' not in out),
    'docs and chore windows prepare nothing':
        lambda out: 'Would open 0 pull requests' in out,
    'a bang title alone prepares nothing and says so in the log':
        lambda out: 'Would open 0 pull requests' in out,
    'an empty window prepares nothing':
        lambda out: 'Would open 0 pull requests' in out,
    'after a promoted and tagged release the window re-anchors and no note repeats':
        lambda out: (
            'chore(develop): release 0.2.1' in out
            and 'a new repair after the release' in out
            and 'the first planned feature' not in out),
}


def find_release_please():
    env = os.environ.get('MRMAP_RELEASE_PLEASE_JS')
    if env and pathlib.Path(env).is_file():
        return env
    if not shutil.which('node'):
        return None
    r = subprocess.run(
        ['node', '-e',
         'console.log(require.resolve("release-please/build/src/bin/release-please.js"))'],
        capture_output=True, text=True)
    path = r.stdout.strip()
    return path if r.returncode == 0 and path else None


def run_planner(rp_js, port, clone, extra=()):
    cmd = ['node', rp_js, 'release-pr', '--token', 'SYNTHETIC-NOT-A-CREDENTIAL',
           '--repo-url', 'https://github.com/mrmap-community/mrmap',
           '--api-url', f'http://127.0.0.1:{port}/api/v3',
           '--graphql-url', f'http://127.0.0.1:{port}/graphql',
           '--target-branch', 'develop', '--default-branch', 'develop',
           '--local', '--local-path', str(clone), '--dry-run', *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def main():
    scenarios = list(SCENARIOS)
    rp_js = find_release_please()
    reason = None
    if not shutil.which('git'):
        reason = 'git is not available'
    elif rp_js is None:
        reason = ('the release-please package is not available; install it per '
                  'the docstring and set MRMAP_RELEASE_PLEASE_JS to its CLI')
    if reason:
        skip_all(reason, scenarios)
    else:
        server = start_mock()
        port = server.server_address[1]
        try:
            for scenario in scenarios:
                work = pathlib.Path(tempfile.mkdtemp(prefix='mrmap-1581-synth-'))
                try:
                    clone = build_repo(work)
                    SCENARIOS[scenario](clone)
                    git(clone, 'push', '-q', 'origin', 'develop')
                    extra = ()
                    if scenario.startswith('planned'):
                        pass  # the plain window decides the bump itself
                    proc = run_planner(rp_js, port, clone, extra)
                    out = proc.stdout + proc.stderr
                    if scenario.startswith('planned'):
                        # the reviewed explicit version, replayed as a second
                        # dispatch of the same history
                        proc2 = run_planner(rp_js, port, clone,
                                            ('--release-as', '0.9.0'))
                        out2 = proc2.stdout + proc2.stderr
                        check('a reviewed explicit version overrides the computed bump',
                              'chore(develop): release 0.9.0' in out2,
                              'workflow_dispatch release_as is the reviewed override')
                    check(scenario, EXPECTATIONS[scenario](out),
                          f'planner exit {proc.returncode}; tail: {out[-400:]}')
                finally:
                    shutil.rmtree(work, ignore_errors=True)
        finally:
            server.shutdown()

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
