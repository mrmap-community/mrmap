#!/bin/sh
# Runs every test suite of the repository's own tooling in scripts/.
#
# WHY THIS EXISTS
#
# scripts/ holds the tools that the agent orchestration runs: wip (the claim
# board and issue identity), agent_capacity (the host admission gate that every
# worker spawn consults) and decisions (the human decision protocol). Each of
# them has a suite, and every one of those suites runs offline with nothing but
# the standard library. None of them is reachable from CI: the QA jobs run in a
# container that binds only ./backend, so scripts/ is not even inside the image
# that does the linting. A regression here surfaces as an agent that starts
# mislabelling or double-claiming work on some operator's host, which is a slow
# and expensive way to learn that a tool broke.
#
# WHAT THIS DOES NOT DO
#
# It does not build images, start containers or touch the network. Suites that
# want docker probe for it and skip the affected checks out loud; the count in
# the summary is then smaller than the count on a docker host, and that is the
# honest reading rather than a green that means nothing.
#
# WHAT NEEDS TO BE PRESENT
#
#   git     test_migration_graph_smoke.py drives real repositories. The backend
#           container image (python:*-alpine) has no git, so a job for these
#           suites belongs on a runner with a plain checkout, not inside django.
#   docker  test_dev_image_* use it where they can; absent it, they skip.
#
# Usage: scripts/check_repo_tooling.sh

set -u

PYTHON=${PYTHON:-python3}
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO" || exit 1

if [ ! -d scripts ]; then
	echo "check_repo_tooling: no scripts/ directory in $REPO" >&2
	exit 1
fi

# A runner without git would report the migration-graph suite as a failure of
# the code under test, which it is not. Say it once, before the results, so the
# log cannot be read as "the tooling is broken".
if command -v git >/dev/null 2>&1; then
	GIT_NOTE="git found"
else
	GIT_NOTE="no git on this runner: the migration-graph suite will fail for that reason alone"
fi

if command -v docker >/dev/null 2>&1; then
	DOCKER_NOTE="docker found"
else
	DOCKER_NOTE="no docker: image suites skip their container checks"
fi

echo "Repository tooling suites ($GIT_NOTE, $DOCKER_NOTE)"
echo

FAILED=0
TOTAL=0
for suite in scripts/test_*.py; do
	[ -f "$suite" ] || continue
	TOTAL=$((TOTAL + 1))
	START=$(date +%s)
	OUT=$("$PYTHON" "$suite" 2>&1)
	STATUS=$?
	END=$(date +%s)
	# The suites print their own verdict on the last line; showing it keeps a
	# failure readable without opening a log.
	SUMMARY=$(printf '%s\n' "$OUT" | sed '/^[[:space:]]*$/d' | tail -n 1)
	if [ "$STATUS" -eq 0 ]; then
		printf '  ok    %-38s %4ss  %s\n' "$(basename "$suite")" \
			"$((END - START))" "$SUMMARY"
	else
		FAILED=$((FAILED + 1))
		printf '  FAIL  %-38s %4ss  exit %s\n' "$(basename "$suite")" \
			"$((END - START))" "$STATUS"
		printf '%s\n' "$OUT" | tail -n 20 | sed 's/^/        /'
	fi
done

echo
if [ "$TOTAL" -eq 0 ]; then
	echo "check_repo_tooling: found no suite to run, which is not a pass" >&2
	exit 1
fi
if [ "$FAILED" -ne 0 ]; then
	echo "$FAILED of $TOTAL suite(s) failed." >&2
	exit 1
fi
echo "All $TOTAL suite(s) passed."
