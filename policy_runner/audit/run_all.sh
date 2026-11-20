#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
repo="$(cd .. && pwd)"
status=0

step() {
  printf '\n== %s\n' "$1"
  shift
  "$@" || status=1
}

no_comments() {
  local found
  found=$(grep -rn -e '#' -e '"""' src/policy_runner --include='*.py' | grep -v '/wire.py:' || true)
  found+=$(grep -n -e '#' -e '"""' "$repo"/user_pc/src/leap_teleop/sources/policy_udp.py \
    "$repo"/user_pc/src/leap_teleop/retarget/passthrough.py || true)
  if [ -n "$found" ]; then echo "$found"; return 1; fi
  echo "no comments or docstrings outside the wire.py license header"
}

step "policy_runner acceptance" uv run --extra dev pytest tests/acceptance -q -p no:warnings
step "leap_teleop" uv run --directory "$repo/user_pc" --extra dev pytest -q -p no:warnings
step "control_hub" uv run --directory "$repo/control_hub" --extra dev pytest -q -p no:warnings
step "ruff" uv run --extra dev ruff check src tests audit
step "comments" no_comments
step "mutants" uv run --extra dev python audit/mutants.py

printf '\n== %s\n' "$([ $status -eq 0 ] && echo PASS || echo FAIL)"
exit $status
