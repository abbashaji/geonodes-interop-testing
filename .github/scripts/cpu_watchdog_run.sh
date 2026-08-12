#!/usr/bin/env bash
# cpu_watchdog_run.sh -- run a command, but kill it automatically if the
# runner's total CPU usage sits near-idle for a sustained window.
#
# This is the CI equivalent of watching a local Blender process's CPU%
# and killing it once it flatlines to 0: legitimately heavy work keeps
# consuming real CPU and is left running for however long it needs, no
# matter how long that is. A hung/crashed process (see KB harness note
# "Script crash does not reliably quit Blender") produces near-zero CPU
# and gets caught within roughly CHECK_INTERVAL * (IDLE_SECONDS_THRESHOLD
# / CHECK_INTERVAL) seconds -- by default under 2 minutes -- instead of
# silently running until the job's outer timeout-minutes cap (or a human
# cancelling it).
#
# Usage: cpu_watchdog_run.sh <command> [args...]
# Exit code: the command's own exit code, or 124 if the watchdog killed it.
#
# Tunables (env, all optional):
#   WATCHDOG_CHECK_INTERVAL   seconds between samples (default 10)
#   WATCHDOG_IDLE_SECONDS     consecutive near-idle seconds before kill (default 90)
#   WATCHDOG_IDLE_PCT         idle% threshold to count a sample as "idle" (default 95)
#
# How it measures "idle": samples the aggregate CPU line in /proc/stat
# (system-wide, not per-PID) at each interval and computes the idle-tick
# delta as a percentage of the total-tick delta since the last sample.
# System-wide rather than per-PID deliberately -- the runner is doing
# nothing else during the test step, and this sidesteps having to walk
# the process tree correctly across xvfb-run's Xvfb + blender children.

set -u

CHECK_INTERVAL="${WATCHDOG_CHECK_INTERVAL:-10}"
IDLE_SECONDS_THRESHOLD="${WATCHDOG_IDLE_SECONDS:-90}"
IDLE_PCT_THRESHOLD="${WATCHDOG_IDLE_PCT:-95}"

if [ "$#" -eq 0 ]; then
  echo "Usage: cpu_watchdog_run.sh <command> [args...]" >&2
  exit 2
fi

# setsid so the whole process tree the command spawns (e.g. xvfb-run's
# Xvfb + blender children) shares one process group -- lets us kill all
# of it at once via the negative-PID form below, instead of leaving
# orphaned children behind.
setsid "$@" &
CMD_PID=$!

read -r _ u1 n1 s1 i1 _ < /proc/stat
idle_elapsed=0

while kill -0 "$CMD_PID" 2>/dev/null; do
  sleep "$CHECK_INTERVAL"

  if ! kill -0 "$CMD_PID" 2>/dev/null; then
    break
  fi

  read -r _ u2 n2 s2 i2 _ < /proc/stat
  total_delta=$(( (u2 + n2 + s2 + i2) - (u1 + n1 + s1 + i1) ))
  idle_delta=$(( i2 - i1 ))
  u1=$u2; n1=$n2; s1=$s2; i1=$i2

  if [ "$total_delta" -le 0 ]; then
    idle_pct=100
  else
    idle_pct=$(( 100 * idle_delta / total_delta ))
  fi

  if [ "$idle_pct" -ge "$IDLE_PCT_THRESHOLD" ]; then
    idle_elapsed=$(( idle_elapsed + CHECK_INTERVAL ))
    echo "[cpu_watchdog] runner CPU ~idle (${idle_pct}%) -- ${idle_elapsed}s/${IDLE_SECONDS_THRESHOLD}s toward kill threshold"
  else
    if [ "$idle_elapsed" -gt 0 ]; then
      echo "[cpu_watchdog] CPU active again (${idle_pct}% busy) -- resetting idle counter, treating as legitimate ongoing work"
    fi
    idle_elapsed=0
  fi

  if [ "$idle_elapsed" -ge "$IDLE_SECONDS_THRESHOLD" ]; then
    echo "=== WATCHDOG KILL: CPU idle for ${idle_elapsed}s -- treating PID $CMD_PID as hung/crashed, not legitimate work. Killing process group. ==="
    kill -9 -"$CMD_PID" 2>/dev/null
    wait "$CMD_PID" 2>/dev/null
    exit 124
  fi
done

wait "$CMD_PID"
exit $?
