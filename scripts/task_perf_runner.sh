#!/bin/sh
# Runs a Celery task-family runtime benchmark and publishes its report (#1396).
#
# WHAT THIS IS FOR
#
# scripts/task_perf_bench.py reads and judges a runtime benchmark; something has
# to run the workload first, inside the environment the record then claims to
# describe. That something is this script: it starts what the workload needs
# (PostGIS and Redis), runs the opt-in Django bench suite in the backend test
# image with a pinned seed and repeat count, and hands the workload files to the
# analyzer for `load`, `report`, `compare`, `detect` and `gate`.
#
# WHY A SCRIPT AND NOT THE LOGIC IN YAML
#
# The same five steps run on an operator's laptop and on the runner. A benchmark
# whose CI invocation differs from its documented local invocation produces two
# things that are not comparable, so the workflow holds a call and no logic and
# the logic lives here, where it can be read and re-run.
#
# NONFLAKINESS RULES, AND WHY EACH ONE IS HERE
#
#   1. The gate runs in `warn` mode unless the caller says otherwise, so a
#      performance report can never redden a pull request. An approving human
#      turns blocking on per family, in scripts/task_perf_baseline.json (#1387).
#   2. Seed, repeat count and workload are arguments with the defaults the docs
#      name, never "whatever the machine chose".
#   3. The suite runs in ONE test process, with --keepdb and without --parallel.
#      Django brings up one PostGIS test database per worker, and the timings of
#      four workers sharing one database describe the contention, not the task.
#   4. The healthcheck of the database is waited for, not slept through: a
#      benchmark against a half-started server is a slow failure with numbers in
#      it, which is the worst kind of flaky.
#   5. A missing docker, a missing image, a skipped suite or an empty output
#      directory is reported as what it is and exits non-zero. A report which
#      silently contains no measurements is the flakiness this issue is about in
#      its worst form - a green that measured nothing.
#
# WHAT NEEDS TO BE PRESENT
#
#   docker + compose   the workload runs in the backend test image, like every
#                      other QA job.
#   python3            the analyzer is stdlib-only and runs on the host.
#
# Usage:
#   scripts/task_perf_runner.sh [--family NAME] [--repeats N] [--seed N]
#                               [--eager] [--heavy] [--mode warn|block]
#                               [--out DIR] [--no-up]
set -u

PYTHON=${PYTHON:-python3}
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO" || exit 1

FAMILY=harvesting.import_chunk
REPEATS=${MRMAP_TASK_PERF_REPEATS:-7}
SEED=${MRMAP_TASK_PERF_SEED:-20261121}
EAGER=0
HEAVY=0
MODE=warn
OUT=${MRMAP_TASK_PERF_OUT:-task-perf}
UP=1
COMPOSE_PROJECT=${COMPOSE_PROJECT_NAME:-mrmap-task-perf}
BENCH_MODULE=tests.django.system.test_task_runtime_bench

while [ $# -gt 0 ]; do
        case "$1" in
                --family) FAMILY=${2:-}; shift 2 ;;
                --repeats) REPEATS=${2:-}; shift 2 ;;
                --seed) SEED=${2:-}; shift 2 ;;
                --eager) EAGER=1; shift ;;
                --heavy) HEAVY=1; shift ;;
                --mode) MODE=${2:-}; shift 2 ;;
                --out) OUT=${2:-}; shift 2 ;;
                --no-up) UP=0; shift ;;
                *) echo "task_perf_runner: unknown argument $1" >&2; exit 2 ;;
        esac
done

case "$MODE" in
        warn|block) ;;
        *) echo "task_perf_runner: --mode wants warn or block, got $MODE" >&2; exit 2 ;;
esac
case "$REPEATS" in
        ''|*[!0-9]*) echo "task_perf_runner: --repeats wants a number, got $REPEATS" >&2; exit 2 ;;
esac
case "$SEED" in
        ''|*[!0-9]*) echo "task_perf_runner: --seed wants a number, got $SEED" >&2; exit 2 ;;
esac

fail() {
        echo "task_perf_runner: $*" >&2
        exit 1
}

command -v docker >/dev/null 2>&1 \
        || fail "no docker on this host: the workload runs in the backend test image and nothing here can measure it without one"
docker compose version >/dev/null 2>&1 \
        || fail "docker compose is not available"

mkdir -p "$OUT" || fail "cannot write to $OUT"
JSONL="$OUT/task-perf.jsonl"
: > "$JSONL" || fail "cannot write $JSONL"

export COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

# The services the workload needs: the database it writes to, and the broker the
# queue-wait reading is about. `up -d` rather than depends_on, so a service which
# does not come up is a message about that service.
if [ "$UP" -eq 1 ]; then
        echo "task_perf_runner: starting postgis and redis (project $COMPOSE_PROJECT)"
        $COMPOSE up -d postgis redis >/dev/null 2>&1 \
                || fail "the stack did not start; run '$COMPOSE -p $COMPOSE_PROJECT up -d postgis redis' to see why"
        tries=0
        while :; do
                PID=$($COMPOSE ps -q postgis 2>/dev/null | head -n 1)
                [ -n "$PID" ] || fail "compose knows no postgis container"
                STATE=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$PID" 2>/dev/null)
                case "$STATE" in
                        healthy) break ;;
                        none)
                                # a service without a healthcheck: running is all it promises
                                RUNNING=$(docker inspect -f '{{.State.Running}}' "$PID" 2>/dev/null)
                                [ "$RUNNING" = "true" ] && break
                                ;;
                        *) ;;
                esac
                tries=$((tries + 1))
                [ "$tries" -gt 60 ] && fail "postgis never became healthy (last state: $STATE)"
                sleep 5
        done
