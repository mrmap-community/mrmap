# ADR-0002: Semantic versioning policy and release baseline

- **Status:** Accepted
- **Date:** 2026-11-25
- **Issue:** #1578 (epic #1577, release management)
- **Decision source:** the six questions Q1..Q6 asked on #1578 through
  `scripts/decisions` (decision request `dr-d77b305c`), recommended in comment
  `7171521112` and confirmed by the maintainer account `jokiefer` (MEMBER) in
  comment `7171857760` on 2026-11-25. Q5 was confirmed with an explicit
  qualification, recorded in §5 below.
- **Measurement anchor:** `0aeec58d3` on `develop` for the audit of 2026-11-19
  (every counted number below comes from that audit and is reproducible with
  the commands of `docs/source/development/release-versioning-baseline.rst`,
  section "Reproducing the measurements"); this record is written at
  `b5118807f`, where the same commands still answer 0 tags, 0 releases and
  `VERSION` = `0.1.0`.

## Context

MrMap had no release. Measured on 2026-11-19 and re-measured at the anchor of
this record: **0 git tags, 0 GitHub releases, 0 published application images**.
The `0.1.0` in the CHANGELOG heading of 2023-03-23 and in the version constant
was therefore never published — it is a claim with no artifact behind it, and
there is nothing published to be compatible with. That is the fact this record
decides from, and it is why the questions could be answered with "start clean"
rather than "stay compatible with X".

The same audit established that the version string is not cosmetic here. It has
exactly four readers, all in-tree: `SPECTACULAR_SETTINGS['VERSION']` (it becomes
`info.version` of the published OpenAPI document), the system status view
(answered as `id` and `mrmap_release`), the OpenAPI **cache key** in
`backend/extras/schema_views.py`, and the Sphinx `release`. A release tool that
bumped the version for a README fix would ship a new application version, a new
docs version and a new cache identity for zero functional change.

The history a release tool would have to read is not classifiable: of 7585
commit subjects on `develop`, 53 parse as Conventional Commits; the repository
merge-merges (833 `Merge pull request` commits, 0 squash-shaped subjects); the
branch prefixes carry no change class (`ao` names a client, `housekeeping` means
chore and refactor at once). Measured against release-please 17.11.2 starting at
`0.1.0`: `feat` → `0.2.0`, every other type → `0.1.1`, any breaking marker →
**`1.0.0`** unless `bump-minor-pre-major` makes it `0.2.0`, and — the row that
decides the shape of this policy — a history **nothing** parses still bumps
PATCH, because the versioning strategy falls through.

Six normative questions were asked of a person, because they are product
promises and not engineering taste: which version to start publishing, how a
breaking change behaves below 1.0.0, where the change class comes from, whether
docs-only history may consume a version, which upgrade path is supported, and
whether the external API gets its own version axis. All six were answered; this
record is the accepted policy those answers form, together with what they
deliberately do **not** permit.

## Decision

### 1. The application version, and its first value (Q1)

The application stays on `0.x`. The version claimed since 2023-03-23 is kept as
an unpublished historical claim: nothing is retro-tagged. The **first published
tag is `v0.2.0`**, computed by the release tooling from the recorded baseline —
not written by hand.

Tags are `vMAJOR.MINOR.PATCH`, annotated, created only on `master`, and a
published tag is never moved, deleted or re-created. `docs/source/conf.py`
selects them for versioned documentation with `smv_tag_whitelist =
r'^v\d+(\.\d+){1,2}$'`, which admits the accepted three-part shape alongside
the historical two-part one; `scripts/test_release_lifecycle.py` fails if that
pattern drifts from `scripts/release_lifecycle.json`.