fi

# The workload. Every knob the record documents is passed explicitly, so the
# JSONL describes the run that produced it and nothing has to be remembered.
# The suite skips unless MRMAP_TASK_PERF_BENCH says otherwise - that is what
# keeps this stopwatch out of the ordinary unit-tests job.
# shellcheck disable=SC2086  # $EXTRA_ENV is a deliberate word list of -e flags
EXTRA_ENV=""
[ "$HEAVY" = "1" ] && EXTRA_ENV="$EXTRA_ENV -e MRMAP_TASK_PERF_HEAVY=1"
[ "$EAGER" = "1" ] && EXTRA_ENV="$EXTRA_ENV -e MRMAP_TASK_PERF_EAGER=1"

echo "task_perf_runner: benchmarking $FAMILY (repeats=$REPEATS seed=$SEED eager=$EAGER heavy=$HEAVY)"
$COMPOSE run --rm --build \
        -e MRMAP_TASK_PERF_BENCH=1 \
        -e MRMAP_TASK_PERF_REPEATS="$REPEATS" \
        -e MRMAP_TASK_PERF_SEED="$SEED" \
        -e MRMAP_TASK_PERF_OUT=/opt/mrmap/"$OUT" \
        $EXTRA_ENV \
        django-tests python manage.py test "$BENCH_MODULE" \
        --noinput --keepdb -v 2 \
        || fail "the benchmark run did not finish; its output is above"

# The reading. One `load` per workload file: the file carries its own arm,
# repeat, seed and environment, so the analyzer's identity check has something
# real to refuse when an arm's workload changed between runs.
FILES=0
for file in "$OUT"/*.json; do
        [ -f "$file" ] || continue
        FILES=$((FILES + 1))
        "$PYTHON" scripts/task_perf_bench.py load \
                --fixture "$file" --out "$JSONL" >/dev/null \
                || fail "$file is not a workload this analyzer understands"
done
if [ "$FILES" -eq 0 ]; then
        fail "$OUT holds no workload file: the suite skipped (MRMAP_TASK_PERF_BENCH unset, or the module moved) rather than measuring nothing"
fi

echo
"$PYTHON" scripts/task_perf_bench.py report --in "$JSONL" | tee "$OUT/report.txt"

echo
echo "task_perf_runner: every workload cell, against the baseline of its workload"
# One line per (family, scale, arm), with its ratio over the baseline arm of the
# same workload and whatever the detectors found. `summary` prints it because it
# owns the record format; a caller parsing JSON out of `compare` with sed would
# be a second, weaker definition of the same thing.
"$PYTHON" scripts/task_perf_bench.py summary --in "$JSONL" \
        --out "$OUT/summary.txt" | tee "$OUT/summary.log"

echo
# The detector artifacts, one file per arm, so a reviewer can read *why* a cell
# was flagged without re-running anything. The reading of them is the summary's
# line above; these are the numbers behind it.
DETECTIONS=0
for arm in baseline sql-n-plus-one duplicate-remote-call slow-body; do
        # stdout is the JSON artifact, stderr the one-line verdict; the verdict
        # stays on the console so "0 detections" is read at the moment the report
        # is, rather than discovered in a file after the job is green
        if "$PYTHON" scripts/task_perf_bench.py detect --in "$JSONL" --arm "$arm" \
                --out "$OUT/detect-$arm.json" 2>"$OUT/detect-$arm.txt"; then
                sed 's/^/  /' "$OUT/detect-$arm.txt"
                # the analyzer prints `detected=none` for a clean arm and a
                # comma list otherwise, so the two cases are exhaustive
                case "$(cat "$OUT/detect-$arm.txt")" in
                        *detected=none) ;;
                        *) DETECTIONS=$((DETECTIONS + 1)) ;;
                esac
        else
                echo "  detect: no $arm arm at these scales"
        fi
done
[ "$DETECTIONS" -eq 0 ] \
        && echo "  all arms clean; a clean report and an untested one differ -" \
           "a family with no declared contract judges only super-linear growth"

echo
# stdout of `gate` is the machine-readable report, which belongs in the artifact;
# its stderr is the one-line verdict, which belongs on the console.
"$PYTHON" scripts/task_perf_bench.py gate --in "$JSONL" \
        --baseline scripts/task_perf_baseline.json --mode "$MODE" \
        --out "$OUT/gate.json" 2> "$OUT/gate.txt"
GATE=$?
cat "$OUT/gate.txt"
echo
echo "task_perf_runner: $FILES workload record(s) in $JSONL; artifacts in $OUT"
echo "task_perf_runner: mode=$MODE exit=$GATE (warn never fails a job; a blocking gate needs a reviewed baseline entry)"
exit "$GATE"