The canonical value is the root `VERSION` file (#1579), projected to
`backend/MrMap/version.py` and read by the four consumers above. It is never
hand-edited in a feature pull request.

### 2. What each class of change does to the number (Q2, Q4)

While the major is `0`:

| Change | Header | Changelog section | Bump | Consumes a version |
| --- | --- | --- | --- | --- |
| feature | `feat:` / `feat(scope):` | Added | MINOR | yes |
| contract-changing feature | `feat!:` or `feat:` + `BREAKING CHANGE:` | Breaking Changes (**mandatory**) + Added | MINOR | yes |
| bug fix | `fix:` / `fix(scope):` | Fixed | PATCH | yes |
| security fix | `fix(security):` | Fixed, security named in the line | PATCH | yes |
| breaking security fix | `fix!:` + `BREAKING CHANGE:` | Breaking Changes | MINOR | yes |
| performance, no behaviour change | `perf:` | Changed | PATCH | yes |
| refactor, no behaviour change | `refactor:` | Changed, or omitted from notes | PATCH | yes |
| revert | `revert:` | as the class it reverts | as that class | yes |
| dependency update | `build(deps):` / `chore(deps):` | Dependencies | PATCH, MINOR if it drops a supported version | yes |
| documentation only | `docs:` | not in the release notes | none | **no** |
| tests only | `test:` | not in the release notes | none | **no** |
| CI, tooling, formatting | `ci:`, `chore:`, `style:` | not in the release notes | none | **no** |
| anything else | rejected by the PR classification check | — | — | — |

Two rules follow from that table and are binding:

- **A breaking change never jumps a pre-1.0 application to `1.0.0`.**
  `bump-minor-pre-major: true` is the implemented reading of Q2; the measured
  alternative would have let the adoption of a commit-message convention decide
  to call the product 1.0. Reaching `1.0.0` is a deliberate, separately decided
  act, not an arithmetic result.
- **A window containing only `docs`, `test`, `ci`, `chore`, `style` and `build`
  produces no release at all** — no version, no changelog section, no pull
  request. This is Q4. The mechanism is the hidden section table of
  `release-please-config.json`: hidden classes parse but yield empty notes, and
  empty notes yield no candidate (`strategies/base.js` returns nothing). It is
  pinned by the synthetic scenario `docs and chore windows prepare nothing` of
  `scripts/test_release_planning_synthetic.py`. `scripts/pr_classify` reports
  `consumes_version` per class and never gates on it, so reporting the policy is
  not the same act as deciding it.

The three places this table exists — here, `scripts/pr_classify` `TYPES`, and
the `changelog-sections` of `release-please-config.json` — are held equal by
`scripts/test_release_planning.py`, which compares both directions and fails on
a drift in either.

### 3. Where the class comes from (Q3)

**The Conventional Commit header on the pull request title is authoritative.**
Commit messages keep the lowercase summary style `AGENTS.md` requires; commit
subjects are not the classifier, because measured, 99.3 % of the history does
not parse and a merge subject never parses.

The verification Q3's answer asked for — that the classification and the
breaking marker are really read — is done and is a documented result, not an
assumption:

- `scripts/pr_classify` parses the title of the carrier and reports the class,
  the scope and the breaking fact on every pull request
  (`.github/workflows/pr-classification.yml`).
- The release planner reads the **body** of the merge carrier, splitting the
  title out of it; a `BREAKING CHANGE:` footer in the pull request description
  is read there. `scripts/test_release_planning_synthetic.py` pins those shapes.
- **Known gap, measured and accepted:** release-please 17.11.2 does not parse a
  bang in a pull-request **title** of a merge carrier (`feat!:` is invisible to
  it). The policy therefore requires the breaking fact to travel where the tool
  can read it — a `BREAKING CHANGE:` paragraph in the pull request description,
  `BEGIN_COMMIT_OVERRIDE`, or a reviewed `release_as` on a manual dispatch. The
  synthetic scenario `a bang title alone prepares nothing and says so in the
  log` fails loudly if a future release-please closes the gap, so the
  workaround retires visibly.

### 4. Channels (consequence of Q1 and Q5)

One channel: **stable**, published from `master` only. `develop` is the
development channel and never carries a tag.

A release-candidate channel stays **unopened**. An RC is only useful to somebody
who can test an upgrade against it, which is exactly what Q5 makes conditional
on a verified, supported baseline. Once #1800 has verified one and a release
window exists, cutting `vX.Y.Z-rc.N` is a decision of the promotion issue
(#1584/#1798), not an automatic side effect.

### 5. The supported upgrade window (Q5, qualified)

Single-hop upgrade from any earlier release is promised **only for explicitly
supported and tested released baselines**:

- The set of supported baselines is stated in
  `scripts/release_upgrade_baseline.json` and is verified **before** the first
  stable publication. #1800 owns that verification.
- **No promise is made about an unverified direct upgrade from every historical
  checkout.** Between two releases that are not both in the supported set, an
  installation upgrades release-by-release through the named intermediate
  release, or reinstalls.
- A deprecation stays **two MINOR releases** before removal. That is the unit
  #1180's "accepted compatibility period" needed, and it is what makes the
  sequencing of that issue's Release A (transition) and Release B (removal)
  datable; the ledger already names the intermediate release and its marker
  migration (`notify/0006_remove_backgroundprocess_threads`).
- The migration history is **never squashed**. Migration authoring must survive
  both directions — forward and reverse — because the upgrade promise depends on
  it (#1530's non-reversible `RemoveField` beside its `DeleteModel` is the
  measured failure this rule exists to prevent).
- The staged boundaries of #1180 are honoured by the upgrade gate: a deployment
  may only advance to a #1180-or-later release when the marker migration is
  recorded, and `scripts/release_gates.py` refuses a candidate that breaks a
  protected node or names a retired app again.

### 6. The external contract has no second version axis (Q6)

While the major is `0`, **the application version is the only version**. No
`api-version` field, no versioned media type, no second number. Contract
compatibility is expressed where it already is:

- CSW negotiates `SUPPORTED_CSW_VERSIONS` (2.0.2) per the OGC protocol rules —
  a standard protocol version, untouched by this policy.
- JSON:API resource types, filter names and operation shapes are covered by the
  **breaking change** class of §2: changing one is a breaking change, which owes
  a `BREAKING CHANGE:` note and, before a released baseline exists, the reviewed
  evidence of the contract gate.
- The surfaces that are contract, and the ones that are not, are named in
  `docs/source/development/release-compatibility-gates.rst`; `MrMap.VERSION` is
  already machine-readable for a consumer that needs to detect a shape change
  (`info.version` of the OpenAPI document, `id`/`mrmap_release` of the system
  view).

If a real integrator asks for a stable contract marker, adding one is a new
decision — a second version axis is itself a contract change, so it needs its
own record that supersedes this section, not a quiet field in the OpenAPI info
block.

### 7. What no answer in this record authorises

Confirming a design decision is not implementation approval, is not the
`agent: approved` label, and is not a pull request review. **This record
authorises no publication.** Between it and a `v0.2.0` tag stand the readiness
gates of #1798 (promotion reconciled with the develop-first policy), #1799
(reproducible candidate image and digest-based publication), #1800 (compatibility
verification including the oldest supported baseline, and complete promotion
evidence), #1801 (end-to-end validation of the first `v0.2.0` candidate) and
#1610 (the release documentation gate). The tooling keeps its refusals while
those are open: `scripts/release_promotion.py` and `scripts/image_release.py`
still refuse rolling aliases without a reviewed alias ledger, and
`scripts/release_contract_baseline.json` stays in `pre-baseline` mode until the
first release's own reviewed pull request replaces it.

## Validation

A record without validation is prose. Each assertion below is machine-checkable
and already wired, so a later change that violates the policy fails a suite
rather than disagreeing with a paragraph.

| ID | Assertion | Enforcement | Baseline at this record |
| --- | --- | --- | --- |
| V-1 | `VERSION` matches `^\d+\.\d+\.\d+$` and is the only hand-maintained version; every projection equals it. | `scripts/test_canonical_version.py`, CI | `VERSION` = `0.1.0`, 1 file, 4 readers |
| V-2 | `release-please-config.json` keeps `bump-minor-pre-major: true`, keeps `bump-patch-for-minor-pre-major` absent, and keeps `skip-github-release: true` (no tag ever from `develop`). | `scripts/test_release_planning.py` | all three hold |
| V-3 | The class table of §2 is identical in `scripts/pr_classify` `TYPES`, in the visible/hidden split of `changelog-sections`, and in the visible sections mapping to Keep a Changelog headings. | `scripts/test_release_planning.py` (compares both directions, against the vocabulary module rather than a copy) | 11 classes agree |
| V-4 | A `docs`/`chore`-only window prepares no pull request and no version. | `scripts/test_release_planning_synthetic.py`, scenario `docs and chore windows prepare nothing` | pinned |
| V-5 | A breaking marker below 1.0.0 yields MINOR, never a major. | `scripts/test_release_planning.py` (config key) + `scripts/test_release_planning_synthetic.py` (measured bump) | `0.1.0 → 0.2.0` |
| V-6 | The classification of a pull request is decidable from its title, and an unknown class is reported unclassifiable. | `.github/workflows/pr-classification.yml`, `scripts/test_pr_classify.py` | strict mode from `STRICT_FROM` |
| V-7 | No tag and no GitHub release exists on `develop`; the only tag writer is the promotion `finalize` step on `master`, behind the protected `release-stable` environment. | `.github/workflows/release-planning.yml` checks (`skip-github-release`, no `environment:`/`secrets.`/`deploy:` there), `scripts/test_release_promotion.py` | **0 tags, 0 releases** |
| V-8 | A published tag is never moved: `finalize` refuses when the tag stands elsewhere, refuses a diverged master tree, and refuses to publish before a human merged the candidate. | `scripts/test_release_promotion.py`, `scripts/test_release_lifecycle_dry_run.py` | refusals green |
| V-9 | Rolling aliases are refused while no reviewed alias ledger exists, and no stable version tag moves once written. | `scripts/test_release_promotion.py`, `scripts/test_release_lifecycle_dry_run.py`, `scripts/test_image_release.py` | refused |
| V-10 | The versioned-docs tag selection documents `vMAJOR.MINOR.PATCH` and stays equal to the machine-readable lifecycle. | `scripts/test_release_lifecycle.py` against `docs/source/conf.py` and `scripts/release_lifecycle.json` | `^v\d+(\.\d+){1,2}$` |
| V-11 | The upgrade ledger keeps the #1180 boundary: protected nodes exist, no retired app is referenced as an application, marker migration named. | `scripts/release_gates.py upgrade`, `scripts/test_release_gates.py` | ledger committed |
| V-12 | The contract gate refuses to treat an undeclared `pre-baseline` as an anything-goes window: `reviewed_0_x` plus `declared_on` are required, and `version`/`upgrade` still enforce what a breaking change owes. | `scripts/test_release_gates.py` | enforced |
| V-13 | The decision audit trail exists on #1578 for Q1..Q6 with the maintainer source recorded, and the register of the ADR page agrees with it. | `scripts/decisions scan --issue 1578` (a human run; the tool verifies `author_association`) | Q1–Q6 Accepted, Q5 qualified |
| V-14 | Every first-release readiness gate is closed before a tag exists; no recorded answer substitutes for one. | #1798, #1799, #1800, #1801, #1610; promotion `preflight` refuses incomplete evidence | all five open |

## Consequences

**Enables.** The version string finally means something: it is computed from a
classifiable window, it moves only when a `feat`/`fix`/`perf`/`revert`/breaking
change is in it, and the three places that consume it (OpenAPI `info.version`,
the system view, the docs release) stop churning on documentation pull requests.
Contributors get one place to declare intent — the pull request title — and CI
answers it before merge. Reviewers get a mandatory Breaking Changes section
whenever a release contains a breaking change, which is the artifact the upgrade
promise is documented in. The 0.x floor means the project can adopt Conventional
Commits without accidentally declaring itself 1.0.

**Costs.** Three artefacts must now be kept in step, and they are held by tests
rather than by discipline: the class table in the ADR, in `scripts/pr_classify`,
and in `release-please-config.json`. Legacy history stays unparseable forever
(7532 commits and counting) and contributes nothing but the fallthrough the Q4
suppression exists to stop, so the first release window must be anchored after
the baseline rather than at the beginning of time. Titles become a reviewed
surface: a wrong prefix is a wrong changelog section, which is why the
classification check exists and why making it required is a human act. And the
upgrade promise is now conditional in a way that costs real work — "supported
and tested" means #1800 must actually run an upgrade from the named baseline
before the first stable tag, and every later release inherits that obligation for
whatever it adds to the supported set.

**Deliberate trade-offs.** `refactor` and `perf` consume a PATCH, so a pure
internal refactor ships a version; the alternative (a hand-curated "was this
release-relevant?" judgement per window) is the kind of manual gate this epic
exists to remove. A separate contract version is refused while 0.x even though a
second axis would be easier for an integrator, because introducing it is itself
a contract change and no integrator has asked. RC tags are refused until a
verified upgrade baseline exists, which costs early feedback on release
candidates and buys the guarantee that a published tag is always an artifact a
supported upgrade path exists for. The bang-in-title gap is worked around rather
than blocked on, because the workaround (write the breaking fact in the
description) is what a reviewer should want there anyway — and the gap is pinned
by a test that fails when the tool fixes it.

## Implementation

| Owner | Owns |
| --- | --- |
| #1579 (landed) | canonical `VERSION` and its projections (V-1) |
| #1580 (landed) | `scripts/pr_classify`, the PR-title classification check (V-6) |
| #1581 (landed) | `release-please-config.json`, the bump and suppression reading (V-2, V-4, V-5) |
| #1582 | versioned application images and the deployment manifest for a tag |
| #1583 (landed) | `scripts/release_gates.py` and the reviewed baseline/ledger files (V-11, V-12) |
| #1584 (landed) | `scripts/release_promotion.py`, the only tag writer (V-7, V-8, V-9) |
| #1585 (landed) | `scripts/release_lifecycle.json`, the versioned-docs tag selection, the operator runbook (V-10) |
| #1586 (landed) | the offline lifecycle dry run (V-4 … V-9 against synthetic histories) |
| #1798 | promotion reconciled with the develop-first policy before the first candidate |
| #1799 | reproducible candidate image build and digest-based publication |
| #1800 | verifies the oldest supported upgrade baseline and completes the promotion evidence (V-13 is a precondition, V-14 is its gate) |
| #1801 | end-to-end validation of the first `v0.2.0` candidate |
| #1610 | the autonomous documentation release gate in front of publication |
| #1180 | the Release A/B sequencing that §5's two-MINOR unit makes datable |
